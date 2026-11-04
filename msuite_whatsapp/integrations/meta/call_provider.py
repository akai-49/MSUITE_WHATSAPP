"""
WhatsApp Calling API provider — the Meta Graph API call-action HTTP call.

Extracted from `api/v1/whatsapp/calls.py` (see WHATSAPP_REFACTOR_PLAN.md
§7/§9). Calling actions go directly from client to Meta (not proxied
through the provider) — only webhooks are forwarded by the provider.
"""

from __future__ import annotations

import frappe
import requests
from frappe import _

from msuite_whatsapp.services.channels.inbox_channel import is_bsuid
from msuite_whatsapp.services.domain import GRAPH_API_BASE, REQUEST_TIMEOUT
from msuite_whatsapp.queries import account_repository as accounts


def meta_call_action(
	wa,
	action: str,
	call_id: str | None = None,
	sdp: str | None = None,
	sdp_type: str | None = None,
	to: str | None = None,
) -> dict:
	"""
	Send a call action to Meta's Graph API.

	Actions:
	  connect     — initiate outbound call (no call_id, sdp_type="offer")
	  pre_accept  — respond to inbound call with SDP answer
	  accept      — confirm WebRTC connection established
	  reject      — decline inbound call
	  terminate   — hang up active call

	Raises:
	    frappe.ValidationError on Meta API error
	"""
	phone_number_id = accounts.get_phone_number_id(wa, "outgoing")
	token = wa.get_password("token")

	if not phone_number_id or not token:
		frappe.throw(_("WhatsApp Account missing phone number or token"))

	payload = {"messaging_product": "whatsapp", "action": action}
	if call_id:
		payload["call_id"] = call_id
	if to:
		if is_bsuid(to):
			payload["recipient"] = to
		else:
			payload["to"] = to
	if sdp:
		payload["session"] = {"sdp": sdp, "sdp_type": sdp_type or "answer"}

	resp = requests.post(
		f"{GRAPH_API_BASE}/{phone_number_id}/calls",
		json=payload,
		headers={"Authorization": f"Bearer {token}"},
		timeout=REQUEST_TIMEOUT,
	)

	result = resp.json()
	if not resp.ok:
		error = result.get("error", {})
		msg = error.get("message", resp.text[:200])
		details = error.get("error_data", {}).get("details", "")
		frappe.throw(_("Meta API error: {0}").format(f"{msg} ({details})" if details else msg))

	return result


def get_calling_settings(wa) -> dict:
	"""Fetch this phone number's Calling configuration from Meta
	(`GET /{phone-number-id}/settings`). Read-only — safe to call to show
	current enablement status before an agent hits the "Calling API not
	enabled" (#138000) error on an actual call."""
	phone_number_id, token = _credentials(wa)
	resp = requests.get(
		f"{GRAPH_API_BASE}/{phone_number_id}/settings",
		headers={"Authorization": f"Bearer {token}"},
		timeout=REQUEST_TIMEOUT,
	)
	return _handle_settings_response(resp)


def enable_calling(wa) -> dict:
	"""Turn on Calling for this phone number
	(`POST /{phone-number-id}/settings`, `calling.status=ENABLED`).

	This only succeeds once Meta has made Calling available for the
	WABA/phone number — if the business hasn't accepted Calling terms in
	WhatsApp Manager yet, Meta rejects this with its own error, which is
	surfaced verbatim (not swallowed) so a failure here is a clear signal
	to finish enabling Calling manually in WhatsApp Manager first.
	"""
	phone_number_id, token = _credentials(wa)
	resp = requests.post(
		f"{GRAPH_API_BASE}/{phone_number_id}/settings",
		json={"calling": {"status": "ENABLED"}},
		headers={"Authorization": f"Bearer {token}"},
		timeout=REQUEST_TIMEOUT,
	)
	return _handle_settings_response(resp)


def _credentials(wa) -> tuple[str, str]:
	phone_number_id = accounts.get_phone_number_id(wa, "outgoing")
	token = wa.get_password("token")
	if not phone_number_id or not token:
		frappe.throw(_("WhatsApp Account missing phone number or token"))
	return phone_number_id, token


def _handle_settings_response(resp) -> dict:
	try:
		result = resp.json()
	except ValueError:
		result = {}
	if not resp.ok:
		error = result.get("error", {})
		msg = error.get("message", resp.text[:200])
		details = error.get("error_data", {}).get("details", "")
		frappe.throw(_("Meta API error: {0}").format(f"{msg} ({details})" if details else msg))
	return result
