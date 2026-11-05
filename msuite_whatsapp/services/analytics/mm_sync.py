"""
WhatsApp Marketing Messages metrics sync.

Pulls ``GET /<WABA_ID>/template_analytics`` for the account's MARKETING templates, once per product
type (``MARKETING_MESSAGES_LITE_API`` and ``CLOUD_API``: broadcasts go out over both routes), and
upserts one ``WhatsApp Marketing Metric`` row per (account, template_id, day, product_type). A
400 for one product type ends only that type's series; 401 / 403 / throttle / network errors stop
the account. The product types are assumed disjoint (UNVERIFIED: needs a live check with real
sends); per-broadcast attribution sums them. Runs from ``sync_daily_tasks`` (no extra cron) and from the manual
Refresh button. Not whitelisted: callers enforce permissions.

Docs (fetched 2026-10-20): https://developers.facebook.com/documentation/business-messaging/whatsapp/analytics
Request form used: ``metric_types=SENT,DELIVERED,...`` (comma list) and ``template_ids=[id1,id2]``
(bracketed, unquoted), as in the docs examples. Plan U5 is unresolved: the docs do not state that
the older JSON-quoted form is rejected, and no live response has confirmed this form.

Meta resets Read/Click counts 7 days after a send (``META_READ_CLICK_RETENTION_DAYS``); rows older
than that never get read/clicked/quick_reply_clicked lowered (see ``_should_overwrite``).
Metrics Meta did not report are passed as None; the DocType records them in ``unavailable_fields``.
"""

import json
from datetime import date

import frappe
from frappe.utils import add_days, cint, getdate, now, today

from msuite_core.constants import GRAPH_API_URL, GRAPH_API_VERSION, LOGGER_NAME
from msuite_whatsapp.constants import WHATSAPP_MM_TERMS_DEFAULT_PREFIX
from msuite_whatsapp.constants import (
	ANALYTICS_BACKFILL_DAYS,
	ANALYTICS_REFETCH_DAYS,
	HTTP_STATUS_BAD_REQUEST,
	HTTP_STATUS_TOO_MANY_REQUESTS,
	META_READ_CLICK_RETENTION_DAYS,
	META_THROTTLE_ERROR_CODES,
	MM_METRIC_TYPES_CORE,
	MM_METRICS_RETENTION_DAYS,
	MM_SYNC_GRANULARITY,
	MM_SYNC_LIST_SEPARATOR,
	MM_SYNC_PRODUCT_TYPES,
	MM_SYNC_SKIP_DISABLED,
	MM_SYNC_SKIP_NO_TEMPLATES,
	MM_SYNC_SKIP_NOT_AVAILABLE,
	MM_SYNC_SKIP_PERMISSION,
	MM_SYNC_SKIP_RATE_LIMITED,
	MM_SYNC_SKIP_REAUTH,
	MM_SYNC_SKIP_REQUEST_FAILED,
	TEMPLATE_ANALYTICS_BATCH_SIZE,
	TEMPLATE_ANALYTICS_MAX_LOOKBACK_DAYS,
	TEMPLATE_ANALYTICS_MIN_DAYS,
	WABA_UTC_OFFSET_FIELD,
	WABA_UTC_OFFSET_SYNCED_FIELD,
	WHATSAPP_MM_SENDABLE_CATEGORY,
	WHATSAPP_MM_SITE_CONFIG_KEY,
)
from msuite_core.services.plans.plan_enforcer import is_feature_enabled
from msuite_whatsapp.services.analytics import sync as analytics_sync
from msuite_whatsapp.services.analytics.mm_parse import (
	derive_utc_offset_minutes,
	extract_day_starts,
	parse_template_analytics,
)

DOCTYPE = "WhatsApp Marketing Metric"
# Reset by Meta 7 days after send; never lowered on old rows.
RESET_FIELDS = ("read", "clicked", "quick_reply_clicked")
VALUE_FIELDS = (
	"sent", "delivered", "read", "clicked", "quick_reply_clicked",
	"amount_spent", "cost_per_delivered", "cost_per_click", "purchase_value",
)
logger = frappe.logger(LOGGER_NAME)


