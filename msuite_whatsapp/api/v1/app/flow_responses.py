"""WhatsApp Flow Response API — Vue SPA-facing read/delete access to
captured Flow submissions. Writes happen only server-side, from
`flow_response_service.py` (send-time `mark_sent` + inbound
`capture_from_message`) — there is deliberately no save/update endpoint
here, the SPA only ever reads and deletes these records.
"""

from __future__ import annotations

import json

import frappe

from msuite_core.services.permissions.checks import check_delete, check_read

DOCTYPE = "WhatsApp Flow Response"


@frappe.whitelist()
def list_flow_responses(flow: str = "", status: str = "", filters: str = "[]", limit: int = 100) -> list:
	check_read(DOCTYPE)

	parsed_filters = json.loads(filters or "[]")
	if flow:
		parsed_filters.append(["flow", "=", flow])
	if status:
		parsed_filters.append(["status", "=", status])

	return frappe.get_all(
		DOCTYPE,
		fields=[
			"name",
			"flow",
			"flow_name_snapshot",
			"whatsapp_account",
			"status",
			"contact_phone",
			"contact_name",
			"flow_token",
			"sent_at",
			"completed_at",
			"modified",
		],
		filters=parsed_filters,
		order_by="modified desc",
		limit=limit,
	)


@frappe.whitelist()
def get_flow_response(name: str) -> dict:
	check_read(DOCTYPE, name)
	return frappe.get_doc(DOCTYPE, name).as_dict()


@frappe.whitelist()
def get_flow_response_metrics(flow: str = "") -> dict:
	check_read(DOCTYPE)

	base_filters = {"flow": flow} if flow else {}
	sent = frappe.db.count(DOCTYPE, {**base_filters, "status": "Sent"})
	completed = frappe.db.count(DOCTYPE, {**base_filters, "status": "Completed"})
	total = sent + completed

	return {
		"total": total,
		"sent": sent,
		"completed": completed,
		"completion_rate": round((completed / total) * 100, 1) if total else 0,
	}


@frappe.whitelist()
def delete_flow_response(name: str) -> dict:
	check_delete(DOCTYPE, name)
	frappe.delete_doc(DOCTYPE, name)
	frappe.db.commit()
	return {"status": "success"}


@frappe.whitelist()
def bulk_delete_flow_responses(names: str | list) -> dict:
	"""Batch delete multiple WhatsApp flow responses."""
	name_list = json.loads(names) if isinstance(names, str) else (names or [])
	deleted, failed = [], []
	for name in name_list:
		if not frappe.has_permission(DOCTYPE, "delete", doc=name):
			failed.append({"name": name, "reason": "No delete permission"})
			continue
		try:
			frappe.delete_doc(DOCTYPE, name, force=True)
			deleted.append(name)
		except Exception as e:
			frappe.log_error(title="bulk_delete_flow_responses", message=str(e))
			failed.append({"name": name, "reason": str(e)})
	frappe.db.commit()
	return {"deleted": deleted, "failed": failed}

