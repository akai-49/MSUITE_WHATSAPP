"""WhatsApp Accounts in the global search."""

import frappe


def search(q: str, limit: int) -> dict | None:
	wa_accounts = frappe.db.get_list(
		"WhatsApp Account",
		filters=[["account_name", "like", f"%{q}%"]],
		fields=["name", "account_name", "waba_name", "status"],
		limit=limit,
	)
	if not wa_accounts:
		wa_accounts = frappe.db.get_list(
			"WhatsApp Account",
			filters=[["waba_name", "like", f"%{q}%"]],
			fields=["name", "account_name", "waba_name", "status"],
			limit=limit,
		)
	if wa_accounts:
		return (
			{
				"category": "WhatsApp",
				"icon": "brand-whatsapp",
				"items": [
					{
						"name": r.name,
						"title": r.account_name or r.name,
						"subtitle": r.waba_name or r.status or "WhatsApp Account",
						"route": "/whatsapp",
					}
					for r in wa_accounts
				],
			}
		)