def _today() -> date:
	"""Return today's date (single patch point for tests)."""
	return getdate(today())


def _is_enabled(account_name: str, waba_id: str) -> bool:
	"""True when the analytics plan feature is on and the site/WABA opted into Marketing Messages.

	Opt-in is the site_config flag or the per-WABA default set when Meta reports the MM terms signed.
	"""
	from msuite_core.central_config import get_central_config

	if not is_feature_enabled("analytics"):
		return False
	return bool(
		cint(get_central_config(WHATSAPP_MM_SITE_CONFIG_KEY))
		or frappe.db.get_default(f"{WHATSAPP_MM_TERMS_DEFAULT_PREFIX}{waba_id}")
	)


def _get_credentials(account_name: str) -> tuple[str, str]:
	"""Return (waba_id, token) and enable Meta insights once if needed.

	Raises frappe.ValidationError when the account lacks a WABA ID or token.
	Side effects: may POST the one-time insights enable and set `is_enabled_for_insights`.
	"""
	account = frappe.get_doc("WhatsApp Account", account_name)
	waba_id, token = analytics_sync._get_waba_credentials(account)
	if not account.is_enabled_for_insights:
		analytics_sync._enable_insights(waba_id, token)
		frappe.db.set_value("WhatsApp Account", account_name, "is_enabled_for_insights", 1)
	return waba_id, token


def _get_waba_id(account_name: str) -> str | None:
	"""Return the account's WABA ID (or business ID), or None."""
	waba_id, business_id = frappe.db.get_value("WhatsApp Account", account_name, ["waba_id", "business_id"]) or (None, None)
	return waba_id or business_id


def _get_marketing_templates(account_name: str) -> dict[str, str]:
	"""Return {meta_template_id: WhatsApp Templates name} for the account's MARKETING templates with an id."""
	rows = frappe.get_all(
		"WhatsApp Templates",
		filters={"whatsapp_account": account_name, "id": ["is", "set"], "category": WHATSAPP_MM_SENDABLE_CATEGORY},
		fields=["name", "id"],
	)
	return {str(r.id): r.name for r in rows}


def _has_rows(account_name: str) -> bool:
	"""True if the account already has metric rows (False means first run: back-fill)."""
	return bool(frappe.db.exists(DOCTYPE, {"whatsapp_account": account_name}))


def _window_days(days: int | None, first_run: bool) -> int:
	"""Look-back in days: explicit `days` (clamped), else back-fill on first run, else the daily refetch window."""
	default = ANALYTICS_BACKFILL_DAYS if first_run else ANALYTICS_REFETCH_DAYS
	return max(TEMPLATE_ANALYTICS_MIN_DAYS, min(cint(days) or default, TEMPLATE_ANALYTICS_MAX_LOOKBACK_DAYS))


def _get_account_currency(account_name: str) -> str | None:
	"""Return the WABA/account currency (from WhatsApp Account), or None if not known.

	Checks `waba_currency` then `currency` on WhatsApp Account. If neither is set, returns None.
	Never invents a default currency (honesty semantics).

	Args:
		account_name: WhatsApp Account document name.

	Returns:
		Currency string (e.g. 'USD', 'INR') or None.
	"""
	if not account_name:
		return None
	account = frappe.db.get_value(
		"WhatsApp Account",
		account_name,
		["waba_currency", "currency"] if frappe.db.has_column("WhatsApp Account", "currency") else ["waba_currency"],
		as_dict=True,
	)
	if account:
		return account.get("waba_currency") or account.get("currency") or None
	return None


def _parse_conversions(value) -> dict:
	"""Parse a conversions dict or JSON string into a dict; empty dict on failure.

	Args:
		value: dict or JSON string representation of conversions.

	Returns:
		dict of conversion counts.
	"""
	if isinstance(value, dict):
		return value
	try:
		parsed = json.loads(value or "{}")
		return parsed if isinstance(parsed, dict) else {}
	except (TypeError, ValueError):
		return {}


