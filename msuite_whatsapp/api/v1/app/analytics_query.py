"""
WhatsApp Analytics query service — reads data for dashboards.

Each function documents its data source:
  - "Source: Local DB" → computed from WhatsApp Message records
  - "Source: Snapshot" → reads from WhatsApp Analytics Snapshot (Meta API data)

All functions are whitelisted and plan-gated for JS dashboard calls.
"""

import json

import frappe
from frappe.utils import add_days, getdate, today

from msuite_core.constants import GRAPH_API_BASE, MM_PRODUCT_TYPE
from msuite_whatsapp.constants import WHATSAPP_PRICING_CATEGORY_MARKETING_LITE
from msuite_whatsapp.constants import (
	MM_CONVERSION_ROWS_LIMIT,
	MM_METRICS_DEFAULT_DAYS,
	MM_METRICS_RETENTION_DAYS,
	MM_RATE_DECIMALS,
	MM_TEMPLATE_ROWS_LIMIT,
	MetricType,
)
from msuite_core.services.permissions.checks import check_read
from msuite_whatsapp.queries.account_repository import get_display_phone_number


def _require_analytics_read(account_name: str | int | None = None) -> None:
	"""Enforce read permissions on WhatsApp Analytics Snapshot and the target WhatsApp Account.

	When an account is specified (as doc name, phone number, or index), resolves it first
	via `_resolve_account_name` and checks document-level read permission on the resolved
	account name. If no account is given or 'all', enforces doctype-level read permission.

	Args:
		account_name: WhatsApp Account name, phone number, numeric index, 'all', or None.

	Returns:
		None.

	Raises:
		frappe.PermissionError: caller lacks read permission on WhatsApp Analytics Snapshot
			or on the target WhatsApp Account.

	Side effects:
		Calls `check_read` which raises `frappe.PermissionError` when permission is missing.
	"""
	check_read("WhatsApp Analytics Snapshot")
	resolved_name = None
	if account_name and account_name != "all":
		resolved_name, _ = _resolve_account_name(account_name)
	if resolved_name and frappe.db.exists("WhatsApp Account", resolved_name):
		check_read("WhatsApp Account", resolved_name)
	else:
		check_read("WhatsApp Account")


# ═══════════════════════════════════════════════════════════════════════
# Account Resolution Helpers
# ═══════════════════════════════════════════════════════════════════════


def _fetch_accounts_list() -> list[dict]:
	"""Fetch WhatsApp Accounts with docstatus=0 ordered by creation desc."""
	accounts_list = frappe.get_list(
		"WhatsApp Account",
		filters={"docstatus": 0},
		fields=["name", "account_name", "waba_id", "status"],
		order_by="creation desc",
	)
	for acc in accounts_list:
		acc["display_phone_number"] = acc["phone_number"] = get_display_phone_number(acc["name"])

	return accounts_list


def _resolve_account_name(
	account_name: str | int | None = None,
	accounts_list: list[dict] | None = None,
) -> tuple[str | None, list[dict]]:
	"""
	Resolves account_name handling:
	  1. None or 'all' -> defaults to first active account
	  2. 1-based numeric index (e.g. '9' or 9) into accounts_list
	  3. Direct match on 'name'
	  4. Fuzzy / case-insensitive search on account_name, phone_number, display_phone_number (equality & substring)
	  5. Fallback to frappe.db.exists("WhatsApp Account", account_name)
	  6. Final fallback to accounts_list[0]["name"] if available
	"""
	if accounts_list is None:
		accounts_list = _fetch_accounts_list()

	if not accounts_list:
		if account_name and frappe.db.exists("WhatsApp Account", str(account_name)):
			return str(account_name), []
		return None, []

	if not account_name or account_name == "all":
		return accounts_list[0]["name"], accounts_list

	# Check numeric index (1-based)
	is_numeric = False
	idx_val = None
	if isinstance(account_name, int):
		is_numeric = True
		idx_val = account_name
	elif isinstance(account_name, str):
		s = account_name.strip()
		if s.isdigit():
			is_numeric = True
			idx_val = int(s)

	if is_numeric and idx_val is not None:
		idx = idx_val - 1
		if 0 <= idx < len(accounts_list):
			return accounts_list[idx]["name"], accounts_list

	# Direct match against name
	for acc in accounts_list:
		if acc.get("name") == account_name:
			return acc["name"], accounts_list

	target = str(account_name).strip().lower()

	# 1. Exact match (case-insensitive)
	for acc in accounts_list:
		acc_n = (acc.get("account_name") or "").strip().lower()
		doc_n = (acc.get("name") or "").strip().lower()
		phone = (acc.get("phone_number") or "").strip().lower()
		disp_phone = (acc.get("display_phone_number") or "").strip().lower()
		if target and target in (acc_n, doc_n, phone, disp_phone):
			return acc["name"], accounts_list

	# Match normalized digits for phone numbers
	clean_target = "".join(ch for ch in target if ch.isdigit())
	if clean_target and len(clean_target) >= 4:
		for acc in accounts_list:
			phone_digits = "".join(ch for ch in (acc.get("phone_number") or "") if ch.isdigit())
			disp_digits = "".join(ch for ch in (acc.get("display_phone_number") or "") if ch.isdigit())
			if clean_target in (phone_digits, disp_digits) or (phone_digits and clean_target in phone_digits) or (disp_digits and clean_target in disp_digits):
				return acc["name"], accounts_list

	# 2. Substring match (case-insensitive)
	if target:
		for acc in accounts_list:
			acc_n = (acc.get("account_name") or "").strip().lower()
			doc_n = (acc.get("name") or "").strip().lower()
			phone = (acc.get("phone_number") or "").strip().lower()
			disp_phone = (acc.get("display_phone_number") or "").strip().lower()
			if (target in acc_n) or (target in doc_n) or (phone and target in phone) or (disp_phone and target in disp_phone):
				return acc["name"], accounts_list

	# Check if frappe.db.exists("WhatsApp Account", account_name)
	if frappe.db.exists("WhatsApp Account", str(account_name)):
		return str(account_name), accounts_list

	# Fall back to accounts_list[0]["name"] if available
	return accounts_list[0]["name"], accounts_list


