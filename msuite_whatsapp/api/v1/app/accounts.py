"""
WhatsApp Account API — WABA helper dropdowns + the cross-domain dashboard.

Relocated from `api/v1/whatsapp/crud.py` (see WHATSAPP_REFACTOR_PLAN.md §9).
The dotted path `msuite_whatsapp.api.v1.app.crud.*` is preserved via
a re-export shim in that module since the SPA calls it by that exact path.
"""

import frappe

from msuite_core.services.permissions.checks import check_read, check_write

ACCOUNT_DOCTYPE = "WhatsApp Account"
TEMPLATE_DOCTYPE = "WhatsApp Templates"
RECIPIENT_LIST_DOCTYPE = "WhatsApp Recipient List"
BULK_MESSAGE_DOCTYPE = "Bulk WhatsApp Message"
FLOW_DOCTYPE = "WhatsApp Flow"


@frappe.whitelist()
def get_dashboard_metrics() -> dict:
	"""Dashboard cards + recent lists, each gated on its own doctype.

	BUG-023: this used to `check_read` all four doctypes up front, so a role
	missing just one (WhatsApp Manager had no read on WhatsApp Flow) failed the
	whole call and the dashboard showed "No templates/broadcasts yet". Now a
	missing permission only empties its own section, and counts/lists go
	through get_list so they respect user permissions.
	"""

	def can(doctype):
		return frappe.has_permission(doctype, "read")

	def count(doctype, filters=None):
		# ponytail: fetches names to count; fine for these small tables
		return len(frappe.get_list(doctype, filters=filters or {}, pluck="name")) if can(doctype) else 0

	total_sent = total_delivered = 0
	if can(TEMPLATE_DOCTYPE):
		sent_sum = frappe.db.sql(
			"SELECT sum(total_sent) AS total_sent, sum(total_delivered) AS total_delivered "
			"FROM `tabWhatsApp Templates`",
			as_dict=True,
		)
		total_sent = (sent_sum and sent_sum[0].total_sent) or 0
		total_delivered = (sent_sum and sent_sum[0].total_delivered) or 0

	recent_tpls = (
		frappe.get_list(
			TEMPLATE_DOCTYPE,
			fields=["name", "template_name", "status", "category", "language", "modified"],
			order_by="modified desc",
			limit=5,
		)
		if can(TEMPLATE_DOCTYPE)
		else []
	)

	recent_bulks = (
		frappe.get_list(
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
			order_by="modified desc",
			limit=5,
		)
		if can(BULK_MESSAGE_DOCTYPE)
		else []
	)

	return {
		"metrics": {
			"templates": count(TEMPLATE_DOCTYPE),
			"recipients": count(RECIPIENT_LIST_DOCTYPE),
			"activeBroadcasts": count(BULK_MESSAGE_DOCTYPE, {"status": ["in", ["Queued", "In Progress"]]}),
			"messagesSent": total_sent,
			"deliveryRate": round((total_delivered / total_sent) * 100) if total_sent > 0 else 0,
			"activeFlows": count(FLOW_DOCTYPE, {"status": "Published"}),
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
