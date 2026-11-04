"""
WhatsApp Block Users API provider.

Implements Meta Graph API block_users endpoint (POST / DELETE / GET /<PHONE_NUMBER_ID>/block_users).
Supports both standard phone numbers and business-scoped user IDs (BSUID).
Parent BSUIDs (e.g. US.ENT....) are rejected by Meta and raise a ValueError.
"""

from __future__ import annotations

from typing import Any

import frappe
import requests
from frappe import _

from msuite_whatsapp.services.domain import GRAPH_API_BASE, REQUEST_TIMEOUT
from msuite_whatsapp.queries import account_repository as accounts


def _build_block_list(identifiers: list[str]) -> list[dict[str, str]]:
	"""
	Convert a list of phone numbers or BSUIDs into the block_users payload structure.
	Meta expects:
	  {"user": "<phone_or_bsuid>"}
	Parent BSUIDs (".ENT.") are not permitted by Meta.
	"""
	block_list = []
	for ident in identifiers:
		val = str(ident).strip()
		if ".ENT." in val.upper():
			raise ValueError(f"Parent BSUID '{val}' cannot be blocked/unblocked per Meta documentation")
		block_list.append({"user": val})
	return block_list


def block_users(wa: Any, identifiers: list[str]) -> dict:
	"""
	Block one or more users (phone numbers or BSUIDs).

	POST /{phone_number_id}/block_users
	"""
	phone_number_id = accounts.get_phone_number_id(wa, "outgoing") or accounts.get_phone_number_id(wa)
	token = wa.get_password("token") if hasattr(wa, "get_password") else None

	if not phone_number_id or not token:
		frappe.throw(_("WhatsApp Account missing phone number or token"))

	block_list = _build_block_list(identifiers)
	payload = {
		"messaging_product": "whatsapp",
		"block_users": block_list,
	}

	resp = requests.post(
		f"{GRAPH_API_BASE}/{phone_number_id}/block_users",
		json=payload,
		headers={"Authorization": f"Bearer {token}"},
		timeout=REQUEST_TIMEOUT,
	)

	result = resp.json() if resp.content else {}
	if not resp.ok:
		error = result.get("error", {})
		msg = error.get("message", resp.text[:200])
		frappe.throw(_("Meta API error: {0}").format(msg))

	return result


def unblock_users(wa: Any, identifiers: list[str]) -> dict:
	"""
	Unblock one or more users (phone numbers or BSUIDs).

	DELETE /{phone_number_id}/block_users
	"""
	phone_number_id = accounts.get_phone_number_id(wa, "outgoing") or accounts.get_phone_number_id(wa)
	token = wa.get_password("token") if hasattr(wa, "get_password") else None

	if not phone_number_id or not token:
		frappe.throw(_("WhatsApp Account missing phone number or token"))

	block_list = _build_block_list(identifiers)
	payload = {
		"messaging_product": "whatsapp",
		"block_users": block_list,
	}

	resp = requests.delete(
		f"{GRAPH_API_BASE}/{phone_number_id}/block_users",
		json=payload,
		headers={"Authorization": f"Bearer {token}"},
		timeout=REQUEST_TIMEOUT,
	)

	result = resp.json() if resp.content else {}
	if not resp.ok:
		error = result.get("error", {})
		msg = error.get("message", resp.text[:200])
		frappe.throw(_("Meta API error: {0}").format(msg))

	return result


def get_blocked_users(wa: Any) -> dict:
	"""
	List currently blocked users.

	GET /{phone_number_id}/block_users
	"""
	phone_number_id = accounts.get_phone_number_id(wa, "outgoing") or accounts.get_phone_number_id(wa)
	token = wa.get_password("token") if hasattr(wa, "get_password") else None

	if not phone_number_id or not token:
		frappe.throw(_("WhatsApp Account missing phone number or token"))

	resp = requests.get(
		f"{GRAPH_API_BASE}/{phone_number_id}/block_users",
		headers={"Authorization": f"Bearer {token}"},
		timeout=REQUEST_TIMEOUT,
	)

	result = resp.json() if resp.content else {}
	if not resp.ok:
		error = result.get("error", {})
		msg = error.get("message", resp.text[:200])
		frappe.throw(_("Meta API error: {0}").format(msg))

	return result