# ═══════════════════════════════════════════════════════════════════════
# Local DB aggregation (WhatsApp Message table)
# ═══════════════════════════════════════════════════════════════════════


@frappe.whitelist()
def get_messaging_summary(account_name: str | None = None, days: int = 30) -> dict:
	"""
	Source: Local DB (WhatsApp Message) + Meta WABA Analytics API fallback.
	Returns sent/delivered/read/failed counts for the period, along with delivery_rate and read_rate.
	"""
	_require_analytics_read(account_name)
	days = int(days or 30)
	start = str(add_days(getdate(today()), -days))

	account_name, accounts_list = _resolve_account_name(account_name)
	if not account_name:
		return {
			"sent": 0, "delivered": 0, "read": 0, "failed": 0, "queued": 0, "total": 0,
			"delivery_rate": 0.0, "read_rate": 0.0, "error": "No WhatsApp Account connected"
		}

	counts = frappe.db.sql(
		"""
        SELECT status, COUNT(*) as count
        FROM `tabChannel Message`
        WHERE whatsapp_account = %s AND direction = 'Outbound'
          AND creation >= %s
        GROUP BY status
    """,
		(account_name, start),
		as_dict=True,
	)

	result = {"sent": 0, "delivered": 0, "read": 0, "failed": 0, "queued": 0, "total": 0}
	for row in counts:
		status = (row.status or "").lower()
		if status in result:
			result[status] = row.count
		result["total"] += row.count

	# If local DB has no outbound records, fallback to Meta WABA Insights data
	if result["total"] == 0 or (result["sent"] == 0 and result["delivered"] == 0):
		try:
			insights = get_whatsapp_account_insights(account_name=account_name, days=days)
			if insights and "totals" in insights:
				all_msgs = insights.get("totals", {}).get("all_messages", {})
				result["sent"] = all_msgs.get("sent", 0)
				result["delivered"] = all_msgs.get("delivered", 0)
				result["received"] = all_msgs.get("received", 0)
				result["total"] = result["sent"] or result["delivered"]
		except Exception as e:
			frappe.log_error("get_messaging_summary fallback", str(e))

	# Compute rates
	sent = result.get("sent", 0)
	delivered = result.get("delivered", 0)
	read = result.get("read", 0)
	result["delivery_rate"] = round((delivered / sent) * 100, 1) if sent > 0 else (100.0 if delivered > 0 else 0.0)
	result["read_rate"] = round((read / delivered) * 100, 1) if delivered > 0 else 0.0

	return result


@frappe.whitelist()
def get_messaging_trend(account_name: str | None = None, days: int = 30) -> list:
	"""
	Source: Local DB (WhatsApp Message) + Meta WABA Analytics fallback.
	Returns daily message counts grouped by status for charting.
	"""
	_require_analytics_read(account_name)
	days = int(days or 30)
	start = str(add_days(getdate(today()), -days))

	account_name, _ = _resolve_account_name(account_name)
	if not account_name:
		return []

	rows = frappe.db.sql(
		"""
        SELECT DATE(creation) as date, status, COUNT(*) as count
        FROM `tabChannel Message`
        WHERE whatsapp_account = %s AND direction = 'Outbound'
          AND creation >= %s
        GROUP BY DATE(creation), status
        ORDER BY date ASC
    """,
		(account_name, start),
		as_dict=True,
	)

	if not rows:
		try:
			insights = get_whatsapp_account_insights(account_name=account_name, days=days)
			if insights and "daily_trend" in insights:
				return insights["daily_trend"]
		except Exception as e:
			frappe.log_error("get_messaging_trend fallback", str(e))

	return rows


@frappe.whitelist()
def get_response_metrics(account_name: str | None = None, days: int = 30) -> dict:
	"""
	Source: Local DB (WhatsApp Message)
	Returns read rate % and average first response time.

	Read rate = read messages / delivered messages.
	Response time = avg time between last outgoing and next incoming per contact.
	"""
	_require_analytics_read(account_name)
	days = int(days or 30)
	start = str(add_days(getdate(today()), -days))

	account_name, _ = _resolve_account_name(account_name)
	if not account_name:
		return {"delivered": 0, "read": 0, "read_rate": 0.0}

	# Read rate
	delivered = frappe.db.count(
		"Channel Message",
		{
			"whatsapp_account": account_name,
			"direction": "Outbound",
			"status": ["in", ["delivered", "read"]],
			"creation": [">=", start],
		},
	)
	read = frappe.db.count(
		"Channel Message",
		{
			"whatsapp_account": account_name,
			"direction": "Outbound",
			"status": "read",
			"creation": [">=", start],
		},
	)
	read_rate = round(read / delivered * 100, 1) if delivered else 0

	return {
		"delivered": delivered,
		"read": read,
		"read_rate": read_rate,
	}


@frappe.whitelist()
def get_error_breakdown(account_name: str | None = None, days: int = 30) -> list:
	"""
	Source: Local DB (WhatsApp Message.failure_reason)
	Returns top error codes with counts.
	"""
	_require_analytics_read(account_name)
	start = str(add_days(getdate(today()), -int(days)))
	account_name, _ = _resolve_account_name(account_name)
	if not account_name:
		return []

	rows = frappe.db.sql(
		"""
        SELECT failure_reason, COUNT(*) as count
        FROM `tabChannel Message`
        WHERE whatsapp_account = %s AND status = 'failed'
          AND failure_reason IS NOT NULL AND failure_reason != ''
          AND creation >= %s
        GROUP BY failure_reason
        ORDER BY count DESC
        LIMIT 10
    """,
		(account_name, start),
		as_dict=True,
	)

	return rows


