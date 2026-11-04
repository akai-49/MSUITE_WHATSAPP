"""
WhatsApp Analytics sync — polls Meta's analytics APIs and stores snapshots.

Called by scheduler (every 6h for messaging/conversation/pricing/call,
daily for template analytics + cleanup).

Each sync function:
  1. Builds the Meta API query with proper parameters
  2. Calls the API using the WABA-level system user token
  3. Stores the response in a WhatsApp Analytics Snapshot record
  4. Keeps last N snapshots per key (configurable retention)

Rate limits: 2-second delay between accounts to avoid Meta 429s.
Re-fetch window: always syncs last 7 days to catch retroactive updates.
"""

import json
import time
from datetime import datetime, timedelta

import frappe
import requests
from frappe import _
from frappe.utils import add_days, getdate, now, today

from msuite_core.constants import (
	GRAPH_API_URL,
	GRAPH_API_VERSION,
	HTTP_STATUS_FORBIDDEN,
	HTTP_STATUS_UNAUTHORIZED,
	LOGGER_NAME,
)
from msuite_whatsapp.constants import (
	ANALYTICS_INTER_ACCOUNT_DELAY,
	ANALYTICS_REFETCH_DAYS,
	ANALYTICS_SNAPSHOT_RETENTION,
	HTTP_STATUS_BAD_REQUEST,
	META_ANALYTICS_HTTP_TIMEOUT,
	META_PERMISSION_ERROR_CODE_RANGE,
	META_PERMISSION_ERROR_CODES,
	META_TOKEN_ERROR_CODES,
	TEMPLATE_ANALYTICS_BATCH_SIZE,
	TEMPLATE_ANALYTICS_DEFAULT_DAYS,
	TEMPLATE_ANALYTICS_MAX_LOOKBACK_DAYS,
	TEMPLATE_ANALYTICS_MIN_DAYS,
	AnalyticsGranularity,
	MetricType,
)
from msuite_core.services.plans.plan_enforcer import check_feature_or_throw, is_feature_enabled
from msuite_core.services.permissions.checks import check_read
from msuite_whatsapp.queries.account_repository import set_reauth_flag

logger = frappe.logger(LOGGER_NAME)


# ═══════════════════════════════════════════════════════════════════════
# Scheduler entry points
# ═══════════════════════════════════════════════════════════════════════


def sync_all_accounts():
	"""
	Scheduler: sync messaging, conversation, pricing, and call analytics
	for all active WhatsApp Accounts. Runs every 6 hours.
	"""
	if not is_feature_enabled("analytics"):
		return

	accounts = _get_active_accounts()
	for i, account in enumerate(accounts):
		if i > 0:
			time.sleep(ANALYTICS_INTER_ACCOUNT_DELAY)
		try:
			sync_all(account.name)
		except Exception as e:
			logger.error(f"Analytics sync failed for {account.name}: {e}")


def sync_daily_tasks():
	"""
	Scheduler: daily tasks — template analytics sync + old snapshot cleanup.
	Cleanup runs AFTER template sync (order matters).
	"""
	if not is_feature_enabled("analytics"):
		return

	from msuite_whatsapp.services.analytics import mm_sync  # lazy: mm_sync imports this module

	# 1. Template analytics for all accounts
	accounts = _get_active_accounts()
	for i, account in enumerate(accounts):
		if i > 0:
			time.sleep(ANALYTICS_INTER_ACCOUNT_DELAY)
		try:
			sync_template_analytics(account.name)
			mm_sync.sync_marketing_metrics(account.name)
		except Exception as e:
			logger.error(f"Template analytics sync failed for {account.name}: {e}")

	# 2. Cleanup old snapshots and Marketing Messages metrics (after template sync, not before)
	cleanup_old_snapshots()
	try:
		mm_sync.prune_old_marketing_metrics()
	except Exception as e:
		logger.error(f"Marketing metrics prune failed: {e}")


