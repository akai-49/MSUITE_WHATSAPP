"""WhatsApp broadcasts in the Home page's recent list."""

from __future__ import annotations

import frappe


def recent_broadcasts() -> list[dict]:
	recent_items = []
	if frappe.db.exists("DocType", "Bulk WhatsApp Message") and frappe.has_permission("Bulk WhatsApp Message", "read"):
		wa_msgs = frappe.get_list(
			"Bulk WhatsApp Message",
			fields=["name", "title", "status", "modified"],
			order_by="modified desc",
			limit=2,
		)
		for w in wa_msgs:
			recent_items.append(
				{
					"id": w.name,
					"type": "WhatsApp Message",
					"title": w.title or w.name,
					"status": w.status or "Draft",
					"route_name": "WhatsAppBulkMessages",
					"modified": str(w.modified),
				}
			)
	return recent_items