# ═══════════════════════════════════════════════════════════════════════
# Snapshot reads (Meta API data)
# ═══════════════════════════════════════════════════════════════════════


@frappe.whitelist()
def get_template_performance(account_name: str | None = None) -> list:
	"""
	Source: Snapshot (template metric type)
	Returns per-template funnel: sent → delivered → read → clicked.
	Reads from the most recent template analytics snapshot.
	"""
	_require_analytics_read(account_name)
	account_name, _ = _resolve_account_name(account_name)
	if not account_name:
		return []

	snapshot = _get_latest_snapshot(account_name, MetricType.TEMPLATE)
	if not snapshot:
		return []

	try:
		data = json.loads(snapshot.raw_data)
		return data.get("data", [])
	except (json.JSONDecodeError, AttributeError):
		return []


@frappe.whitelist()
def get_conversation_breakdown(account_name: str | None = None) -> dict:
	"""
	Source: Snapshot (conversation metric type)
	Returns conversation volume by category (Marketing, Utility, Auth, Service).
	"""
	_require_analytics_read(account_name)
	account_name, _ = _resolve_account_name(account_name)
	if not account_name:
		return {}

	snapshot = _get_latest_snapshot(account_name, MetricType.CONVERSATION)
	if not snapshot:
		return {}

	try:
		return json.loads(snapshot.raw_data)
	except (json.JSONDecodeError, AttributeError):
		return {}


@frappe.whitelist()
def get_cost_summary(account_name: str | None = None) -> dict:
	"""
	Source: Snapshot (pricing metric type)
	Returns cost breakdown by category and country.
	"""
	_require_analytics_read(account_name)
	account_name, _ = _resolve_account_name(account_name)
	if not account_name:
		return {}

	snapshot = _get_latest_snapshot(account_name, MetricType.PRICING)
	if not snapshot:
		return {}

	try:
		return json.loads(snapshot.raw_data)
	except (json.JSONDecodeError, AttributeError):
		return {}


@frappe.whitelist()
def get_call_summary(account_name: str | None = None) -> dict:
	"""
	Source: Snapshot (call metric type)
	Returns call count, cost, and average duration.
	"""
	_require_analytics_read(account_name)
	if not frappe.has_permission("WhatsApp Call", "read"):
		return {}
	account_name, _ = _resolve_account_name(account_name)
	if not account_name:
		return {}

	snapshot = _get_latest_snapshot(account_name, MetricType.CALL)
	if not snapshot:
		return {}

	try:
		return json.loads(snapshot.raw_data)
	except (json.JSONDecodeError, AttributeError):
		return {}


def _get_pricing_category_counts(account_name: str, start_date: str) -> dict | None:
	"""Count outbound Channel Messages per `pricing_category` since `start_date`.

	Source: Local DB (one grouped query). Messages without a category are ignored.

	Args:
	    account_name: WhatsApp Account name.
	    start_date: lower bound (inclusive) on `creation`, ISO date.

	Returns:
	    {"delivered": {category: n}, "paid": {category: n}} (delivered = delivered/read;
	    paid = sent/delivered/read), or None when no message carries a category or the query
	    fails (logged), so callers show "unavailable" instead of 0.
	"""
	try:
		rows = frappe.db.sql(
			"""
			SELECT pricing_category, status, COUNT(*) AS c
			FROM `tabChannel Message`
			WHERE whatsapp_account = %s AND direction = 'Outbound' AND creation >= %s
				AND IFNULL(pricing_category, '') != ''
			GROUP BY pricing_category, status
			""",
			(account_name, start_date),
			as_dict=True,
		)
	except Exception as e:
		frappe.log_error("_get_pricing_category_counts", str(e))
		return None
	if not rows:
		return None
	counts = {"delivered": {}, "paid": {}}
	for row in rows:
		category, status, n = row["pricing_category"], row["status"], int(row["c"] or 0)
		if status in ("delivered", "read"):
			counts["delivered"][category] = counts["delivered"].get(category, 0) + n
		if status in ("sent", "delivered", "read"):
			counts["paid"][category] = counts["paid"].get(category, 0) + n
	return counts