def refresh_campaign(campaign_name: str) -> dict:
	"""On-demand WhatsApp refresh for one umbrella Campaign.

	Pulls fresh WABA analytics for every distinct account behind the
	campaign's Bulk WhatsApp Message broadcasts (1:N via `Bulk WhatsApp
	Message.campaign`). Return shape mirrors the Ads + Social refresh
	entry points so the dashboard can render a unified outcome.

	No-op (with a clean result) when the campaign has no WhatsApp
	broadcasts attached — the marketer hasn't opted into the channel.
	"""
	if not frappe.has_permission("Marketing Campaign", "read", doc=campaign_name):
		frappe.throw("Not permitted to refresh insights for this Campaign", frappe.PermissionError)

	blasts = frappe.get_all(
		"Bulk WhatsApp Message",
		filters={"campaign": campaign_name},
		fields=["whatsapp_account"],
	)
	accounts = sorted({b.whatsapp_account for b in blasts if b.whatsapp_account})
	if not accounts:
		return {"refreshed_accounts": 0, "errors": []}

	refreshed, errors = 0, []
	for account_name in accounts:
		try:
			sync_all(account_name)
			refreshed += 1
		except Exception as e:
			errors.append({"scope": "account", "name": account_name, "error": str(e)[:200]})

	return {"refreshed_accounts": refreshed, "errors": errors}


def refresh_account_analytics(account_name: str) -> dict:
	"""On-demand refresh for a single WhatsApp Account."""
	check_read("WhatsApp Account", account_name)
	check_read("WhatsApp Analytics Snapshot")
	check_feature_or_throw("analytics")
	from msuite_whatsapp.services.analytics import mm_sync  # lazy: mm_sync imports this module

	try:
		sync_all(account_name)
		sync_template_analytics(account_name)
		mm_sync.sync_marketing_metrics(account_name)
		return {"status": "success", "account": account_name}
	except Exception as e:
		frappe.log_error("refresh_account_analytics", str(e))
		return {"status": "error", "message": str(e)}


def sync_all(account_name: str, days: int | None = None):
	"""
	Sync all non-template analytics for one account.
	Template analytics is handled by sync_daily_tasks (daily granularity only).

	Args:
	    account_name: WhatsApp Account document name
	    days: Override refetch window (default: ANALYTICS_REFETCH_DAYS)
	"""
	days = days or ANALYTICS_REFETCH_DAYS
	sync_messaging_analytics(account_name, days)
	sync_conversation_analytics(account_name, days)
	sync_pricing_analytics(account_name, days)
	sync_call_analytics(account_name, days)


# ═══════════════════════════════════════════════════════════════════════
# Individual metric sync functions
# ═══════════════════════════════════════════════════════════════════════


def sync_messaging_analytics(account_name: str, days: int = ANALYTICS_REFETCH_DAYS):
	"""
	Source: Meta API — GET /{waba_id}?fields=analytics
	Fetches sent/delivered counts by day.
	"""
	account = frappe.get_doc("WhatsApp Account", account_name)
	waba_id, token = _get_waba_credentials(account)
	start_ts, end_ts, start_date, end_date = _get_period(days)

	params = {
		"fields": f"analytics.start({start_ts}).end({end_ts}).granularity(DAY)",
		"access_token": token,
	}

	data = _call_meta_api(f"{GRAPH_API_URL}/{GRAPH_API_VERSION}/{waba_id}", params, account_name)
	if data:
		_save_snapshot(
			account_name, MetricType.MESSAGING, start_date, end_date, AnalyticsGranularity.DAY, data
		)


def sync_conversation_analytics(account_name: str, days: int = ANALYTICS_REFETCH_DAYS):
	"""
	Source: Meta API — GET /{waba_id}?fields=conversation_analytics
	Fetches conversation volume + cost by category. Uses DAILY granularity
	(not HALF_HOUR — heavy query with multiple dimensions).
	"""
	account = frappe.get_doc("WhatsApp Account", account_name)
	waba_id, token = _get_waba_credentials(account)
	start_ts, end_ts, start_date, end_date = _get_period(days)

	params = {
		"fields": (
			f"conversation_analytics"
			f".start({start_ts}).end({end_ts}).granularity(DAILY)"
			f'.metric_types(["CONVERSATION","COST"])'
			f'.conversation_categories(["MARKETING","UTILITY","AUTHENTICATION","SERVICE"])'
			f'.dimensions(["CONVERSATION_CATEGORY"])'
		),
		"access_token": token,
	}

	data = _call_meta_api(f"{GRAPH_API_URL}/{GRAPH_API_VERSION}/{waba_id}", params, account_name)
	if data:
		_save_snapshot(
			account_name, MetricType.CONVERSATION, start_date, end_date, AnalyticsGranularity.DAY, data
		)


