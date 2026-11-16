"""
WhatsApp Account API — WABA helper dropdowns + the cross-domain dashboard.

Relocated from `api/v1/whatsapp/crud.py` (see WHATSAPP_REFACTOR_PLAN.md §9).
The dotted path `msuite_whatsapp.api.v1.app.crud.*` is preserved via
a re-export shim in that module since the SPA calls it by that exact path.
"""

from datetime import timedelta
import frappe
from frappe.utils import add_days, getdate, today

from msuite_whatsapp.services.permissions.checks import check_read, check_write
from msuite_whatsapp.services.analytics.aivo_facts import get_whatsapp_aivo_facts
from msuite_whatsapp.services.analytics.broadcast_metrics import _rate, summarize_status_counts
from msuite_whatsapp.api.v1.app.analytics_query import calculate_reply_rate

ACCOUNT_DOCTYPE = "WhatsApp Account"
TEMPLATE_DOCTYPE = "WhatsApp Templates"
RECIPIENT_LIST_DOCTYPE = "WhatsApp Recipient List"
BULK_MESSAGE_DOCTYPE = "Bulk WhatsApp Message"
FLOW_DOCTYPE = "WhatsApp Flow"
CHANNEL_MESSAGE_DOCTYPE = "Channel Message"

CAT_MAP = {
	"MARKETING": "Marketing",
	"UTILITY": "Utility",
	"TRANSACTIONAL": "Utility",
	"AUTHENTICATION": "Authentication",
	"OTP": "Authentication",
}


def _format_quality_rating(qr: str | None) -> str:
	"""Format raw Meta quality rating into user-facing label."""
	if not qr:
		return "Unknown"
	q = str(qr).strip().upper()
	if q in ("GREEN", "HIGH"):
		return "High"
	if q in ("YELLOW", "MEDIUM"):
		return "Medium"
	if q in ("RED", "LOW"):
		return "Low"
	return qr


def _format_messaging_tier(tier: str | None) -> str:
	"""Format raw messaging tier string."""
	if not tier:
		return "—"
	t = str(tier).strip().upper()
	if t.startswith("TIER_"):
		t = t.replace("TIER_", "")
	if t == "UNLIMITED":
		return "Unlimited"
	return t