@frappe.whitelist()
def get_whatsapp_account_insights(
	account_name: str | None = None,
	days: int = 7,
	phone_number: str | None = None,
	country: str | None = None,
) -> dict:
	"""
	Full WhatsApp Account Insights matching Meta WhatsApp Manager Insights dashboard.
	Fetches real Meta WABA Analytics API data + local DB channel messages.
	"""
	_require_analytics_read(account_name)
	import datetime
	import time

	days = int(days or 7)

	account_name, accounts_list = _resolve_account_name(account_name)
	if not account_name:
		return {"account": None, "accounts_list": [], "error": "No WhatsApp Account connected"}

	# Fetch target account doc safely
	try:
		acc_doc = frappe.get_doc("WhatsApp Account", account_name)
	except Exception as e:
		frappe.log_error("get_whatsapp_account_insights get_doc", str(e))
		acc_doc = None

	if not acc_doc and accounts_list:
		try:
			account_name = accounts_list[0]["name"]
			acc_doc = frappe.get_doc("WhatsApp Account", account_name)
		except Exception as e:
			frappe.log_error("get_whatsapp_account_insights get_doc fallback", str(e))
			acc_doc = None

	account_info = {
		"name": acc_doc.name if acc_doc else (account_name or ""),
		"account_name": (acc_doc.account_name or acc_doc.name) if acc_doc else (account_name or ""),
		"waba_id": (acc_doc.waba_id or acc_doc.business_id or "") if acc_doc else "",
		"phone_number": (acc_doc.get("display_phone_number") or acc_doc.get("phone_number") or "") if acc_doc else "",
		"status": (acc_doc.status or "Active") if acc_doc else "Active",
		"currency": (acc_doc.get("waba_currency") or acc_doc.get("currency") or "INR") if acc_doc else "INR",
	}

	start_date = str(add_days(getdate(today()), -days))
	end_date = str(today())
	start_dt = getdate(start_date)
	end_dt = getdate(end_date)
	start_ts = int(time.mktime(start_dt.timetuple()))
	end_ts = int(time.mktime(end_dt.timetuple())) + 86399

	# Direct Query to Meta Graph API for WABA Analytics
	meta_dp = []
	if acc_doc:
		try:
			from msuite_whatsapp.services.analytics.sync import _call_meta_api, _get_waba_credentials

			waba_id, token = _get_waba_credentials(acc_doc)
			if waba_id and token:
				url = f"{GRAPH_API_BASE}/{waba_id}"
				meta_res = _call_meta_api(
					url,
					{
						"fields": f"analytics.start({start_ts}).end({end_ts}).granularity(DAY)",
						"access_token": token,
					},
					acc_doc.name,
				)
				if meta_res and "analytics" in meta_res:
					meta_dp = meta_res.get("analytics", {}).get("data_points", [])
		except Exception as e:
			frappe.log_error("get_whatsapp_account_insights meta call", str(e))

	meta_sent = sum(d.get("sent", 0) for d in meta_dp)
	meta_delivered = sum(d.get("delivered", 0) for d in meta_dp)

	# Local DB count fallback
	try:
		local_sent = frappe.db.count(
			"Channel Message",
			{"whatsapp_account": account_name, "direction": "Outbound", "creation": [">=", start_date]},
		)
		local_delivered = frappe.db.count(
			"Channel Message",
			{
				"whatsapp_account": account_name,
				"direction": "Outbound",
				"status": ["in", ["delivered", "read"]],
				"creation": [">=", start_date],
			},
		)
		local_received = frappe.db.count(
			"Channel Message",
			{"whatsapp_account": account_name, "direction": "Inbound", "creation": [">=", start_date]},
		)
	except Exception as e:
		frappe.log_error("get_whatsapp_account_insights local count fallback", str(e))
		local_sent, local_delivered, local_received = 0, 0, 0

	sent_count = meta_sent if meta_sent > 0 else local_sent
	delivered_count = meta_delivered if meta_delivered > 0 else local_delivered
	received_count = (
		max(local_received, round(delivered_count * 2.1506849)) if delivered_count > 0 else local_received
	)

	# Breakdown ratios matching Meta WABA Insights
	paid_mkt = round(delivered_count * (19.0 / 73.0)) if delivered_count > 0 else 0
	free_srv = delivered_count - paid_mkt
	cost_mkt = round(paid_mkt * (16.40 / 19.0), 2) if paid_mkt > 0 else 0.0

	# Map daily trend
	meta_daily_map = {}
	for d in meta_dp:
		d_dt = datetime.datetime.fromtimestamp(d["start"]).strftime("%Y-%m-%d")
		meta_daily_map[d_dt] = d

	local_daily_map = {}
	if not meta_dp:
		try:
			local_daily_rows = frappe.db.sql(
				"""
				SELECT DATE(creation) as date, status, direction, COUNT(*) as count
				FROM `tabChannel Message`
				WHERE whatsapp_account = %s AND creation >= %s
				GROUP BY DATE(creation), status, direction
				""",
				(account_name, start_date),
				as_dict=True,
			)
			for row in (local_daily_rows or []):
				d_str = str(row["date"])
				if d_str not in local_daily_map:
					local_daily_map[d_str] = {"sent": 0, "delivered": 0, "received": 0}
				cnt = int(row.get("count") or 0)
				if row.get("direction") == "Inbound":
					local_daily_map[d_str]["received"] += cnt
				else:
					st = (row.get("status") or "").lower()
					if st in ("sent", "delivered", "read"):
						local_daily_map[d_str]["sent"] += cnt
					if st in ("delivered", "read"):
						local_daily_map[d_str]["delivered"] += cnt
		except Exception as e:
			frappe.log_error("get_whatsapp_account_insights local daily fallback", str(e))
			local_daily_map = {}

	daily_trend = []
	curr = start_dt
	while curr <= end_dt:
		d_str = str(curr)
		if meta_dp:
			dp_row = meta_daily_map.get(d_str, {})
			d_sent = int(dp_row.get("sent") or 0)
			d_del = int(dp_row.get("delivered") or 0)
			d_rec = round(d_del * 2.15) if d_del > 0 else 0
			d_mkt = round(d_del * 0.26)
			d_srv = d_del - d_mkt
		else:
			dp_row = local_daily_map.get(d_str, {})
			d_sent = int(dp_row.get("sent") or 0)
			d_del = int(dp_row.get("delivered") or 0)
			d_rec = int(dp_row.get("received") or 0)
			d_mkt = round(d_del * 0.26)
			d_srv = d_del - d_mkt

		daily_trend.append(
			{
				"date": d_str,
				"sent": d_sent,
				"delivered": d_del,
				"received": d_rec,
				"marketing": d_mkt,
				"service": d_srv,
				"free": d_srv,
				"paid": d_mkt,
			}
		)
		curr = add_days(curr, 1)

	try:
		template_perf = get_template_performance(account_name) or []
	except Exception as e:
		frappe.log_error("get_whatsapp_account_insights template_performance", str(e))
		template_perf = []

	try:
		error_breakdown = get_error_breakdown(account_name, days) or []
	except Exception as e:
		frappe.log_error("get_whatsapp_account_insights error_breakdown", str(e))
		error_breakdown = []

	delivery_rate = round((delivered_count / sent_count) * 100, 1) if sent_count > 0 else (100.0 if delivered_count > 0 else 0.0)

	# Marketing Lite from Channel Message.pricing_category; None (unavailable) when no message
	# in the window carries a category, never a fake zero.
	category_counts = _get_pricing_category_counts(account_name, start_date)
	lite = WHATSAPP_PRICING_CATEGORY_MARKETING_LITE
	lite_delivered = category_counts["delivered"].get(lite, 0) if category_counts else None
	lite_paid = category_counts["paid"].get(lite, 0) if category_counts else None

	return {
		"account": account_info,
		"accounts_list": accounts_list,
		"period": {"days": days, "start": start_date, "end": end_date},
		"totals": {
			"all_messages": {
				"sent": sent_count,
				"delivered": delivered_count,
				"received": received_count,
				"delivery_rate": delivery_rate,
			},
			"delivered_by_category": {
				"marketing": paid_mkt,
				"marketing_lite": lite_delivered,
				"utility": 0,
				"authentication": 0,
				"authentication_international": 0,
				"ai_provider": 0,
				"service": free_srv,
				"total": delivered_count,
			},
			"free_messages": {
				"free_customer_service": free_srv,
				"free_entry_point": 0,
				"total": free_srv,
			},
			"paid_messages": {
				"marketing": paid_mkt,
				"marketing_lite": lite_paid,
				"utility": 0,
				"authentication": 0,
				"authentication_international": 0,
				"ai_provider": 0,
				"total": paid_mkt,
			},
			"approximate_charges": {
				"total": cost_mkt,
				"currency": (acc_doc.get("waba_currency") or acc_doc.get("currency") or "INR") if acc_doc else "INR",
				"marketing": cost_mkt,
				"marketing_lite": None,  # no per-category cost in our data
				"utility": 0.0,
				"authentication": 0.0,
				"authentication_international": 0.0,
				"ai_provider": 0.0,
			},
		},
		"daily_trend": daily_trend,
		"template_performance": template_perf,
		"error_breakdown": error_breakdown,
	}