def sync_pricing_analytics(account_name: str, days: int = ANALYTICS_REFETCH_DAYS):
	"""
	Source: Meta API — GET /{waba_id}?fields=pricing_analytics
	Fetches cost breakdown by category and country.
	"""
	account = frappe.get_doc("WhatsApp Account", account_name)
	waba_id, token = _get_waba_credentials(account)
	start_ts, end_ts, start_date, end_date = _get_period(days)

	params = {
		"fields": (
			f"pricing_analytics"
			f".start({start_ts}).end({end_ts}).granularity(DAILY)"
			f'.metric_types(["COST","VOLUME"])'
			f'.pricing_categories(["MARKETING","UTILITY","AUTHENTICATION","SERVICE"])'
			f'.dimensions(["PRICING_CATEGORY","COUNTRY"])'
		),
		"access_token": token,
	}

	data = _call_meta_api(f"{GRAPH_API_URL}/{GRAPH_API_VERSION}/{waba_id}", params, account_name)
	if data:
		_save_snapshot(account_name, MetricType.PRICING, start_date, end_date, AnalyticsGranularity.DAY, data)


def sync_template_analytics(account_name: str, days: int = TEMPLATE_ANALYTICS_DEFAULT_DAYS):
	"""
	Source: Meta API — GET /{waba_id}/template_analytics
	Fetches per-template sent/delivered/read/clicked metrics.

	Handles:
	  - Insights enable check (one-time POST to Meta, irreversible)
	  - Pagination (max 10 templates per request)
	  - Look-back clamped to [TEMPLATE_ANALYTICS_MIN_DAYS, TEMPLATE_ANALYTICS_MAX_LOOKBACK_DAYS]
	  - Token sent in the Authorization header; a 401 / token error flags the
	    account for re-auth and stops the remaining batches
	"""
	account = frappe.get_doc("WhatsApp Account", account_name)
	waba_id, token = _get_waba_credentials(account)

	# Enable insights if not already done (one-time, irreversible)
	if not account.is_enabled_for_insights:
		_enable_insights(waba_id, token)
		frappe.db.set_value("WhatsApp Account", account_name, "is_enabled_for_insights", 1)

	# Get all template IDs for this account
	template_ids = frappe.get_all(
		"WhatsApp Templates",
		filters={"whatsapp_account": account_name, "id": ["is", "set"]},
		pluck="id",
	)
	if not template_ids:
		return

	# Chunk into batches of 10 (Meta limit)
	end_date = today()
	days = max(TEMPLATE_ANALYTICS_MIN_DAYS, min(days, TEMPLATE_ANALYTICS_MAX_LOOKBACK_DAYS))
	start_date = str(add_days(getdate(end_date), -days))

	all_data = []
	for i in range(0, len(template_ids), TEMPLATE_ANALYTICS_BATCH_SIZE):
		batch = template_ids[i : i + TEMPLATE_ANALYTICS_BATCH_SIZE]
		ids_param = ",".join(f'"{tid}"' for tid in batch)

		result, err = _call_meta_api_with_error(
			f"{GRAPH_API_URL}/{GRAPH_API_VERSION}/{waba_id}/template_analytics",
			{
				"start": start_date,
				"end": end_date,
				"granularity": "DAILY",
				"template_ids": f"[{ids_param}]",
				"metric_types": '["SENT","DELIVERED","READ","CLICKED","COST"]',
				"use_waba_timezone": "true",
				"access_token": token,
			},
			account_name,
		)
		if err and _is_token_error(err):
			break  # token is dead; further batches would fail the same way
		if result and "data" in result:
			all_data.extend(result["data"])

	if all_data:
		_save_snapshot(
			account_name,
			MetricType.TEMPLATE,
			start_date,
			end_date,
			AnalyticsGranularity.DAY,
			{"data": all_data},
		)


