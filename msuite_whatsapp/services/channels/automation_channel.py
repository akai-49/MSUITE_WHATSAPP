"""What Automation asks WhatsApp for, through the msuite_automation_steps hook."""

from __future__ import annotations


def claim_send_slot(account: str | None, recipient: str) -> bool:
	"""Take a slot in the portfolio's messaging limit. False means retry later."""
	from msuite_whatsapp.services.bulk.rate_limit_service import claim_for_account

	return claim_for_account(account, recipient)


def is_opted_out(phone: str) -> bool:
	from msuite_whatsapp.services.bulk import bulk_send_service

	return bulk_send_service.is_opted_out(phone)


def queue_bulk(bulk_doc) -> None:
	from msuite_whatsapp.services.bulk import bulk_send_service

	bulk_send_service.queue_messages(bulk_doc)


def send_one_bulk(bulk_doc, recipient: dict) -> None:
	from msuite_whatsapp.services.bulk import bulk_send_service

	bulk_send_service.create_single_message(bulk_doc, recipient)