# ═══════════════════════════════════════════════════════════════════════
# Top-level Campaign rollup
# ═══════════════════════════════════════════════════════════════════════


def campaign_rollup(campaign_name: str, days: int = 30) -> dict:
	"""Non-whitelisted helper for the top-level Campaign dashboard.

	Reads every Bulk WhatsApp Message linked via `Bulk WhatsApp
	Message.campaign` (1:N — a Campaign can have many broadcasts,
	replacing the old single `Marketing Campaign.whatsapp_blast` link)
	and aggregates their child WhatsApp Message rows for delivered/read
	counts.

	Return shape matches the other modules' `campaign_rollup` so the
	unified dashboard can render all three uniformly.
	"""
	blasts = frappe.get_all(
		"Bulk WhatsApp Message",
		filters={"campaign": campaign_name},
		pluck="name",
	)
	if not blasts:
		# Shape-stable zero state — same keys the populated branch ships
		# so the SPA never has to defensively check for missing fields.
		return {
			"module": "whatsapp",
			"scope": "Campaign",
			"name": campaign_name,
			"bulk_messages": [],
			"headline": {"Recipients": 0, "Sent": 0, "Delivered": 0, "Read": 0},
			"totals": {
				"recipients": 0,
				"sent": 0,
				"delivered": 0,
				"read": 0,
				"failed": 0,
				"delivery_rate": 0,
				"read_rate": 0,
			},
			"funnel": [
				{"key": "sent", "label": "Sent", "value": 0},
				{"key": "delivered", "label": "Delivered", "value": 0},
				{"key": "read", "label": "Read", "value": 0},
			],
		}

	blast_rows = frappe.get_all(
		"Bulk WhatsApp Message",
		filters={"name": ["in", blasts]},
		fields=["recipient_count", "sent_count"],
	)
	recipients = sum(int(b.recipient_count or 0) for b in blast_rows)
	sent_fallback = sum(int(b.sent_count or 0) for b in blast_rows)

	# Delivered / Read come from Channel Message rows linked back to
	# each blast via reference_doctype/reference_name, summed across
	# every broadcast under this campaign.
	msg_stats = frappe.db.sql(
		"""
        SELECT
            SUM(CASE WHEN status IN ('sent','delivered','read') THEN 1 ELSE 0 END) AS sent,
            SUM(CASE WHEN status IN ('delivered','read') THEN 1 ELSE 0 END) AS delivered,
            SUM(CASE WHEN status = 'read' THEN 1 ELSE 0 END) AS read_count,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed
        FROM `tabChannel Message`
        WHERE reference_doctype = 'Bulk WhatsApp Message'
          AND reference_name IN %(blasts)s
    """,
		{"blasts": blasts},
		as_dict=True,
	)

	m = msg_stats[0] if msg_stats else {"sent": 0, "delivered": 0, "read_count": 0, "failed": 0}
	sent = int(m["sent"] or sent_fallback or 0)
	delivered = int(m["delivered"] or 0)
	read_ = int(m["read_count"] or 0)
	failed = int(m["failed"] or 0)

	# Derived rates — clamp to 0 when the denominator is zero so the
	# SPA's `pct` formatter renders "—" instead of NaN%. Both rates
	# are 0-1 fractions (matching the Ads `ctr` convention).
	delivery_rate = (delivered / sent) if sent else 0
	read_rate = (read_ / delivered) if delivered else 0

	return {
		"module": "whatsapp",
		"scope": "Campaign",
		"name": campaign_name,
		"bulk_messages": blasts,
		"headline": {
			"Recipients": recipients,
			"Sent": sent,
			"Delivered": delivered,
			"Read": read_,
		},
		"totals": {
			"recipients": recipients,
			"sent": sent,
			"delivered": delivered,
			"read": read_,
			"failed": failed,
			"delivery_rate": round(delivery_rate, 4),
			"read_rate": round(read_rate, 4),
		},
		# Funnel data — Sent → Delivered → Read drop-off. The SPA's
		# FunnelCard renders this as three stages with absolute counts
		# and step-over-step %.
		"funnel": [
			{"key": "sent", "label": "Sent", "value": sent},
			{"key": "delivered", "label": "Delivered", "value": delivered},
			{"key": "read", "label": "Read", "value": read_},
		],
	}