@frappe.whitelist()
def get_dashboard_metrics(period: str = "month", account_name: str | None = None) -> dict:
	"""Dashboard cards + recent lists, each gated on its own doctype.

	BUG-023: this used to `check_read` all four doctypes up front, so a role
	missing just one (WhatsApp Manager had no read on WhatsApp Flow) failed the
	whole call and the dashboard showed "No templates/broadcasts yet". Now a
	missing permission only empties its own section, and counts/lists go
	through get_list so they respect user permissions.

	Supports:
	- named periods: '7d', 'month' (month-to-date), 'qtr' (90d)
	- category rollup (Marketing, Utility, Authentication) with sent, delivered, read
	- quality rating and messaging tier
	- template approval counts
	- previous-period values for delta comparisons
	- derived reply rate and conversations opened
	- pure rule-based Aivo facts
	"""

	def can(doctype):
		return frappe.has_permission(doctype, "read")

	def count(doctype, filters=None):
		return len(frappe.get_list(doctype, filters=filters or {}, pluck="name")) if can(doctype) else 0

	# 1. Period window calculation
	today_date = getdate(today())
	if period in ("mtd", "month", "month-to-date"):
		current_until = today_date
		current_since = today_date.replace(day=1)
		p_days = (current_until - current_since).days + 1
		prev_until = current_since - timedelta(days=1)
		prev_since = prev_until - timedelta(days=p_days - 1)
		period_label = "month"
	elif period in ("qtr", "90d"):
		p_days = 90
		current_until = today_date
		current_since = add_days(current_until, -p_days + 1)
		prev_until = add_days(current_since, -1)
		prev_since = add_days(prev_until, -p_days + 1)
		period_label = "qtr"
	elif period in ("7d", "7days"):
		p_days = 7
		current_until = today_date
		current_since = add_days(current_until, -p_days + 1)
		prev_until = add_days(current_since, -1)
		prev_since = add_days(prev_until, -p_days + 1)
		period_label = "7d"
	else:
		current_until = today_date
		current_since = today_date.replace(day=1)
		p_days = (current_until - current_since).days + 1
		prev_until = current_since - timedelta(days=1)
		prev_since = prev_until - timedelta(days=p_days - 1)
		period_label = "month"

	start_datetime = f"{current_since} 00:00:00"
	end_datetime = f"{current_until} 23:59:59.999999"
	prev_start_datetime = f"{prev_since} 00:00:00"
	prev_end_datetime = f"{prev_until} 23:59:59.999999"

	# 2. Template stats, approvals, and rejections
	total_templates = 0
	approved_count = 0
	pending_count = 0
	rejected_count = 0
	rejected_templates: list[dict] = []
	recent_tpls = []
	tpl_cat_stats = {
		"Marketing": {"sent": 0, "delivered": 0, "read": 0},
		"Utility": {"sent": 0, "delivered": 0, "read": 0},
		"Authentication": {"sent": 0, "delivered": 0, "read": 0},
	}
	tpl_total_sent = 0
	tpl_total_delivered = 0
	tpl_total_read = 0
	tpl_cat_by_name: dict[str, str] = {}

	if can(TEMPLATE_DOCTYPE):
		tpl_filters = {"whatsapp_account": account_name} if account_name else {}
		tpl_rows = frappe.get_list(
			TEMPLATE_DOCTYPE,
			fields=[
				"name",
				"template_name",
				"status",
				"category",
				"total_sent",
				"total_delivered",
				"total_read",
				"rejection_reason",
			],
			filters=tpl_filters,
			limit=1000,
		)
		total_templates = len(tpl_rows)
		for t in tpl_rows:
			t_name = t.get("name") if isinstance(t, dict) else t.name
			t_tname = t.get("template_name") if isinstance(t, dict) else t.template_name
			t_status = t.get("status") if isinstance(t, dict) else t.status
			t_cat = t.get("category") if isinstance(t, dict) else t.category
			t_rej = t.get("rejection_reason") if isinstance(t, dict) else t.rejection_reason
			t_sent = t.get("total_sent") if isinstance(t, dict) else t.total_sent
			t_deliv = t.get("total_delivered") if isinstance(t, dict) else t.total_delivered
			t_read = t.get("total_read") if isinstance(t, dict) else t.total_read

			if t_name and t_cat:
				tpl_cat_by_name[t_name] = t_cat
			if t_tname and t_cat:
				tpl_cat_by_name[t_tname] = t_cat

			st = (t_status or "").upper()
			if st == "APPROVED":
				approved_count += 1
			elif st in ("PENDING", "DRAFT"):
				pending_count += 1
			elif st in ("REJECTED", "PAUSED", "DISABLED"):
				rejected_count += 1

			if st == "REJECTED" or t_rej:
				rejected_templates.append(
					{
						"name": t_name,
						"template_name": t_tname or t_name,
						"rejection_reason": t_rej or "Policy violation",
					}
				)

			raw_cat = (t_cat or "").strip().upper()
			cat_norm = CAT_MAP.get(raw_cat, "Other")
			s = int(t_sent or 0)
			d = int(t_deliv or 0)
			r = int(t_read or 0)
			tpl_total_sent += s
			tpl_total_delivered += d
			tpl_total_read += r
			if cat_norm in tpl_cat_stats:
				tpl_cat_stats[cat_norm]["sent"] += s
				tpl_cat_stats[cat_norm]["delivered"] += d
				tpl_cat_stats[cat_norm]["read"] += r

		recent_tpls = frappe.get_list(
			TEMPLATE_DOCTYPE,
			fields=["name", "template_name", "status", "category", "language", "modified"],
			filters=tpl_filters,
			order_by="modified desc",
			limit=5,
		)

	# 3. Channel Message stats for current and previous periods (single query)
	cm_cat_rows: dict[str, list[dict]] = {
		"Marketing": [],
		"Utility": [],
		"Authentication": [],
	}
	prev_cm_rows: list[dict] = []

	if can(CHANNEL_MESSAGE_DOCTYPE):
		cm_params = {
			"current_start": start_datetime,
			"current_end": end_datetime,
			"prev_start": prev_start_datetime,
		}
		cm_filter = ""
		if account_name:
			cm_filter = "AND whatsapp_account = %(account)s"
			cm_params["account"] = account_name

		cm_rows = frappe.db.sql(
			f"""
			SELECT
				template_name,
				pricing_category,
				status,
				CASE WHEN creation >= %(current_start)s THEN 1 ELSE 0 END AS in_current,
				COUNT(*) AS count
			FROM `tabChannel Message`
			WHERE direction = 'Outbound'
				AND (channel_type = 'WhatsApp' OR whatsapp_account IS NOT NULL)
				AND creation >= %(prev_start)s AND creation <= %(current_end)s
				{cm_filter}
			GROUP BY template_name, pricing_category, status, in_current
			""",
			cm_params,
			as_dict=True,
		)
		for row in (cm_rows or []):
			in_curr = bool(row.get("in_current"))
			if in_curr:
				tpl_cat = tpl_cat_by_name.get(row.get("template_name"))
				cat_raw = (tpl_cat or row.get("pricing_category") or "").strip().upper()
				cat_norm = CAT_MAP.get(cat_raw, "Other" if cat_raw else "Marketing")
				if cat_norm in cm_cat_rows:
					cm_cat_rows[cat_norm].append(row)
			else:
				prev_cm_rows.append(row)

	# 4. Merge Category rollup (prefer Channel Message in active period, fallback to template stats)
	cm_cat_summary = {
		cat: summarize_status_counts(cm_cat_rows[cat])
		for cat in ("Marketing", "Utility", "Authentication")
	}
	cm_total_sent = sum(cm_cat_summary[cat]["totals"]["sent"] for cat in ("Marketing", "Utility", "Authentication"))

	category_rollup = []
	total_sent = 0
	total_delivered = 0
	total_read = 0

	for cat in ("Marketing", "Utility", "Authentication"):
		if cm_total_sent > 0:
			summary_block = cm_cat_summary[cat]
			s = summary_block["totals"]["sent"]
			d = summary_block["totals"]["delivered"]
			r = summary_block["totals"]["read"]
			d_rate = round(summary_block["rates"]["delivery"] * 100, 1) if summary_block["rates"]["delivery"] is not None else None
			r_rate = round(summary_block["rates"]["read"] * 100, 1) if summary_block["rates"]["read"] is not None else None
		else:
			tpl_c = tpl_cat_stats.get(cat, {"sent": 0, "delivered": 0, "read": 0})
			s = tpl_c["sent"]
			d = tpl_c["delivered"]
			r = tpl_c["read"]
			d_rate = round(_rate(d, s) * 100, 1) if _rate(d, s) is not None else None
			r_rate = round(_rate(r, d) * 100, 1) if _rate(r, d) is not None else None

		total_sent += s
		total_delivered += d
		total_read += r

		category_rollup.append(
			{
				"category": cat,
				"name": cat,
				"sent": s,
				"delivered": d,
				"read": r,
				"delivery_rate": d_rate,
				"read_rate": r_rate,
			}
		)

	delivery_rate = round(_rate(total_delivered, total_sent) * 100, 1) if _rate(total_delivered, total_sent) is not None else None
	read_rate = round(_rate(total_read, total_delivered) * 100, 1) if _rate(total_read, total_delivered) is not None else None

	# 5. Derived reply rate and conversations opened
	reply_info = calculate_reply_rate(account_name, start_datetime, end_datetime)
	replied = reply_info.get("contacts_replied", 0)
	reply_rate = reply_info.get("reply_rate", 0.0)
	conversations_opened = reply_info.get("conversations_opened", 0)

	# 6. Previous-period values
	prev_summary = summarize_status_counts(prev_cm_rows)
	prev_totals = prev_summary["totals"]
	prev_rates = prev_summary["rates"]
	prev_sent = prev_totals["sent"]
	prev_delivered = prev_totals["delivered"]
	prev_read = prev_totals["read"]
	prev_delivery_rate = round(prev_rates["delivery"] * 100, 1) if prev_rates["delivery"] is not None else None
	prev_read_rate = round(prev_rates["read"] * 100, 1) if prev_rates["read"] is not None else None

	prev_reply_info = calculate_reply_rate(account_name, prev_start_datetime, prev_end_datetime)
	prev_replied = prev_reply_info.get("contacts_replied", 0)
	prev_reply_rate = prev_reply_info.get("reply_rate", 0.0)

	# 7. Quality rating and messaging tier from WhatsApp Account / Phone Number
	quality_raw = "UNKNOWN"
	messaging_limit_tier = ""

	if can(ACCOUNT_DOCTYPE):
		account_filter = "AND a.name = %(account)s" if account_name else ""
		phone_rows = frappe.db.sql(
			f"""
			SELECT
				p.quality_rating,
				p.messaging_limit_tier,
				p.is_default_outgoing,
				p.status,
				a.account_name,
				a.name AS account_id
			FROM `tabWhatsApp Phone Number` p
			JOIN `tabWhatsApp Account` a ON a.name = p.parent
			WHERE a.docstatus = 0
			{account_filter}
			ORDER BY p.is_default_outgoing DESC, p.idx ASC
			""",
			{"account": account_name} if account_name else {},
			as_dict=True,
		)
		if phone_rows:
			quality_rank = {"RED": 1, "LOW": 1, "YELLOW": 2, "MEDIUM": 2, "GREEN": 3, "HIGH": 3, "UNKNOWN": 4}

			def _get_p_qual(p):
				return (p.get("quality_rating") if isinstance(p, dict) else getattr(p, "quality_rating", None)) or ""

			def _get_p_tier(p):
				return (p.get("messaging_limit_tier") if isinstance(p, dict) else getattr(p, "messaging_limit_tier", None)) or ""

			sorted_by_qual = sorted(
				[p for p in phone_rows if _get_p_qual(p)],
				key=lambda x: quality_rank.get(_get_p_qual(x).upper(), 5),
			)
			picked_phone = sorted_by_qual[0] if sorted_by_qual else phone_rows[0]
			quality_raw = _get_p_qual(picked_phone) or "UNKNOWN"
			messaging_limit_tier = _get_p_tier(picked_phone)

	# 8. Pure rule-based Aivo facts
	aivo_facts = get_whatsapp_aivo_facts(
		rejected_templates=rejected_templates,
		quality_rating=quality_raw,
		category_metrics=category_rollup,
	)

	# 9. Recent broadcasts (bottom table)
	recent_bulks = []
	if can(BULK_MESSAGE_DOCTYPE):
		bulk_filters = {"whatsapp_account": account_name} if account_name else {}
		recent_bulks = frappe.get_list(
			BULK_MESSAGE_DOCTYPE,
			fields=[
				"name",
				"title",
				"status",
				"template",
				"recipient_count",
				"sent_count",
				"scheduled_time",
				"modified",
			],
			filters=bulk_filters,
			order_by="modified desc",
			limit=10,
		)
		if recent_bulks and can(CHANNEL_MESSAGE_DOCTYPE):
			bulk_names = [b.name for b in recent_bulks]
			tpl_names = [b.template for b in recent_bulks if b.template]
			tpl_cat_map = {}
			if tpl_names and can(TEMPLATE_DOCTYPE):
				tpl_objs = frappe.get_all(
					TEMPLATE_DOCTYPE, filters={"name": ["in", tpl_names]}, fields=["name", "category"]
				)
				for to in tpl_objs:
					tpl_cat_map[to.name] = CAT_MAP.get((to.category or "").upper(), to.category or "Marketing")

			bm_stats = frappe.db.sql(
				"""
				SELECT
					reference_name,
					SUM(CASE WHEN status IN ('sent','delivered','read') THEN 1 ELSE 0 END) AS sent,
					SUM(CASE WHEN status IN ('delivered','read') THEN 1 ELSE 0 END) AS delivered,
					SUM(CASE WHEN status = 'read' THEN 1 ELSE 0 END) AS read_count
				FROM `tabChannel Message`
				WHERE reference_doctype = %(doctype)s AND reference_name IN %(names)s
				GROUP BY reference_name
				""",
				{"doctype": BULK_MESSAGE_DOCTYPE, "names": tuple(bulk_names)},
				as_dict=True,
			)
			bm_stats_map = {row.get("reference_name"): row for row in (bm_stats or [])}

			for b in recent_bulks:
				b_name = b.get("name") if isinstance(b, dict) else b.name
				b_template = b.get("template") if isinstance(b, dict) else b.template
				b_status = b.get("status") if isinstance(b, dict) else b.status
				b_rec = int(b.get("recipient_count") if isinstance(b, dict) else (b.recipient_count or 0))
				b_sent = int(b.get("sent_count") if isinstance(b, dict) else (b.sent_count or 0))

				st = bm_stats_map.get(b_name, {})
				b["purpose"] = tpl_cat_map.get(b_template, "Marketing")
				b["delivered"] = st.get("delivered") or 0
				b["read"] = st.get("read_count") or 0
				b["replied"] = 0
				if b_status == "Completed":
					deliv = int(b["delivered"])
					b["outcome"] = f"{round((deliv / b_rec) * 100)}% delivered" if b_rec else "Completed"
				elif b_status in ("Queued", "In Progress"):
					b["outcome"] = f"{b_sent} / {b_rec}"
				else:
					b["outcome"] = b_status or "Draft"

	return {
		"metrics": {
			"templates": count(TEMPLATE_DOCTYPE),
			"recipients": count(RECIPIENT_LIST_DOCTYPE),
			"activeBroadcasts": count(BULK_MESSAGE_DOCTYPE, {"status": ["in", ["Queued", "In Progress"]]}),
			"messagesSent": total_sent,
			"deliveryRate": round(delivery_rate) if total_sent > 0 else 0,
			"activeFlows": count(FLOW_DOCTYPE, {"status": "Published"}),
		},
		"summary": {
			"sent": total_sent,
			"recipients": count(RECIPIENT_LIST_DOCTYPE),
			"lists": count(RECIPIENT_LIST_DOCTYPE),
			"quality": _format_quality_rating(quality_raw),
			"quality_raw": quality_raw,
			"prevQuality": _format_quality_rating(quality_raw),
			"delivered": total_delivered,
			"deliveredPct": delivery_rate,
			"read": total_read,
			"readPct": read_rate,
			"replied": replied,
			"replyPct": reply_rate,
			"templatesApproved": approved_count,
			"templatesTotal": total_templates,
			"templatesRejected": rejected_count,
			"templatesPending": pending_count,
			"tier": _format_messaging_tier(messaging_limit_tier),
		},
		"previous_period": {
			"sent": prev_sent,
			"delivered": prev_delivered,
			"read": prev_read,
			"delivery_rate": prev_delivery_rate,
			"read_rate": prev_read_rate,
			"replied": prev_replied,
			"reply_rate": prev_reply_rate,
		},
		"category_rollup": category_rollup,
		"delivery_health": {
			"sent": total_sent,
			"delivered": total_delivered,
			"delivered_pct": delivery_rate,
			"read": total_read,
			"read_pct": read_rate,
			"conversations_opened": conversations_opened,
			"reply_rate": reply_rate,
		},
		"account_standing": {
			"quality_rating": _format_quality_rating(quality_raw),
			"quality_raw": quality_raw,
			"tier": _format_messaging_tier(messaging_limit_tier),
			"templates": [
				{"label": "Approved", "n": approved_count, "dot": "var(--success, #10B981)"},
				{"label": "Pending", "n": pending_count, "dot": "var(--warning, #F59E0B)"},
				{"label": "Rejected", "n": rejected_count, "dot": "var(--danger, #EF4444)"},
			],
		},
		"aivo_facts": aivo_facts,
		"period": {
			"period": period_label,
			"start_date": str(current_since),
			"end_date": str(current_until),
		},
		"recent_templates": recent_tpls,
		"recent_broadcasts": recent_bulks,
	}