def _get_account_utc_offset(account_name: str) -> int | None:
	"""Retrieve the stored WABA UTC offset (minutes east of UTC) for account_name, else None.

	Args:
		account_name: WhatsApp Account document name.

	Returns:
		int minutes east of UTC if set and previously synced, else None.
		Has no side effects; does not raise.
	"""
	if not account_name or not frappe.db.has_column("WhatsApp Account", WABA_UTC_OFFSET_FIELD):
		return None
	current = frappe.db.get_value("WhatsApp Account", account_name, [WABA_UTC_OFFSET_FIELD, WABA_UTC_OFFSET_SYNCED_FIELD])
	if not current or not current[1]:
		return None
	return current[0]


def _fetch_template_batch(account_name, waba_id, token, template_ids, start, end, product_type, day_starts=None, utc_offset_minutes=None):
	"""GET template_analytics of one `product_type` for one batch of template ids.

	`day_starts`: optional set that receives the response's unix `start` values (for the UTC offset).
	`utc_offset_minutes`: optional WABA UTC offset in minutes east of UTC to resolve local dates unambiguously.

	Returns (rows, error): parsed rows restricted to `template_ids` and tagged with `product_type`, or ([], err dict from
	`_call_meta_api_with_error`). Side effects: HTTP GET; may flag the account for re-auth on 401.
	"""
	params = {
		"start": start,
		"end": end,
		"granularity": MM_SYNC_GRANULARITY,
		"product_type": product_type,
		"metric_types": MM_SYNC_LIST_SEPARATOR.join(MM_METRIC_TYPES_CORE),
		"template_ids": f"[{MM_SYNC_LIST_SEPARATOR.join(template_ids)}]",
		"use_waba_timezone": "true",
		"access_token": token,
	}
	body, err = analytics_sync._call_meta_api_with_error(
		f"{GRAPH_API_URL}/{GRAPH_API_VERSION}/{waba_id}/template_analytics", params, account_name
	)
	if err:
		return [], err
	if day_starts is not None:
		day_starts.update(extract_day_starts(body))
	wanted = set(template_ids)
	return [{**r, "product_type": product_type} for r in parse_template_analytics(body, utc_offset_minutes=utc_offset_minutes) if r["template_id"] in wanted], None


def _classify_error(err: dict) -> str | None:
	"""Map a Meta error to the skip reason that should stop the account, or None to keep going."""
	status, code = err.get("status_code"), err.get("code")
	if analytics_sync._is_token_error(err):
		return MM_SYNC_SKIP_REAUTH
	if status == HTTP_STATUS_TOO_MANY_REQUESTS or code in META_THROTTLE_ERROR_CODES:
		return MM_SYNC_SKIP_RATE_LIMITED
	if analytics_sync._is_permission_error(err):
		return MM_SYNC_SKIP_PERMISSION
	if status == HTTP_STATUS_BAD_REQUEST:
		return MM_SYNC_SKIP_NOT_AVAILABLE
	if err.get("exception") or (code is None and isinstance(status, int) and status < HTTP_STATUS_BAD_REQUEST):
		return MM_SYNC_SKIP_REQUEST_FAILED  # network failure or non-JSON body
	return None