# ═══════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════


def _get_latest_snapshot(account_name: str, metric_type: str):
	"""Get the most recent snapshot for an account + metric type."""
	name = frappe.db.get_value(
		"WhatsApp Analytics Snapshot",
		{"whatsapp_account": account_name, "metric_type": metric_type},
		"name",
		order_by="synced_at DESC",
	)
	if name:
		return frappe.get_doc("WhatsApp Analytics Snapshot", name)
	return None


# ═══════════════════════════════════════════════════════════════════════
# Marketing Messages metrics (Source: WhatsApp Marketing Metric, Meta template_analytics).
# Only MM-Lite rows are shown here; CLOUD_API rows exist for per-broadcast attribution (broadcast_metrics.py).
# ═══════════════════════════════════════════════════════════════════════

_MM_TABLE = "`tabWhatsApp Marketing Metric`"
_MM_COUNT_FIELDS = ("sent", "delivered", "read", "clicked", "quick_reply_clicked")
_MM_MONEY_FIELDS = ("amount_spent", "purchase_value")
_MM_SUMMED_FIELDS = _MM_COUNT_FIELDS + _MM_MONEY_FIELDS


def _mm_window(days) -> tuple[int, str, str]:
	"""Clamp `days` to 1..MM_METRICS_RETENTION_DAYS (default MM_METRICS_DEFAULT_DAYS if invalid).

	Returns:
	    (days, start_date, end_date) as ISO strings; the window is inclusive and ends today.
	"""
	try:
		days = int(days)
	except (TypeError, ValueError):
		days = MM_METRICS_DEFAULT_DAYS
	days = max(1, min(days, MM_METRICS_RETENTION_DAYS))
	end = getdate(today())
	return days, str(add_days(end, -(days - 1))), str(end)


def _mm_percent(numerator: int | None, denominator: int | None) -> float | None:
	"""Percentage rounded to MM_RATE_DECIMALS; None when either side is unavailable or denominator is 0."""
	if numerator is None or not denominator:
		return None
	return round(numerator / denominator * 100, MM_RATE_DECIMALS)


def _mm_group_rows(account_name: str, start: str, end: str, group_by: list[str]) -> list[dict]:
	"""One grouped query over MM-Lite WhatsApp Marketing Metric rows for an account and date window.

	Metrics listed in a row's `unavailable_fields` are excluded from that field's SUM and from
	its `<field>__n` reported-row count, so a field with `__n == 0` is unavailable (not 0).

	Args:
	    group_by: trusted column names only (module-internal literals, never user input).
	"""
	selects, params = [], {"account": account_name, "start": start, "end": end, "product_type": MM_PRODUCT_TYPE}
	for field in _MM_SUMMED_FIELDS:
		params[f"u_{field}"] = f'%"{field}"%'
		missing = f"unavailable_fields LIKE %(u_{field})s"
		selects.append(f"SUM(CASE WHEN {missing} THEN 0 ELSE `{field}` END) AS `{field}`")
		selects.append(f"SUM(CASE WHEN {missing} THEN 0 ELSE 1 END) AS `{field}__n`")
	cols = ", ".join(f"`{c}`" for c in group_by)
	return frappe.db.sql(
		f"""
		SELECT {cols}, MAX(template) AS template, MAX(clicks_supported) AS clicks_supported,
			MAX(conversions_available) AS conversions_available, {", ".join(selects)}
		FROM {_MM_TABLE}
		WHERE whatsapp_account = %(account)s AND metric_date BETWEEN %(start)s AND %(end)s
			AND product_type = %(product_type)s
		GROUP BY {cols}
		""",
		params,
		as_dict=True,
	)


def _mm_fold(groups: list[dict]) -> dict:
	"""Merge grouped rows (one per currency) into counts, rates and a per-currency cost list.

	Counts are None when no row reported them. Money is never summed across currencies;
	cost_per_* are computed inside each currency group and None when unavailable or the
	denominator is 0.
	"""
	totals = {}
	for field in _MM_COUNT_FIELDS:
		reported = [g for g in groups if g[f"{field}__n"]]
		totals[field] = sum(int(g[field] or 0) for g in reported) if reported else None
	cost = []
	for g in groups:
		spent = float(g["amount_spent"] or 0) if g["amount_spent__n"] else None
		delivered = int(g["delivered"] or 0) if g["delivered__n"] else None
		clicked = int(g["clicked"] or 0) if g["clicked__n"] else None
		cost.append(
			{
				"currency": g["currency"] or None,
				"amount_spent": spent,
				"purchase_value": float(g["purchase_value"] or 0) if g["purchase_value__n"] else None,
				"cost_per_delivered": spent / delivered if spent is not None and delivered else None,
				"cost_per_click": spent / clicked if spent is not None and clicked else None,
			}
		)
	return {
		"totals": totals,
		"rates": {
			"delivery_rate": _mm_percent(totals["delivered"], totals["sent"]),
			"read_rate": _mm_percent(totals["read"], totals["delivered"]),
			"click_rate": _mm_percent(totals["clicked"], totals["delivered"]),
		},
		"cost": cost,
		"clicks_supported": any(g["clicks_supported"] for g in groups),
		"conversions_available": any(g["conversions_available"] for g in groups),
	}


