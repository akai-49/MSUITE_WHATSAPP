"""
Per-broadcast and per-campaign WhatsApp metrics (roadmap 5.3, decision D2).

Days are the WABA's local days: a valid IANA `waba_timezone`, else a fixed offset derived at sync time
(mm_sync), else template-level. A fixed offset cannot follow daylight saving (see README).

Honesty rules (see README, "Per-broadcast metrics"):
- Sent / Delivered / Read / Failed are exact: counted from Channel Message rows of the broadcast.
- Meta reports clicks and conversions per TEMPLATE per day only. They are labelled "exact" only
  when, for every day the broadcast sent, Meta's `sent` equals our sent count (strict, D8) and Meta
  returned the metric. Meta's numbers are SUMMED over the product types (MM-Lite + Cloud API, one
  Marketing Metric row each per day), because broadcasts go out over both routes. UNVERIFIED: the
  product types are assumed disjoint (a send counted under exactly one); needs a live check with
  real sends. A day with only one product type's row is valid (the other sent nothing); a day with
  no row at all is missing. Otherwise they are "template_level" (the whole template's numbers for those
  days, shared with every other send of the template) or "unavailable". Nothing is prorated.
- A metric Meta did not report is "unavailable", never 0.

Read-only: no DB writes. Permission checks live in the whitelisted endpoints
(`whatsapp/api/bulk_messages.py`); the functions here assume the caller already checked.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import frappe
from frappe import _
from frappe.utils import get_system_timezone

from msuite_core.constants import SECONDS_PER_MINUTE
from msuite_whatsapp.constants import (
	MM_BROADCAST_ROWS_LIMIT,
	WABA_UTC_OFFSET_FIELD,
	WABA_UTC_OFFSET_SYNCED_FIELD,
	MessageStatus,
)

BULK_MESSAGE_DOCTYPE = "Bulk WhatsApp Message"
METRIC_DOCTYPE = "WhatsApp Marketing Metric"

ATTRIBUTION_EXACT = "exact"
ATTRIBUTION_TEMPLATE_LEVEL = "template_level"
ATTRIBUTION_UNAVAILABLE = "unavailable"
# Weakest label wins when rolling several broadcasts into a campaign.
_ATTRIBUTION_STRENGTH = {ATTRIBUTION_UNAVAILABLE: 0, ATTRIBUTION_TEMPLATE_LEVEL: 1, ATTRIBUTION_EXACT: 2}

UNKNOWN_KEY = "unknown"  # breakdown key for blank send_path / pricing_category (legacy rows)
TEMPLATE_LEVEL_CAPTION = "all sends of this template"
_MINUTE_FORMAT = "%%Y-%%m-%%d %%H:%%i"  # MariaDB DATE_FORMAT (%% escapes the driver param marker); sub-hour buckets keep :30/:45 zones correct
_MINUTE_PARSE = "%Y-%m-%d %H:%M"
_SENT_STATUSES = (MessageStatus.SENT, MessageStatus.DELIVERED, MessageStatus.READ)
_STATUS_TIME_COLUMNS = ("read_at", "delivered_at", "sent_at", "failed_at")
_COUNT_FIELDS = ("sent", "delivered", "read", "clicked", "quick_reply_clicked")


# --------------------------------------------------------------------------- pure helpers


def _rate(numerator: int, denominator: int) -> float | None:
	"""Return numerator/denominator, or None when the denominator is 0 (never a fake 0%)."""
	return numerator / denominator if denominator else None


def _loads_list(value) -> list:
	"""Parse a JSON list column; anything malformed yields an empty list."""
	try:
		parsed = json.loads(value or "[]")
	except (TypeError, ValueError):
		return []
	return parsed if isinstance(parsed, list) else []


def _sum_conversions(rows: list) -> dict:
	"""Sum the per-row `conversions` JSON objects key by key (non-numeric values skipped)."""
	total: dict = defaultdict(float)
	for row in rows:
		try:
			parsed = json.loads(row.get("conversions") or "{}")
		except (TypeError, ValueError):
			continue
		for key, value in (parsed.items() if isinstance(parsed, dict) else []):
			if isinstance(value, (int, float)) and not isinstance(value, bool):
				total[key] += value
	return dict(total)


def _day_rows(value) -> list:
	"""Normalise one day's metric entry to a list of rows (a bare row dict counts as one product type)."""
	if not value:
		return []
	return value if isinstance(value, list) else [value]


