"""What Automation asks WhatsApp for, through the msuite_automation_steps hook."""

from __future__ import annotations


def claim_send_slot(account: str | None, recipient: str) -> bool:
	"""Take a slot in the portfolio's messaging limit. False means retry later."""
	from msuite_whatsapp.services.bulk.rate_limit_service import claim_for_account

	return claim_for_account(account, recipient)


def _phone_candidates(phone: str) -> list[str]:
	"""Spellings of a phone number or BSUID that stored handles may use (raw, digits, +digits)."""
	clean = str(phone).strip()
	digits = "".join(c for c in clean if c.isdigit())
	return list({clean, digits, f"+{digits}"} - {"", "+"})


def has_marketing_consent(phone: str) -> bool:
	"""Check if a recorded positive WhatsApp opt-in exists for a phone number or BSUID.

	Consent means a Channel Handle with opted_in = 1 (matched on platform handle or
	BSUID), or a Contact (phone_e164 / mobile_no / phone) that is not unsubscribed
	from WhatsApp and has consent_updated_at set. An opt-out always wins.

	Args:
		phone: Recipient phone number or BSUID.

	Returns:
		bool: True when consent is recorded and the recipient is not opted out.

	Raises:
		None.

	Side Effects:
		None.
	"""
	import frappe

	if not phone or is_opted_out(phone):
		return False
	# A BSUID matches only itself: digit-stripping it could hit someone else's phone handle.
	from msuite_core.utils.phone import is_bsuid

	candidates = [str(phone).strip()] if is_bsuid(phone) else _phone_candidates(phone)
	for field in ("platform_handle", "bsuid"):
		if frappe.db.exists("Channel Handle", {"channel_type": "WhatsApp", field: ["in", candidates], "opted_in": 1}):
			return True
	for field in ("phone_e164", "mobile_no", "phone"):
		if frappe.db.exists(
			"Contact",
			{field: ["in", candidates], "unsubscribed_whatsapp": 0, "consent_updated_at": ["is", "set"]},
		):
			return True
	return False


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

	candidates = _phone_candidates(phone)
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