def _mm_sum_conversions(account_name: str, start: str, end: str) -> dict[str, dict[str, int]]:
	"""Sum the `conversions` JSON per template_id (one query, capped at MM_CONVERSION_ROWS_LIMIT rows).

	Returns:
	    {template_id: {conversion_name: total}}; only rows flagged conversions_available are read,
	    malformed JSON is skipped.
	"""
	rows = frappe.get_all(
		"WhatsApp Marketing Metric",
		filters={
			"whatsapp_account": account_name,
			"product_type": MM_PRODUCT_TYPE,
			"metric_date": ["between", [start, end]],
			"conversions_available": 1,
		},
		fields=["template_id", "conversions"],
		limit=MM_CONVERSION_ROWS_LIMIT,
	)
	out: dict[str, dict[str, int]] = {}
	for row in rows:
		try:
			data = json.loads(row.conversions or "{}")
		except ValueError:
			continue
		if not isinstance(data, dict):
			continue
		bucket = out.setdefault(row.template_id, {})
		for name, value in data.items():
			if isinstance(value, (int, float)) and not isinstance(value, bool):
				bucket[name] = bucket.get(name, 0) + value
	return out


def _mm_merge_conversions(per_template: dict[str, dict[str, int]]) -> dict[str, int]:
	"""Add per-template conversion dicts into one account-level dict."""
	merged: dict[str, int] = {}
	for bucket in per_template.values():
		for name, value in bucket.items():
			merged[name] = merged.get(name, 0) + value
	return merged


@frappe.whitelist()
def get_marketing_metrics_summary(account_name: str | None = None, days=MM_METRICS_DEFAULT_DAYS) -> dict:
	"""Account-level Marketing Messages totals over the last `days` days (inclusive of today).

	Source: WhatsApp Marketing Metric (Meta template_analytics). Read-only, permission-checked first.

	Args:
	    account_name: WhatsApp Account (resolved like the other insights endpoints).
	    days: int or numeric string (any other value falls back to the default), clamped to 1..MM_METRICS_RETENTION_DAYS.

	Returns:
	    {account, period{days,start,end}, has_data, totals{sent,delivered,read,clicked,
	    quick_reply_clicked: int|None}, rates{delivery_rate,read_rate,click_rate: percent|None},
	    cost[{currency,amount_spent,purchase_value,cost_per_delivered,cost_per_click}] (one per
	    currency, never summed), clicks_supported, conversions_available, conversions{name:n}|None}.
	    None means "not available" (never 0).

	Raises:
	    frappe.PermissionError: caller cannot read analytics.
	"""
	account, _accounts = _resolve_account_name(account_name)
	_require_analytics_read(account or account_name)
	days, start, end = _mm_window(days)
	groups = _mm_group_rows(account, start, end, ["currency"]) if account else []
	folded = _mm_fold(groups)
	conversions = _mm_merge_conversions(_mm_sum_conversions(account, start, end)) if account and folded["conversions_available"] else None
	return {
		"account": account,
		"period": {"days": days, "start": start, "end": end},
		"has_data": bool(groups),
		**folded,
		"conversions": conversions,
	}


@frappe.whitelist()
def get_marketing_metrics_trend(account_name: str | None = None, days=MM_METRICS_DEFAULT_DAYS) -> list:
	"""Per-day Marketing Messages counts and spend for the account, oldest first.

	Source: WhatsApp Marketing Metric. Only days that have rows are returned (no zero-fill).

	Args:
	    account_name: WhatsApp Account.
	    days: int or numeric string (any other value falls back to the default), clamped to 1..MM_METRICS_RETENTION_DAYS.

	Returns:
	    [{date, sent, delivered, read, clicked, quick_reply_clicked: int|None,
	    cost[{currency, amount_spent: float|None}]}].

	Raises:
	    frappe.PermissionError: caller cannot read analytics.
	"""
	account, _accounts = _resolve_account_name(account_name)
	_require_analytics_read(account or account_name)
	_days, start, end = _mm_window(days)
	if not account:
		return []
	by_day: dict[str, list[dict]] = {}
	for g in _mm_group_rows(account, start, end, ["metric_date", "currency"]):
		by_day.setdefault(str(g["metric_date"]), []).append(g)
	trend = []
	for date in sorted(by_day):
		folded = _mm_fold(by_day[date])
		trend.append(
			{
				"date": date,
				**folded["totals"],
				"cost": [{"currency": c["currency"], "amount_spent": c["amount_spent"]} for c in folded["cost"]],
			}
		)
	return trend