def _active_metric_rows(rows: list) -> list:
	"""Return rows that carried traffic (sent > 0 or sent unavailable); fall back to all rows if none.

	Args:
		rows: list of Marketing Metric row dicts.

	Returns:
		filtered list of rows that carried traffic, or all rows if none carried traffic.
	"""
	active = [
		r for r in rows
		if (r.get("sent") or 0) > 0 or "sent" in _loads_list(r.get("unavailable_fields"))
	]
	return active or rows


def _template_totals(rows: list, days: list[date], missing_days: list[date]) -> dict:
	"""Sum Marketing Metric rows (all product types, all days) into the template-level block.

	A count is None when any active row (sent > 0) lists it in `unavailable_fields`. Mixed currencies
	give `amount_spent` None. `complete` is False when a sending day has no synced row.

	Args:
		rows: list of Marketing Metric row dicts across all days and product types.
		days: list of sending dates.
		missing_days: list of sending dates with no metric rows.

	Returns:
		dict containing totals, amount_spent, currency, conversions, and completeness info.
	"""
	active = _active_metric_rows(rows)
	unavailable = {name for row in active for name in _loads_list(row.get("unavailable_fields"))}
	totals = {f: (None if f in unavailable else sum(row.get(f) or 0 for row in rows)) for f in _COUNT_FIELDS}
	currencies = {row.get("currency") for row in active if row.get("currency")}
	spent_unknown = "amount_spent" in unavailable or len(currencies) > 1
	return {
		"caption": TEMPLATE_LEVEL_CAPTION,
		"from_date": days[0].isoformat(),
		"to_date": days[-1].isoformat(),
		**totals,
		"amount_spent": None if spent_unknown else sum(row.get("amount_spent") or 0 for row in rows),
		"currency": next(iter(currencies)) if len(currencies) == 1 else None,
		"conversions": _sum_conversions(rows),
		"complete": not missing_days,
		"missing_days": [d.isoformat() for d in missing_days],
	}


