"""
WhatsApp Consent API — bulk opt-in / opt-out management.
"""

from __future__ import annotations

import json
import re

import frappe
from frappe import _

from msuite_campaigns.audience.services.contact_sync_service import (
	record_channel_opt_in,
	record_channel_opt_out,
)
from msuite_whatsapp.services.validation import phone as phone_validator
from msuite_whatsapp.services.permissions.checks import check_write

RECIPIENT_LIST_DOCTYPE = "WhatsApp Recipient List"
MAX_NUMBERS_PER_CALL = 5000


@frappe.whitelist()
def bulk_set_whatsapp_consent(numbers, action: str) -> dict:
	"""Bulk update WhatsApp consent (opt-in or opt-out).

	Args:
		numbers: list of phone numbers, or pasted text (newline/comma separated),
		         or JSON-encoded string list.
		action: 'opt_in' or 'opt_out'.

	Returns:
		dict: {"updated": int, "not_found": int, "invalid": int}
	"""
	check_write(RECIPIENT_LIST_DOCTYPE)

	action = (action or "").strip().lower()
	if action not in ("opt_in", "opt_out"):
		frappe.throw(_("Invalid action: {0}. Must be 'opt_in' or 'opt_out'.").format(action), frappe.ValidationError)

	raw_items = []
	is_json_list = False
	if isinstance(numbers, str):
		text = numbers.strip()
		if text.startswith("[") and text.endswith("]"):
			try:
				parsed = json.loads(text)
				if isinstance(parsed, list):
					raw_items, is_json_list = parsed, True
			except Exception:
				pass
		if not is_json_list and text:
			raw_items = [item.strip() for item in re.split(r"[\r\n,]+", text) if item.strip()]
	elif isinstance(numbers, (list, tuple)):
		raw_items = list(numbers)

	if len(raw_items) > MAX_NUMBERS_PER_CALL:
		frappe.throw(
			_("Cannot process more than {0} numbers per call.").format(MAX_NUMBERS_PER_CALL),
			frappe.ValidationError,
		)

	updated = 0
	not_found = 0
	invalid = 0
	seen: set[str] = set()

	for item in raw_items:
		item_str = str(item).strip() if item is not None else ""
		if not item_str:
			continue

		verdict = phone_validator.normalize(item_str)
		e164 = verdict.get("e164")
		if verdict.get("status") != phone_validator.VALID or not e164:
			invalid += 1
			continue

		if e164 in seen:
			continue
		seen.add(e164)

		if action == "opt_in":
			ok = record_channel_opt_in("WhatsApp", e164, reason="Bulk consent update")
		else:
			ok = record_channel_opt_out("WhatsApp", e164, reason="Bulk consent update", create_if_missing=False)

		if ok:
			updated += 1
		else:
			not_found += 1

	return {
		"updated": updated,
		"not_found": not_found,
		"invalid": invalid,
	}
