"""Phone validation helpers."""

from __future__ import annotations

from typing import Any
import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat

VALID = "valid"
INVALID = "invalid"


def get_system_default_region() -> str:
	try:
		country = frappe.db.get_single_value("System Settings", "country")
		if country:
			from frappe.geo.country_info import get_all
			info = get_all().get(country)
			if info and info.get("code"):
				return info["code"].upper()
	except Exception:
		pass
	return "US"


def normalize(number: Any, region: str = "US") -> dict[str, Any]:
	if not number:
		return {"status": INVALID, "e164": None, "reason": "Empty number"}
	try:
		parsed = phonenumbers.parse(str(number), region.upper() if region else None)
		if phonenumbers.is_valid_number(parsed):
			e164 = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
			return {"status": VALID, "e164": e164, "reason": None}
	except NumberParseException as e:
		return {"status": INVALID, "e164": None, "reason": str(e)}

	digits = "".join(c for c in str(number) if c.isdigit() or c == "+")
	if len(digits) >= 10:
		if not digits.startswith("+"):
			digits = "+" + digits
		return {"status": VALID, "e164": digits, "reason": None}

	return {"status": INVALID, "e164": None, "reason": f"Invalid number: {number}"}