def _resolve_attribution(
	broadcast_daily_sent: dict[date, int],
	template_daily: dict[date, list[dict] | dict],
	block_reason: str | None = None,
	day_note: str | None = None,
) -> dict:
	"""Decide how far Meta's per-template numbers can be attributed to one broadcast.

	Args:
	    broadcast_daily_sent: our sent count per day (WABA-timezone days) for the broadcast.
	    template_daily: Marketing Metric rows (dict-like) of the broadcast's template, keyed by day:
	        a list with one row per product type (a bare row counts as a one-element list).
	    block_reason: when set, exact matching is impossible (unknown timezone, undated sends...);
	        the result is template-level at best and carries this reason.
	    day_note: when the days came from a fixed UTC offset, a sentence appended to the reason of every
	        result that compared days (the daylight-saving caveat).

	Returns:
	    {"clicks", "conversions": "exact"|"template_level"|"unavailable", "reason": str,
	     "values": {clicked, quick_reply_clicked, conversions}|None (only when exact),
	     "template_level": totals block|None}

	"exact" needs every sending day to have at least one row, with `sent` summed over that day's rows
	(product types) equal to ours (strict, no tolerance) and not unavailable in any of them, and, per
	metric, Meta support in EVERY included row (`clicks_supported` / `conversions_available`, metric
	not in `unavailable_fields`). Numbers are never scaled or prorated.
	"""
	days = sorted(d for d, count in broadcast_daily_sent.items() if count > 0)
	by_day = {d: _day_rows(template_daily.get(d)) for d in days}
	rows = [row for d in days for row in by_day[d]]
	if not days:
		return _attribution(ATTRIBUTION_UNAVAILABLE, ATTRIBUTION_UNAVAILABLE, _("No messages were sent yet."))
	if not rows:
		return _attribution(
			ATTRIBUTION_UNAVAILABLE, ATTRIBUTION_UNAVAILABLE, _("No Meta metrics synced for this template yet.")
		)
	missing = [d for d in days if not by_day[d]]
	template_level = _template_totals(rows, days, missing)
	active_rows = _active_metric_rows(rows)

	def _supported(flag: str, metric_names: tuple[str, ...]) -> bool:
		"""Check if a metric is supported and available across all active rows that carried traffic.

		Args:
			flag: boolean flag field name (e.g. 'clicks_supported', 'conversions_available').
			metric_names: tuple of metric names to check in unavailable_fields.

		Returns:
			True if supported in all active rows and not listed in unavailable_fields.
		"""
		return all(
			row.get(flag) and not set(metric_names) & set(_loads_list(row.get("unavailable_fields")))
			for row in active_rows
		)

	clicks_ok = _supported("clicks_supported", ("clicked",))
	conversions_ok = _supported("conversions_available", ())
	day_match = not missing and all(
		not any("sent" in _loads_list(row.get("unavailable_fields")) for row in by_day[d])
		and sum(row.get("sent") or 0 for row in by_day[d]) == broadcast_daily_sent[d]
		for d in days
	)
	exact = day_match and not block_reason
	if exact:
		reason = _("Meta's sent count matches this broadcast on every day it sent.")
	elif block_reason:
		reason = block_reason
	elif missing:
		reason = _("Meta metrics are missing for some days this broadcast sent.")
	else:
		reason = _("Meta's sent count differs from this broadcast's on at least one day (other sends share the template).")

	def _label(supported: bool) -> str:
		if not supported:
			return ATTRIBUTION_UNAVAILABLE
		return ATTRIBUTION_EXACT if exact else ATTRIBUTION_TEMPLATE_LEVEL

	result = _attribution(_label(clicks_ok), _label(conversions_ok), f"{reason} {day_note}" if day_note else reason)
	result["template_level"] = template_level
	if exact:
		clicks_exact = result["clicks"] == ATTRIBUTION_EXACT
		result["values"] = {
			"clicked": template_level["clicked"] if clicks_exact else None,
			"quick_reply_clicked": template_level["quick_reply_clicked"] if clicks_exact else None,
			"conversions": template_level["conversions"] if result["conversions"] == ATTRIBUTION_EXACT else None,
		}
	return result


def _attribution(clicks: str, conversions: str, reason: str) -> dict:
	"""Build the attribution result shell."""
	return {"clicks": clicks, "conversions": conversions, "reason": reason, "values": None, "template_level": None}


def _aggregate_status_rows(rows: list) -> dict:
	"""Fold grouped Channel Message rows of ONE broadcast into totals, breakdowns and last_status_at.

	`rows`: dicts with status, send_path, pricing_category, count and the MAX of read_at,
	delivered_at, sent_at, failed_at (any may be None). Read implies delivered,
	delivered implies sent; failed is separate and excluded from the success counts and breakdowns.
	"""
	by_status: dict[str, int] = defaultdict(int)
	send_path: dict[str, int] = defaultdict(int)
	pricing: dict[str, int] = defaultdict(int)
	last_at = None
	for row in rows:
		status = (row.get("status") or "").lower()
		count = row.get("count") or 0
		by_status[status] += count
		if status in _SENT_STATUSES:
			send_path[row.get("send_path") or UNKNOWN_KEY] += count
			pricing[row.get("pricing_category") or UNKNOWN_KEY] += count
		for stamp in (row.get(c) for c in _STATUS_TIME_COLUMNS):
			if stamp and (last_at is None or stamp > last_at):
				last_at = stamp
	read = by_status[MessageStatus.READ]
	delivered = read + by_status[MessageStatus.DELIVERED]
	sent = delivered + by_status[MessageStatus.SENT]
	return {
		"totals": {
			"queued": by_status[MessageStatus.QUEUED],
			"sent": sent,
			"delivered": delivered,
			"read": read,
			"failed": by_status[MessageStatus.FAILED],
		},
		"send_path_breakdown": dict(send_path),
		"pricing_category_breakdown": dict(pricing),
		"last_status_at": last_at,
	}


