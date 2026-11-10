"""What Automation asks WhatsApp for, through the msuite_automation_steps hook."""

from __future__ import annotations


def claim_send_slot(account: str | None, recipient: str) -> bool:
	"""Take a slot in the portfolio's messaging limit. False means retry later."""
	from msuite_whatsapp.services.bulk.rate_limit_service import claim_for_account

	return claim_for_account(account, recipient)


def is_opted_out(phone: str) -> bool:
	"""Check if a phone number or handle is opted out of WhatsApp.

	Args:
		phone: Recipient phone number or channel handle identifier.

	Returns:
		bool: True if opted out via Audience Member or Channel Handle metadata.

	Raises:
		None.

	Side Effects:
		None.
	"""
	from msuite_whatsapp.services.bulk import bulk_send_service

	if not phone:
		return False
	if bulk_send_service.is_opted_out(phone):
		return True

	import json
	import frappe

	clean = str(phone).strip()
	digits = "".join(c for c in clean if c.isdigit())
	candidates = list({clean, digits, f"+{digits}"} - {"", "+"})
	handles = frappe.get_all(
		"Channel Handle",
		filters={"channel_type": "WhatsApp", "platform_handle": ["in", candidates]},
		fields=["name", "metadata"],
	) or []
	if not handles:
		handles = frappe.get_all(
			"Channel Handle",
			filters={"channel_type": "WhatsApp", "bsuid": ["in", candidates]},
			fields=["name", "metadata"],
		) or []
	for h in handles:
		meta = h.get("metadata") if isinstance(h, dict) else getattr(h, "metadata", None)
		if isinstance(meta, str):
			try:
				meta = json.loads(meta)
			except Exception:
				meta = {}
		if isinstance(meta, dict) and meta.get("opted_out") in (True, 1, "1", "true", "True"):
			return True
	return False


def queue_bulk(bulk_doc) -> None:
	from msuite_whatsapp.services.bulk import bulk_send_service

	bulk_send_service.queue_messages(bulk_doc)


def send_one_bulk(bulk_doc, recipient: dict) -> None:
	from msuite_whatsapp.services.bulk import bulk_send_service

	bulk_send_service.create_single_message(bulk_doc, recipient)