def sync_marketing_metrics(account_name: str, days: int | None = None) -> dict:
	"""Sync Marketing Messages template metrics for one account.

	Args:
	    account_name: WhatsApp Account name.
	    days: optional look-back override, clamped to [1, TEMPLATE_ANALYTICS_MAX_LOOKBACK_DAYS].
	        Default: 30 days on the first run, 7 afterwards.

	Returns:
	    {"rows": rows written, "skipped": reason or None, "errors": [token-free messages]}.
	    Never raises for Meta/network failures; one bad batch does not abort the rest. A 400
	    ("not available") ends only that product type's series (`skipped` is set to it only when
	    every product type was refused); token/permission/throttle/network errors stop the account.
	Side effects: HTTP GETs, upserts, one commit per account (also after a partial failure).
	"""
	result = {"rows": 0, "skipped": None, "errors": []}
	waba_id = _get_waba_id(account_name)
	if not waba_id or not _is_enabled(account_name, waba_id):
		result["skipped"] = MM_SYNC_SKIP_DISABLED
		return result
	templates = _get_marketing_templates(account_name)
	if not templates:
		result["skipped"] = MM_SYNC_SKIP_NO_TEMPLATES
		return result

	waba_id, token = _get_credentials(account_name)
	waba_currency = _get_account_currency(account_name)
	utc_offset_minutes = _get_account_utc_offset(account_name)
	end_day = _today()
	end = str(end_day)
	start = str(add_days(end_day, -_window_days(days, not _has_rows(account_name))))
	ids = list(templates)
	refused = 0  # product types Meta answered 400 for
	day_starts: set[int] = set()  # WABA-local midnights seen, to derive the account's UTC offset
	for product_type in MM_SYNC_PRODUCT_TYPES:
		for i in range(0, len(ids), TEMPLATE_ANALYTICS_BATCH_SIZE):
			batch = ids[i : i + TEMPLATE_ANALYTICS_BATCH_SIZE]
			rows, err = _fetch_template_batch(
				account_name, waba_id, token, batch, start, end, product_type, day_starts, utc_offset_minutes=utc_offset_minutes
			)
			if err:
				result["errors"].append(err.get("message") or "Meta request failed")
				reason = _classify_error(err)
				if reason == MM_SYNC_SKIP_NOT_AVAILABLE:
					refused += 1
					break  # this product type is unavailable; try the next one
				if reason:
					result["skipped"] = reason
					break
				continue
			for row in rows:
				row.update(
					whatsapp_account=account_name,
					template=templates[row["template_id"]],
					currency=row.get("currency") or waba_currency,
				)
				result["rows"] += 1
				_upsert_metric_row(row)
		if result["skipped"]:
			break
	if refused == len(MM_SYNC_PRODUCT_TYPES):
		result["skipped"] = MM_SYNC_SKIP_NOT_AVAILABLE
	_store_utc_offset(account_name, derive_utc_offset_minutes(day_starts, getdate(start), end_day))
	frappe.db.commit()
	return result


def _store_utc_offset(account_name: str, offset_minutes: int | None) -> bool:
	"""Persist the WABA UTC offset (minutes east of UTC) on the WhatsApp Account when it changed.

	A synced-at stamp marks a derived value, because an Int column reads 0 (a valid offset) when
	never set. No-op when `offset_minutes` is None, the account is missing, or the columns do not
	exist yet (site not migrated). Returns True when a write happened.
	Side effects: one DB update, no commit, `modified` untouched.
	"""
	if offset_minutes is None or not frappe.db.has_column("WhatsApp Account", WABA_UTC_OFFSET_FIELD):
		return False
	current = frappe.db.get_value("WhatsApp Account", account_name, [WABA_UTC_OFFSET_FIELD, WABA_UTC_OFFSET_SYNCED_FIELD])
	if not current or (current[1] and current[0] == offset_minutes):
		return False
	frappe.db.set_value(
		"WhatsApp Account",
		account_name,
		{WABA_UTC_OFFSET_FIELD: offset_minutes, WABA_UTC_OFFSET_SYNCED_FIELD: now()},
		update_modified=False,
	)
	return True


def _should_overwrite(existing: dict, new: dict, today_date: date, field: str) -> bool:
	"""Whether `new[field]` may replace `existing[field]`.

	Unreported (None) values never overwrite. For rows older than META_READ_CLICK_RETENTION_DAYS,
	read/clicked/quick_reply_clicked only ever increase (Meta resets them to 0 after 7 days).
	Everything else (sent, delivered, cost) updates.
	"""
	value = new.get(field)
	if value is None:
		return False
	if field in RESET_FIELDS:
		age = (today_date - getdate(existing["metric_date"])).days
		if age > META_READ_CLICK_RETENTION_DAYS:
			return value > (existing.get(field) or 0)
	return True