def _rates(totals: dict) -> dict:
	"""Delivery rate = delivered/sent; read rate = read/delivered. None on a 0 denominator."""
	return {
		"delivery": _rate(totals["delivered"], totals["sent"]),
		"read": _rate(totals["read"], totals["delivered"]),
	}


def summarize_status_counts(rows: list[dict]) -> dict:
	"""Summarize status counts and calculate delivery and read rates.

	Folds grouped Channel Message rows (or plain status-count dicts) using status
	implication rules (read implies delivered implies sent). Rates with a zero
	denominator are None.

	Args:
		rows: list of dicts with 'status' and 'count' (and optional breakdown/time fields).

	Returns:
		dict with:
			"totals": dict with counts for queued, sent, delivered, read, and failed.
			"rates": dict with "delivery" and "read" rates (float between 0 and 1, or None).
	"""
	agg = _aggregate_status_rows(rows)
	return {
		"totals": agg["totals"],
		"rates": _rates(agg["totals"]),
	}


def _to_waba_day(minute: str, system_tz: tzinfo, waba_tz: tzinfo) -> date:
	"""Convert a system-timezone 'YYYY-MM-DD HH:MM' bucket to its calendar day in the WABA timezone (any tzinfo)."""
	return datetime.strptime(minute, _MINUTE_PARSE).replace(tzinfo=system_tz).astimezone(waba_tz).date()


def _zone(name: str | None) -> ZoneInfo | None:
	"""Return the IANA zone for `name`, or None when blank/unrecognised (e.g. a numeric Meta id)."""
	try:
		return ZoneInfo(name) if name else None
	except (ZoneInfoNotFoundError, ValueError, OSError):
		return None


def _day_zone(iana_name: str | None, offset_minutes: int | None) -> tuple[tzinfo | None, bool]:
	"""Pick the zone used to bucket a broadcast's sends into days.

	Order: a valid IANA `waba_timezone`, else a fixed zone from the offset derived at sync time
	(0 is valid), else None (template-level fallback). Returns (zone, is_fixed_offset).
	Daylight saving: a fixed offset cannot follow DST, so sends within hours of a transition can
	land on the wrong day; callers must say so in the attribution reason.
	"""
	zone = _zone(iana_name)
	if zone is not None:
		return zone, False
	if offset_minutes is None:
		return None, False
	return timezone(timedelta(minutes=offset_minutes)), True


def _format_utc_offset(offset_minutes: int) -> str:
	"""Format minutes east of UTC as 'UTC+05:30' / 'UTC-03:30'."""
	hours, minutes = divmod(abs(offset_minutes), SECONDS_PER_MINUTE)
	return f"UTC{'-' if offset_minutes < 0 else '+'}{hours:02d}:{minutes:02d}"


# --------------------------------------------------------------------------- loaders (DB)


def _load_broadcasts(names: list[str]) -> list[dict]:
	"""Fetch name/title/template/account/recipient_count of the broadcasts (one query)."""
	return frappe.get_all(
		BULK_MESSAGE_DOCTYPE,
		filters={"name": ("in", names)},
		fields=["name", "title", "template", "whatsapp_account", "recipient_count", "campaign"],
		order_by="creation desc",
		limit=len(names),
	)