@frappe.whitelist()
def get_waba_accounts() -> list:
	check_read(ACCOUNT_DOCTYPE)
	return frappe.get_all(
		ACCOUNT_DOCTYPE,
		fields=["name", "account_name", "status", "needs_reauth", "waba_id", "last_verified_at"],
		limit=100,
	)


@frappe.whitelist()
def verify_waba_connection(account_name: str) -> dict:
	"""Check the stored token against Meta and update health fields.

	Surfaces in the UI as a "Verify" action on a connected WABA -- the
	only permission check we can do client-side without the Meta app
	secret (only the provider holds that). See `client.verify_token`'s
	docstring.
	"""
	check_read(ACCOUNT_DOCTYPE, account_name)

	from msuite_whatsapp.integrations.meta.client import verify_token
	from msuite_whatsapp.queries import account_repository as accounts

	result = verify_token(account_name)
	now = frappe.utils.now_datetime()

	if result["ok"]:
		frappe.db.set_value(
			ACCOUNT_DOCTYPE,
			account_name,
			{
				"last_verified_at": now,
				"needs_reauth": 0,
				"last_token_error": "",
			},
			update_modified=False,
		)
	else:
		accounts.set_reauth_flag(account_name, needs_reauth=True, error=result["error"])

	frappe.db.commit()
	return result


@frappe.whitelist()
def get_languages_list() -> list:
	check_read("Language")
	return frappe.get_all(
		"Language",
		fields=["name", "language_name"],
		limit=300,
		order_by="language_name asc",
	)


@frappe.whitelist()
def get_waba_phone_numbers(waba_name: str) -> list:
	check_read(ACCOUNT_DOCTYPE, waba_name)
	doc = frappe.get_doc(ACCOUNT_DOCTYPE, waba_name)
	out = []
	if doc.phones:
		for p in doc.phones:
			out.append(
				{
					"id": p.phone_number_id or p.name,
					"number": p.display_phone_number or p.name,
				}
			)
	return out


@frappe.whitelist()
def get_country_dialing_codes() -> list:
	# perm: static country metadata, no data
	from frappe.geo.country_info import get_all

	countries = get_all()
	out = []
	for name, info in countries.items():
		if info.get("isd"):
			out.append(
				{
					"name": name,
					"code": (info.get("code") or "").upper(),
					"isd": info.get("isd"),
				}
			)
	out.sort(key=lambda x: x["name"])
	return out
