"""Phone helpers for msuite_whatsapp."""

from __future__ import annotations

import re
from typing import Any
import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat


def format_number(number: Any) -> Any:
	"""Strip leading '+' from a phone number string if present."""
	return number.lstrip("+") if isinstance(number, str) else number


_BSUID_RE = re.compile(r"[A-Za-z]{2}\.(?:ENT\.)?[A-Za-z0-9]{1,128}", re.IGNORECASE)


def is_bsuid(value: Any) -> bool:
	"""True when `value` is a well-formed (parent) business-scoped user id."""
	return isinstance(value, str) and bool(_BSUID_RE.fullmatch(value.strip()))


def customer_phone(platform_handle: str | None) -> str:
	"""The phone a Channel Handle's platform_handle stands for.
	Empty string if handle is a BSUID, else platform_handle."""
	return "" if is_bsuid(platform_handle) else (platform_handle or "")


def normalize_phone(phone: Any) -> str:
	"""Digits only, no leading '+' or formatting. Returns empty string for BSUIDs."""
	if not phone or is_bsuid(phone):
		return ""
	return "".join(c for c in str(phone) if c.isdigit())


_MOBILE_RE = re.compile(r"^\+?\d{10,15}$")
_isd_codes_cache = None


def _isd_codes():
	global _isd_codes_cache
	if _isd_codes_cache is None:
		try:
			from frappe.geo.country_info import get_all
			codes = []
			for country_name, info in get_all().items():
				isd = (info.get("isd") or "").lstrip("+")
				if isd:
					codes.append((isd, country_name))
			codes.sort(key=lambda c: -len(c[0]))
			_isd_codes_cache = codes
		except Exception:
			_isd_codes_cache = []
	return _isd_codes_cache


def match_country_code(digits: str) -> tuple[str | None, str | None]:
	for isd, country_name in _isd_codes():
		if digits.startswith(isd):
			return country_name, isd
	return None, None


def clean_mobile(raw: str | None, default_region: str | None = None) -> tuple[str | None, str | None]:
	if not raw:
		return None, "Empty"
	if is_bsuid(raw):
		return None, "BSUID recipients are not supported for bulk/import messaging (phone numbers only)"

	mobile = "".join(c for c in str(raw) if c.isdigit() or c == "+")
	if "+" in mobile[1:]:
		mobile = mobile[0] + mobile[1:].replace("+", "")
	if _MOBILE_RE.match(mobile):
		return mobile, None

	return None, f"Invalid mobile number format: {raw}"