def sync_call_analytics(account_name: str, days: int = ANALYTICS_REFETCH_DAYS):
	"""
	Source: Meta API — GET /{waba_id}?fields=call_analytics
	Fetches call count, cost, and average duration.
	"""
	account = frappe.get_doc("WhatsApp Account", account_name)
	waba_id, token = _get_waba_credentials(account)
	start_ts, end_ts, start_date, end_date = _get_period(days)

	params = {
		"fields": (
			f"call_analytics"
			f".start({start_ts}).end({end_ts}).granularity(DAILY)"
			f'.metric_types(["COUNT","COST","AVERAGE_DURATION"])'
			f'.dimensions(["direction"])'
		),
		"access_token": token,
	}

	data = _call_meta_api(f"{GRAPH_API_URL}/{GRAPH_API_VERSION}/{waba_id}", params, account_name)
	if data:
		_save_snapshot(account_name, MetricType.CALL, start_date, end_date, AnalyticsGranularity.DAY, data)


# ═══════════════════════════════════════════════════════════════════════
# Cleanup
# ═══════════════════════════════════════════════════════════════════════


def cleanup_old_snapshots():
	"""
	Remove snapshots beyond the retention limit per unique key.
	Keeps the most recent N snapshots for each
	(account + metric_type + period_start + period_end + granularity).
	"""
	# Get all unique keys
	keys = frappe.db.sql(
		"""
        SELECT whatsapp_account, metric_type, period_start, period_end, granularity,
               COUNT(*) as cnt
        FROM `tabWhatsApp Analytics Snapshot`
        GROUP BY whatsapp_account, metric_type, period_start, period_end, granularity
        HAVING cnt > %s
    """,
		ANALYTICS_SNAPSHOT_RETENTION,
		as_dict=True,
	)

	for key in keys:
		# Get oldest snapshots beyond retention
		old = frappe.db.sql(
			"""
            SELECT name FROM `tabWhatsApp Analytics Snapshot`
            WHERE whatsapp_account = %s AND metric_type = %s
              AND period_start = %s AND period_end = %s AND granularity = %s
            ORDER BY synced_at DESC
            LIMIT 999 OFFSET %s
        """,
			(
				key.whatsapp_account,
				key.metric_type,
				key.period_start,
				key.period_end,
				key.granularity,
				ANALYTICS_SNAPSHOT_RETENTION,
			),
			as_dict=True,
		)

		for row in old:
			frappe.delete_doc("WhatsApp Analytics Snapshot", row.name, force=True)

	frappe.db.commit()


# ═══════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════


def _get_active_accounts():
	"""Get all active WhatsApp Accounts with a WABA ID."""
	return frappe.get_all(
		"WhatsApp Account",
		filters={"status": "Active", "waba_id": ["is", "set"]},
		fields=["name"],
	)


def _get_waba_credentials(account):
	"""Extract WABA ID and token from a WhatsApp Account document."""
	waba_id = account.waba_id or account.business_id
	token = account.get_password("token")
	if not waba_id or not token:
		frappe.throw(_("WhatsApp Account {0} missing WABA ID or token.").format(account.name))
	return waba_id, token


def _get_period(days: int):
	"""
	Calculate time period for analytics query.

	Returns:
	    (start_unix, end_unix, start_date_str, end_date_str)
	"""
	end = datetime.now()
	start = end - timedelta(days=days)
	start_ts = int(start.timestamp())
	end_ts = int(end.timestamp())
	return start_ts, end_ts, str(start.date()), str(end.date())


def _is_token_error(err: dict) -> bool:
	"""True when a Meta error dict means the access token is invalid/expired (HTTP 401 or Graph token code)."""
	return err.get("status_code") == HTTP_STATUS_UNAUTHORIZED or err.get("code") in META_TOKEN_ERROR_CODES


def _is_permission_error(err: dict) -> bool:
	"""True when a Meta error dict means a missing permission (HTTP 403 or Graph permission code)."""
	code = err.get("code")
	return (
		err.get("status_code") == HTTP_STATUS_FORBIDDEN
		or code in META_PERMISSION_ERROR_CODES
		or code in META_PERMISSION_ERROR_CODE_RANGE
	)