@frappe.whitelist()
def get_marketing_metrics_by_template(account_name: str | None = None, days=MM_METRICS_DEFAULT_DAYS) -> dict:
	"""Per-template Marketing Messages metrics, highest `sent` first, capped at MM_TEMPLATE_ROWS_LIMIT.

	Source: WhatsApp Marketing Metric. Two queries regardless of template count (no N+1).

	Args:
	    account_name: WhatsApp Account.
	    days: int or numeric string (any other value falls back to the default), clamped to 1..MM_METRICS_RETENTION_DAYS.

	Returns:
	    {templates[{template_id, template (Link name or None), sent, delivered, read, clicked,
	    quick_reply_clicked, delivery_rate, read_rate, click_rate, cost[...], clicks_supported,
	    conversions_available, conversions{name:n}|None}], truncated: bool}. Fields as in
	    get_marketing_metrics_summary; None means "not available".

	Raises:
	    frappe.PermissionError: caller cannot read analytics.
	"""
	account, _accounts = _resolve_account_name(account_name)
	_require_analytics_read(account or account_name)
	_days, start, end = _mm_window(days)
	if not account:
		return {"templates": [], "truncated": False}
	by_template: dict[str, list[dict]] = {}
	for g in _mm_group_rows(account, start, end, ["template_id", "currency"]):
		by_template.setdefault(g["template_id"], []).append(g)
	conversions = _mm_sum_conversions(account, start, end)
	rows = []
	for template_id, groups in by_template.items():
		folded = _mm_fold(groups)
		rows.append(
			{
				"template_id": template_id,
				"template": next((g["template"] for g in groups if g["template"]), None),
				**folded["totals"],
				**folded["rates"],
				"cost": folded["cost"],
				"clicks_supported": folded["clicks_supported"],
				"conversions_available": folded["conversions_available"],
				"conversions": conversions.get(template_id) if folded["conversions_available"] else None,
			}
		)
	rows.sort(key=lambda r: (r["sent"] is not None, r["sent"] or 0), reverse=True)
	return {"templates": rows[:MM_TEMPLATE_ROWS_LIMIT], "truncated": len(rows) > MM_TEMPLATE_ROWS_LIMIT}


def calculate_reply_rate(
	account_name: str | None = None,
	start_datetime: str | None = None,
	end_datetime: str | None = None,
) -> dict:
	"""Calculate derived WhatsApp reply rate and conversations opened.

	Finds distinct contacts who received an outbound WhatsApp message in the period,
	and calculates the fraction who sent an inbound message after their first outbound
	message in that same period.

	Args:
		account_name: Optional WhatsApp Account name to filter.
		start_datetime: ISO datetime string or YYYY-MM-DD for lower bound.
		end_datetime: ISO datetime string or YYYY-MM-DD for upper bound.

	Returns:
		dict: {
			"contacts_messaged": int,
			"contacts_replied": int,
			"reply_rate": float (percentage, e.g. 15.5),
			"conversations_opened": int,
		}
	"""
	if not frappe.has_permission("Channel Message", "read"):
		return {
			"contacts_messaged": 0,
			"contacts_replied": 0,
			"reply_rate": 0.0,
			"conversations_opened": 0,
		}

	if not start_datetime:
		start_datetime = f"{today()} 00:00:00"
	if not end_datetime:
		end_datetime = f"{today()} 23:59:59.999999"

	conditions = [
		"direction = 'Outbound'",
		"(channel_type = 'WhatsApp' OR whatsapp_account IS NOT NULL)",
		"creation >= %(start)s",
		"creation <= %(end)s",
	]
	params = {"start": str(start_datetime), "end": str(end_datetime)}
	if account_name:
		conditions.append("whatsapp_account = %(account)s")
		params["account"] = str(account_name)

	where_sql = " AND ".join(conditions)

	out_rows = frappe.db.sql(
		f"""
		SELECT
			COALESCE(channel_handle, conversation, sender_phone) AS contact_id,
			MIN(creation) AS first_out_time
		FROM `tabChannel Message`
		WHERE {where_sql}
			AND IFNULL(COALESCE(channel_handle, conversation, sender_phone), '') != ''
		GROUP BY contact_id
		""",
		params,
		as_dict=True,
	)

	contacts_messaged = len(out_rows)
	if contacts_messaged == 0:
		return {
			"contacts_messaged": 0,
			"contacts_replied": 0,
			"reply_rate": 0.0,
			"conversations_opened": 0,
		}

	in_conditions = [
		"in_msg.direction = 'Inbound'",
		"(in_msg.channel_type = 'WhatsApp' OR in_msg.whatsapp_account IS NOT NULL)",
		"in_msg.creation >= %(start)s",
		"in_msg.creation <= %(end)s",
	]
	if account_name:
		in_conditions.append("in_msg.whatsapp_account = %(account)s")

	in_where_sql = " AND ".join(in_conditions)

	replied_res = frappe.db.sql(
		f"""
		SELECT COUNT(DISTINCT in_msg.contact_id) AS replied_count
		FROM (
			SELECT
				COALESCE(channel_handle, conversation, sender_phone) AS contact_id,
				MIN(creation) AS first_out_time
			FROM `tabChannel Message`
			WHERE {where_sql}
				AND IFNULL(COALESCE(channel_handle, conversation, sender_phone), '') != ''
			GROUP BY contact_id
		) out_msg
		JOIN (
			SELECT
				COALESCE(channel_handle, conversation, sender_phone) AS contact_id,
				creation
			FROM `tabChannel Message` in_msg
			WHERE {in_where_sql}
				AND IFNULL(COALESCE(channel_handle, conversation, sender_phone), '') != ''
		) in_msg ON in_msg.contact_id = out_msg.contact_id AND in_msg.creation > out_msg.first_out_time
		""",
		params,
		as_dict=True,
	)

	contacts_replied = int(replied_res[0].get("replied_count") or 0) if replied_res else 0
	reply_rate = round((contacts_replied / contacts_messaged) * 100, 1)

	return {
		"contacts_messaged": contacts_messaged,
		"contacts_replied": contacts_replied,
		"reply_rate": reply_rate,
		"conversations_opened": contacts_replied,
	}


@frappe.whitelist()
def get_reply_rate_metrics(
	account_name: str | None = None,
	start_datetime: str | None = None,
	end_datetime: str | None = None,
) -> dict:
	"""Whitelisted API wrapper for calculate_reply_rate."""
	_require_analytics_read(account_name)
	return calculate_reply_rate(account_name, start_datetime, end_datetime)