def _apply_row_update(doc, row: dict, today_date: date) -> bool:
	"""Apply changes from row to doc.

	Args:
		doc: WhatsApp Marketing Metric document.
		row: Dict with metric fields.
		today_date: Current date for age check.

	Returns:
		True if any field or conversion changed, False if unchanged.
	"""
	changed = False
	try:
		prev_unavail = set(json.loads(doc.unavailable_fields or "[]"))
	except (TypeError, ValueError):
		prev_unavail = set()

	for f in VALUE_FIELDS:
		if row.get(f) is None:
			# Unreported field -> write None so _record_unavailable_fields keeps it unavailable
			doc.set(f, None)
			if f not in prev_unavail:
				changed = True
		else:
			if f in prev_unavail:
				doc.set(f, row[f])
				changed = True
			elif _should_overwrite(doc.as_dict(), row, today_date, f):
				if doc.get(f) != row[f]:
					doc.set(f, row[f])
					changed = True

	for f in ("clicks_supported", "conversions_available"):
		if row.get(f) and not doc.get(f):
			doc.set(f, row[f])
			changed = True

	currency = row.get("currency") or None
	if doc.get("currency") != currency:
		doc.set("currency", currency)
		changed = True

	new_conversions = _parse_conversions(row.get("conversions"))
	old_conversions = _parse_conversions(doc.get("conversions"))
	if new_conversions != old_conversions:
		doc.conversions = json.dumps(new_conversions)
		changed = True

	new_template = row.get("template")
	if new_template and doc.get("template") != new_template:
		doc.template = new_template
		changed = True

	return changed


def _upsert_metric_row(row: dict) -> str:
	"""Insert or update the metric row for (account, template_id, metric_date, product_type).

	If a concurrent insert raises frappe.DuplicateEntryError, re-fetches the existing row
	and applies the update instead of crashing the sync.

	Args:
		row: Dict with metric fields and identifiers.

	Returns:
		'inserted', 'updated' or 'unchanged'.

	Side effects:
		DB write (no commit); links are not re-validated.
	"""
	key = {k: row[k] for k in ("whatsapp_account", "template_id", "metric_date", "product_type")}
	name = frappe.db.get_value(DOCTYPE, key, "name")

	if not name:
		doc = frappe.new_doc(DOCTYPE)
		doc.update({
			**key,
			**{f: row.get(f) for f in VALUE_FIELDS},
			"clicks_supported": row.get("clicks_supported", False),
			"conversions_available": row.get("conversions_available", False),
			"currency": row.get("currency") or None,
			"template": row.get("template"),
			"conversions": json.dumps(_parse_conversions(row.get("conversions"))),
			"raw_data": json.dumps(row, default=str),
			"synced_at": now(),
		})
		doc.flags.ignore_links = True
		try:
			doc.save(ignore_permissions=True)
			return "inserted"
		except frappe.DuplicateEntryError:
			name = frappe.db.get_value(DOCTYPE, key, "name")
			if not name:
				raise

	doc = frappe.get_doc(DOCTYPE, name)
	today_date = _today()
	changed = _apply_row_update(doc, row, today_date)
	if not changed:
		return "unchanged"
	doc.raw_data = json.dumps(row, default=str)
	doc.synced_at = now()
	doc.flags.ignore_links = True
	doc.save(ignore_permissions=True)
	return "updated"


def prune_old_marketing_metrics() -> int:
	"""Delete metric rows older than MM_METRICS_RETENTION_DAYS (the cut-off day itself is kept).

	Returns the number of rows removed. Side effects: DB delete and commit.
	"""
	cutoff = add_days(_today(), -MM_METRICS_RETENTION_DAYS)
	count = frappe.db.count(DOCTYPE, {"metric_date": ["<", cutoff]})
	if count:
		frappe.db.delete(DOCTYPE, {"metric_date": ["<", cutoff]})
		frappe.db.commit()
	return count