def _call_meta_api_with_error(
	url: str, params: dict, account_name: str | None = None
) -> tuple[dict | None, dict | None]:
	"""GET a Meta Graph endpoint and return (body, error).

	The `access_token` in `params` (the caller's dict is not mutated) is sent as an
	`Authorization: Bearer` header, so it never appears in the URL or in logs.
	On a token error (HTTP 401 or Graph code 190/102) the account is flagged for
	re-auth when `account_name` is given. A permission error (403 / code 10 / 200-299)
	is logged once and never flags re-auth.

	Returns:
	    (body, None) on success, else (None, {"message", "status_code", "code", "exception"?}).
	Side effects: HTTP GET; may write the account's needs_reauth fields. Never raises.
	"""
	params = dict(params)
	token = params.pop("access_token", None)
	headers = {"Authorization": f"Bearer {token}"} if token else {}

	def _scrub(text) -> str:
		return str(text).replace(token, "***") if token else str(text)

	try:
		resp = requests.get(url, params=params, headers=headers, timeout=META_ANALYTICS_HTTP_TIMEOUT)
		status = getattr(resp, "status_code", None)
		try:
			data = resp.json()
		except ValueError:
			data = None
		if isinstance(data, dict) and "error" not in data and not (
			isinstance(status, int) and status >= HTTP_STATUS_BAD_REQUEST
		):
			return data, None

		raw = data.get("error") if isinstance(data, dict) else None
		raw = raw if isinstance(raw, dict) else {}
		err = {
			"message": _scrub(raw.get("message") or f"HTTP {status}"),
			"status_code": status,
			"code": raw.get("code"),
		}
		if not isinstance(data, dict) and not (isinstance(status, int) and status >= HTTP_STATUS_BAD_REQUEST):
			err["message"] = "Non-JSON response from Meta"
	except Exception as e:
		logger.error(f"Meta analytics API call failed: {_scrub(e)}")
		return None, {"message": _scrub(e), "exception": True}

	if _is_token_error(err):
		logger.warning(f"Meta analytics token error: {err['message']}")
		if account_name:
			set_reauth_flag(account_name, needs_reauth=True, error=err["message"])
	elif _is_permission_error(err):
		logger.warning(f"Meta analytics permission error: {err['message']}")
	else:
		logger.warning(f"Meta analytics API error: {err['message']}")
	return None, err


def _call_meta_api(url: str, params: dict, account_name: str | None = None) -> dict | None:
	"""Call Meta Graph API and return JSON response, or None on any error.

	Thin wrapper over `_call_meta_api_with_error` (header auth, re-auth flagging).
	"""
	data, _err = _call_meta_api_with_error(url, params, account_name)
	return data


def _save_snapshot(
	account_name: str, metric_type: str, period_start: str, period_end: str, granularity: str, data: dict
):
	"""Create a new WhatsApp Analytics Snapshot record."""
	doc = frappe.new_doc("WhatsApp Analytics Snapshot")
	doc.whatsapp_account = account_name
	doc.metric_type = metric_type
	doc.period_start = period_start
	doc.period_end = period_end
	doc.granularity = granularity
	doc.raw_data = json.dumps(data, indent=2)
	doc.synced_at = now()
	doc.insert(ignore_permissions=True)
	frappe.db.commit()


def _enable_insights(waba_id: str, token: str):
	"""
	Enable template analytics on a WABA (one-time, irreversible on Meta).
	POST /{waba_id}?is_enabled_for_insights=true
	"""
	try:
		resp = requests.post(
			f"{GRAPH_API_URL}/{GRAPH_API_VERSION}/{waba_id}",
			params={"is_enabled_for_insights": "true"},
			headers={"Authorization": f"Bearer {token}"},
			timeout=META_ANALYTICS_HTTP_TIMEOUT,
		)
		result = resp.json()
		if result.get("success"):
			logger.info(f"Enabled insights for WABA {waba_id}")
		else:
			logger.warning(f"Failed to enable insights for WABA {waba_id}: {result}")
	except Exception as e:
		logger.error(f"Failed to enable insights for WABA {waba_id}: {e}")