def _load_status_rows(names: list[str]) -> list[dict]:
	"""One grouped query over Channel Message for all broadcasts: counts per status/route/category.

	Args:
		names: list of Bulk WhatsApp Message document names.

	Returns:
		list of dicts containing status, send_path, pricing_category, count, and status timestamps,
		or [] immediately when names is empty.
	"""
	if not names:
		return []
	return frappe.db.sql(
		"""
		SELECT reference_name, status, send_path, pricing_category, COUNT(*) AS count,
			MAX(read_at) AS read_at, MAX(delivered_at) AS delivered_at, MAX(sent_at) AS sent_at,
			MAX(failed_at) AS failed_at
		FROM `tabChannel Message`
		WHERE reference_doctype = %(doctype)s AND reference_name IN %(names)s
		GROUP BY reference_name, status, send_path, pricing_category
		""",
		{"doctype": BULK_MESSAGE_DOCTYPE, "names": tuple(names)},
		as_dict=True,
	)


def _load_sent_minutes(names: list[str]) -> list[dict]:
	"""Sent-success message counts per broadcast per minute of `sent_at` (minute None = undated).

	Args:
		names: list of Bulk WhatsApp Message document names.

	Returns:
		list of dicts containing reference_name, minute, and count, or [] immediately when names is empty.
	"""
	if not names:
		return []
	return frappe.db.sql(
		f"""
		SELECT reference_name, DATE_FORMAT(sent_at, '{_MINUTE_FORMAT}') AS minute, COUNT(*) AS count
		FROM `tabChannel Message`
		WHERE reference_doctype = %(doctype)s AND reference_name IN %(names)s AND status IN %(statuses)s
		GROUP BY reference_name, minute
		""",  # noqa: S608 -- _MINUTE_FORMAT is a module constant
		{"doctype": BULK_MESSAGE_DOCTYPE, "names": tuple(names), "statuses": _SENT_STATUSES},
		as_dict=True,
	)


def _load_template_info(templates: list[str]) -> dict[str, dict]:
	"""Map WhatsApp Templates name -> {id (Meta template id), whatsapp_account}."""
	rows = frappe.get_all(
		"WhatsApp Templates",
		filters={"name": ("in", templates)},
		fields=["name", "id", "whatsapp_account"],
	)
	return {r.name: r for r in rows}


def _load_waba_timezones(accounts: list[str]) -> dict[str, str]:
	"""Map WhatsApp Account name -> stored `waba_timezone` (may be blank)."""
	rows = frappe.get_all(
		"WhatsApp Account",
		filters={"name": ("in", accounts)},
		fields=["name", "waba_timezone"],
	)
	return {r.name: r.waba_timezone for r in rows}


def _load_waba_utc_offsets(accounts: list[str]) -> dict[str, int]:
	"""Map WhatsApp Account name -> UTC offset minutes derived at sync time (only accounts with one).

	Empty on a site where the columns are not migrated yet. The synced-at stamp tells a derived 0
	(UTC) from the Int column's default 0.
	"""
	if not frappe.db.has_column("WhatsApp Account", WABA_UTC_OFFSET_FIELD):
		return {}
	rows = frappe.get_all(
		"WhatsApp Account",
		filters={"name": ("in", accounts)},
		fields=["name", WABA_UTC_OFFSET_FIELD, WABA_UTC_OFFSET_SYNCED_FIELD],
	)
	return {
		r.name: r[WABA_UTC_OFFSET_FIELD]
		for r in rows
		if r.get(WABA_UTC_OFFSET_SYNCED_FIELD) and r.get(WABA_UTC_OFFSET_FIELD) is not None
	}


def _load_metric_rows(accounts: list[str], template_ids: list[str], first_day: date, last_day: date) -> list[dict]:
	"""Marketing Metric rows (every product type) for the accounts/templates between the two days (one query)."""
	return frappe.get_all(
		METRIC_DOCTYPE,
		filters={
			"whatsapp_account": ("in", accounts),
			"template_id": ("in", template_ids),
			"metric_date": ("between", [first_day, last_day]),
		},
		fields=[
			"whatsapp_account",
			"template_id",
			"metric_date",
			*_COUNT_FIELDS,
			"amount_spent",
			"currency",
			"conversions",
			"unavailable_fields",
			"clicks_supported",
			"conversions_available",
		],
	)


