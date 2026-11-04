"""
Legacy WhatsApp webhook endpoint — preserved for URL-level back-compat.

The provider still POSTs to this URL because every existing
`MSuite App.webhook_url` row points at it. Internally it just forwards
the payload to the inbox bridge which writes Channel Message + status.
The legacy WhatsApp Message write path was removed in the Phase E
cleanup; no more two-source-of-truth.

The endpoint stays here (rather than moving to
`inbox/api/v1/webhook.py`) to keep the public URL stable. New code
should call `msuite_whatsapp.services.webhooks.inbound_webhook.feed_whatsapp_payload`
directly.
"""

import frappe
from frappe import _
from werkzeug.wrappers import Response

from msuite_core.integrations.provider_auth import handle_verification_challenge, validate_provider_auth


@frappe.whitelist(allow_guest=True)
def webhook():
	"""Receive a WhatsApp webhook payload.

	GET: Meta verification challenge — the challenge is echoed only when
	     `hub.verify_token` matches `meta_webhook_verify_token` in site config.
	POST: provider auth validated, payload routed to the inbox bridge.
	"""
	challenge = handle_verification_challenge()
	if challenge is not None:
		return challenge

	validate_provider_auth()
	return post()


def post():
	"""Forward the payload to the inbox bridge."""
	import json

	data = None
	if frappe.request:
		data = frappe.request.get_json(silent=True)

	if not data:
		data = dict(frappe.local.form_dict)

	if isinstance(data, str):
		try:
			data = json.loads(data)
		except Exception:
			pass

	frappe.logger("msuite_workspace.inbox").debug(f"WhatsApp webhook payload: {data}")

	try:
		from msuite_whatsapp.services.webhooks.inbound_webhook import feed_whatsapp_payload

		feed_whatsapp_payload(data)
	except Exception:
		frappe.logger("msuite_workspace.inbox").exception("Inbox WhatsApp bridge failed")
	return {"status": "success"}
