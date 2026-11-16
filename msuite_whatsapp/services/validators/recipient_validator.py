"""
WhatsApp Recipient validators — mobile number cleaning, country-code
matching, and duplicate detection. Pure functions, no DB writes.
"""

from __future__ import annotations

import re

import frappe
from frappe import _

from msuite_whatsapp.utils.phone import clean_mobile, match_country_code


def validate_and_normalize_recipients(recipients, default_region: str | None = None) -> None:
	"""Clean + validate every recipient row and reject duplicates in place.

	Used by both `WhatsAppRecipientList.validate()` (the path that
	actually runs for desk-grid edits, CSV import, DocType import — see
	its docstring for why the child controller's own `validate()` isn't
	enough) and any other bulk-recipient entry point.
	"""
	from msuite_whatsapp.services.validation import phone as phone_validator

	region = (default_region or phone_validator.get_system_default_region()).upper()
	seen = {}
	for row in recipients or []:
		cleaned, error = clean_mobile(row.mobile_number, region)
		if error:
			frappe.throw(_("Row {0}: invalid mobile number ({1}).").format(row.idx, error))
		row.mobile_number = cleaned

		if cleaned.startswith("+"):
			country_name, _isd = match_country_code(cleaned[1:])
			row.country_code = country_name

		if cleaned in seen:
			frappe.throw(
				_("Duplicate mobile number {0} (rows {1} and {2}).").format(cleaned, seen[cleaned], row.idx)
			)
		seen[cleaned] = row.idx


def validate_single_mobile_number(mobile_number: str, default_region: str | None = None) -> str:
	"""Validate + clean a single mobile number, returning the cleaned value
	or raising. Used by `WhatsAppRecipient.validate()` for the standalone
	row-editor case."""
	cleaned, error = clean_mobile(mobile_number, default_region)
	if error:
		frappe.throw(_("Invalid mobile number: {0}").format(error))
	return cleaned