# --------------------------------------------------------------------------- orchestration


def _compute(broadcasts: list[dict]) -> list[dict]:
	"""Compute the metrics dict of every broadcast with a constant number of queries.

	Args:
		broadcasts: list of dicts with broadcast information (at least 'name').

	Returns:
		list of computed broadcast metric dicts, or [] immediately when broadcasts or names is empty.
	"""
	if not broadcasts:
		return []
	names = [b["name"] for b in broadcasts if b.get("name")]
	if not names:
		return []
	status_by_name: dict[str, list] = defaultdict(list)
	for row in _load_status_rows(names):
		status_by_name[row["reference_name"]].append(row)
	minutes_by_name: dict[str, list] = defaultdict(list)
	for row in _load_sent_minutes(names):
		minutes_by_name[row["reference_name"]].append(row)

	templates = sorted({b["template"] for b in broadcasts if b.get("template")})
	template_info = _load_template_info(templates) if templates else {}
	account_of = {
		b["name"]: b.get("whatsapp_account") or (template_info.get(b.get("template")) or {}).get("whatsapp_account")
		for b in broadcasts
	}
	accounts = sorted({a for a in account_of.values() if a})
	timezones = _load_waba_timezones(accounts) if accounts else {}
	offsets = _load_waba_utc_offsets(accounts) if accounts else {}
	system_tz = ZoneInfo(get_system_timezone())

	# Day buckets per broadcast, in the WABA timezone: an IANA name, else the derived fixed offset.
	daily: dict[str, dict[date, int]] = {}
	block: dict[str, str | None] = {}
	day_note: dict[str, str | None] = {}
	for name in names:
		waba_tz, is_fixed = _day_zone(timezones.get(account_of[name]), offsets.get(account_of[name]))
		fallback_used = waba_tz is None
		day_note[name] = (
			_(
				"Days were derived from a fixed UTC offset ({0}) read from Meta's reports, so sends within hours "
				"of a daylight-saving change may fall on the wrong day."
			).format(_format_utc_offset(offsets[account_of[name]]))
			if is_fixed
			else None
		)
		tz = waba_tz or system_tz
		per_day: dict[date, int] = defaultdict(int)
		undated = 0
		for row in minutes_by_name.get(name, []):
			if row["minute"] is None:
				undated += row["count"]
			else:
				per_day[_to_waba_day(row["minute"], system_tz, tz)] += row["count"]
		daily[name] = per_day
		block[name] = (
			_("The WhatsApp account's time zone is not stored, so days cannot be matched exactly.")
			if fallback_used
			else _("Some sent messages have no sent time, so days cannot be matched exactly.")
			if undated
			else None
		)

	metric_index: dict[tuple, dict[date, list[dict]]] = defaultdict(lambda: defaultdict(list))
	days_all = [d for per_day in daily.values() for d in per_day]
	ids = sorted({t["id"] for t in template_info.values() if t.get("id")})
	if days_all and ids and accounts:
		for row in _load_metric_rows(accounts, ids, min(days_all), max(days_all)):
			metric_index[(row["whatsapp_account"], row["template_id"])][row["metric_date"]].append(row)

	results = []
	for b in broadcasts:
		name = b["name"]
		metrics = _aggregate_status_rows(status_by_name.get(name, []))
		metrics["totals"]["recipients"] = b.get("recipient_count") or 0
		metrics["rates"] = _rates(metrics["totals"])
		meta_id = (template_info.get(b.get("template")) or {}).get("id")
		if not meta_id:
			attribution = _attribution(
				ATTRIBUTION_UNAVAILABLE, ATTRIBUTION_UNAVAILABLE, _("This template has no Meta template id.")
			)
		else:
			attribution = _resolve_attribution(
				daily[name], metric_index.get((account_of[name], meta_id), {}), block[name], day_note[name]
			)
		template_level = attribution.pop("template_level")
		results.append(
			{
				"name": name,
				"title": b.get("title"),
				"template": b.get("template"),
				**metrics,
				"template_level": template_level,
				"attribution": attribution,
			}
		)
	return results


