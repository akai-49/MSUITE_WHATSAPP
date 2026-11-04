"""
WhatsApp Account / Phone repository.

Single source of truth for resolving accounts, phone numbers, and
credentials. Consolidates three previously-duplicated phone-ID
resolvers (`whatsapp_account.py::get_default_phone`,
`utils/send.py::_phone_id`, `utils/media.py::_get_phone_id`) into one
implementation.

No HTTP calls live here — only `frappe.db` / `frappe.get_doc` reads.
Providers call into this module for credentials; they never resolve
accounts themselves.
"""

from __future__ import annotations

import frappe

from msuite_core.constants import GRAPH_API_URL, GRAPH_API_VERSION

ACCOUNT_DOCTYPE = "WhatsApp Account"
PHONE_CHILD_DOCTYPE = "WhatsApp Phone Number"
STATUS_ACTIVE = "Active"


def get_account_doc(account):
	"""Accept either a WhatsApp Account doc-name string or the doc itself.
	Falls back to default outgoing account if None, empty, or unresolvable."""
	if not account:
		account_name = find_default_account("outgoing")
		if not account_name:
			frappe.throw("No active WhatsApp Account found.")
		return frappe.get_doc(ACCOUNT_DOCTYPE, account_name)
	if isinstance(account, str):
		if not frappe.db.exists(ACCOUNT_DOCTYPE, account):
			account_name = find_default_account("outgoing")
			if not account_name:
				frappe.throw(f"WhatsApp Account {account!r} not found.")
			return frappe.get_doc(ACCOUNT_DOCTYPE, account_name)
		return frappe.get_doc(ACCOUNT_DOCTYPE, account)
	return account


def get_credentials(account) -> tuple[str, str, str]:
	"""Returns (base_url, version, token). Throws if no token is configured."""
	doc = get_account_doc(account)
	token = doc.get_password("token", raise_exception=False) or ""
	if not token:
		frappe.throw(f"WhatsApp Account {doc.name!r} has no token configured.")
	return GRAPH_API_URL, GRAPH_API_VERSION, token


def get_default_phone(account, phone_type: str = "outgoing"):
	"""
	Get the default phone child row for sending/receiving.

	Args:
	    account: WhatsApp Account doc-name or doc.
	    phone_type: "outgoing" or "incoming"

	Returns:
	    WhatsApp Phone Number child row, or first Active phone, or None.
	"""
	doc = get_account_doc(account)
	field = "is_default_outgoing" if phone_type == "outgoing" else "is_default_incoming"
	for phone in doc.phones or []:
		if phone.get(field):
			return phone
	for phone in doc.phones or []:
		if phone.status == STATUS_ACTIVE:
			return phone
	return None


def get_phone_number_id(account, phone_type: str = "outgoing") -> str:
	"""Resolve the phone_number_id to use for outbound calls (Meta API path
	segment) from the `phones` child table; throws if there is no phone.

	This is the single resolver that replaces the three duplicated
	implementations called out in the architecture audit (§3, §9).
	"""
	doc = get_account_doc(account)
	phones = getattr(doc, "phones", None) or []
	if phones:
		field = "is_default_outgoing" if phone_type == "outgoing" else "is_default_incoming"
		for phone in phones:
			if getattr(phone, field, 0):
				return phone.phone_number_id
		return phones[0].phone_number_id
	frappe.throw(f"No phone_number_id configured on WhatsApp Account {doc.name!r}")


def find_account_by_phone_number_id(phone_number_id: str) -> str | None:
	"""Find the parent WhatsApp Account name for a given Meta phone_number_id.

	"""
	if not phone_number_id:
		return None
	return frappe.db.get_value(PHONE_CHILD_DOCTYPE, {"phone_number_id": phone_number_id}, "parent")


def get_display_phone_number(account_name: str) -> str:
	"""Display number of the account's default-outgoing phone, else its first
	phone; "" when it has none. Replaces the old flat `display_phone_number`."""
	rows = frappe.get_all(
		PHONE_CHILD_DOCTYPE,
		filters={"parent": account_name, "parenttype": ACCOUNT_DOCTYPE},
		fields=["display_phone_number"],
		order_by="is_default_outgoing desc, idx asc",
		limit=1,
	)
	return (rows[0].display_phone_number if rows else "") or ""


def find_default_phone_account(account_type: str = "incoming") -> str | None:
	"""Parent account of the Active phone flagged as the default for a direction."""
	phone_field = "is_default_incoming" if account_type == "incoming" else "is_default_outgoing"
	return frappe.db.get_value(PHONE_CHILD_DOCTYPE, {phone_field: 1, "status": STATUS_ACTIVE}, "parent")


def find_default_account(account_type: str = "incoming") -> str | None:
	"""Find the default account name for a direction ('incoming'/'outgoing').

	Checks the `phones` child table default flags first, then falls back to the
	first Active account.
	"""
	return find_default_phone_account(account_type) or frappe.db.get_value(
		ACCOUNT_DOCTYPE, {"status": STATUS_ACTIVE}, "name"
	)


def get_whatsapp_account(phone_id: str | None = None, account_type: str = "incoming"):
	"""
	Resolve a WhatsApp Account document by phone_number_id or default type.

	Canonical implementation — `whatsapp.utils.get_whatsapp_account` is a
	backward-compatible re-export of this function.

	Args:
	    phone_id: Meta phone_number_id to look up.
	    account_type: 'incoming' or 'outgoing' — used to find the default account.

	Returns:
	    WhatsApp Account document, or None.
	"""
	if phone_id:
		account_name = find_account_by_phone_number_id(phone_id)
		if account_name:
			return frappe.get_doc(ACCOUNT_DOCTYPE, account_name)

	default_name = find_default_account(account_type)
	if default_name:
		return frappe.get_doc(ACCOUNT_DOCTYPE, default_name)

	return None


def is_account_active(account_name: str) -> bool:
	return frappe.db.get_value(ACCOUNT_DOCTYPE, account_name, "status") == STATUS_ACTIVE


def find_active_account(exclude: str | None = None) -> str | None:
	filters = {"status": STATUS_ACTIVE}
	if exclude:
		filters["name"] = ["!=", exclude]
	return frappe.db.get_value(ACCOUNT_DOCTYPE, filters, "name")


def list_active_accounts(fields: list[str] | None = None) -> list[dict]:
	return frappe.get_all(
		ACCOUNT_DOCTYPE,
		filters={"status": STATUS_ACTIVE},
		fields=fields or ["name", "waba_id", "business_id"],
	)


def set_reauth_flag(account_name: str, *, needs_reauth: bool, error: str = "") -> None:
	"""Persist token-health fields without bumping `modified` (used from
	background sync jobs that shouldn't trigger doc-change side effects)."""
	frappe.db.set_value(
		ACCOUNT_DOCTYPE,
		account_name,
		{
			"needs_reauth": 1 if needs_reauth else 0,
			"last_token_error": error,
			**({"last_token_error_at": frappe.utils.now_datetime()} if needs_reauth else {}),
		},
		update_modified=False,
	)
