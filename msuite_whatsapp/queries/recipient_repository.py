"""WhatsApp Recipient / Recipient List repository — DB-only access."""

from __future__ import annotations

import frappe

RECIPIENT_DOCTYPE = "WhatsApp Recipient"
RECIPIENT_LIST_DOCTYPE = "WhatsApp Recipient List"


def count_recipients(list_name: str) -> int:
	return frappe.db.count(RECIPIENT_DOCTYPE, {"parent": list_name, "parenttype": RECIPIENT_LIST_DOCTYPE})


def list_recipients(list_name: str, fields: list[str] | None = None) -> list[dict]:
	return frappe.get_all(
		RECIPIENT_DOCTYPE,
		filters={"parent": list_name},
		fields=fields or ["mobile_number", "recipient_name", "recipient_data"],
	)


def existing_mobiles(list_name: str) -> set[str]:
	return set(
		frappe.get_all(
			RECIPIENT_DOCTYPE,
			filters={"parent": list_name},
			pluck="mobile_number",
		)
	)


def mobile_exists_in_list(list_name: str, mobile_number: str, exclude_name: str | None = None) -> bool:
	filters = {"parent": list_name, "mobile_number": mobile_number}
	if exclude_name:
		filters["name"] = ("!=", exclude_name)
	return bool(frappe.db.exists(RECIPIENT_DOCTYPE, filters))


def recipient_data_samples(list_name: str, limit: int = 100) -> list[dict]:
	return frappe.get_all(
		RECIPIENT_DOCTYPE,
		filters={"parent": list_name},
		fields=["recipient_data"],
		limit=limit,
	)