def get_broadcast_metrics(bulk_message: str) -> dict:
	"""Metrics for one Bulk WhatsApp Message.

	Args:
	    bulk_message: name of the broadcast. Permission is NOT checked here (see the endpoint).

	Returns:
	    {name, title, template, totals{recipients,queued,sent,delivered,read,failed},
	     rates{delivery,read}, send_path_breakdown, pricing_category_breakdown, last_status_at,
	     template_level (block|None), attribution{clicks,conversions,reason,values}}

	Raises:
	    frappe.DoesNotExistError: unknown broadcast name.
	"""
	broadcasts = _load_broadcasts([bulk_message])
	if not broadcasts:
		frappe.throw(_("Bulk WhatsApp Message {0} not found").format(bulk_message), frappe.DoesNotExistError)
	return _compute(broadcasts)[0]


def get_campaign_metrics(campaign: str) -> dict:
	"""Metrics summed over the Bulk WhatsApp Messages of a campaign.

	Reads at most MM_BROADCAST_ROWS_LIMIT broadcasts the caller may read (`truncated` is True when
	more exist). Attribution is evaluated per broadcast; the campaign label is the weakest one.
	Template-level blocks stay on each entry of `broadcasts` (summing them would double count a
	template shared by several broadcasts).

	Returns:
	    {campaign, broadcast_count, truncated, totals, rates, send_path_breakdown,
	     pricing_category_breakdown, last_status_at, attribution{clicks,conversions,reason},
	     broadcasts: [get_broadcast_metrics-shaped dicts]}
	"""
	rows = frappe.get_list(
		BULK_MESSAGE_DOCTYPE,
		filters={"campaign": campaign},
		fields=["name"],
		order_by="creation desc",
		limit=MM_BROADCAST_ROWS_LIMIT + 1,
	)
	truncated = len(rows) > MM_BROADCAST_ROWS_LIMIT
	names = [r.name for r in rows[:MM_BROADCAST_ROWS_LIMIT]]
	per_broadcast = _compute(_load_broadcasts(names)) if names else []

	totals = {k: sum(m["totals"][k] for m in per_broadcast) for k in ("recipients", "queued", "sent", "delivered", "read", "failed")}
	breakdowns = {}
	for key in ("send_path_breakdown", "pricing_category_breakdown"):
		merged: dict[str, int] = defaultdict(int)
		for m in per_broadcast:
			for label, count in m[key].items():
				merged[label] += count
		breakdowns[key] = dict(merged)
	times = [m["last_status_at"] for m in per_broadcast if m["last_status_at"]]
	if per_broadcast:
		attribution = {
			metric: min((m["attribution"][metric] for m in per_broadcast), key=_ATTRIBUTION_STRENGTH.get)
			for metric in ("clicks", "conversions")
		}
		attribution["reason"] = _("Weakest label across the campaign's broadcasts; see each broadcast for its reason.")
	else:
		attribution = _attribution(ATTRIBUTION_UNAVAILABLE, ATTRIBUTION_UNAVAILABLE, _("This campaign has no broadcasts."))
		del attribution["values"], attribution["template_level"]
	return {
		"campaign": campaign,
		"broadcast_count": len(per_broadcast),
		"truncated": truncated,
		"totals": totals,
		"rates": _rates(totals),
		**breakdowns,
		"last_status_at": max(times) if times else None,
		"attribution": attribution,
		"broadcasts": per_broadcast,
	}
