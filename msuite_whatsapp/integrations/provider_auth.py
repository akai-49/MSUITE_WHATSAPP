"""Provider auth & verification for webhooks."""

from __future__ import annotations

import frappe
from werkzeug.wrappers import Response


def handle_verification_challenge():
	"""Handle Meta webhook verification handshake."""
	if not (frappe.request and frappe.request.method == "GET"):
		return None

	def _param(name):
		return frappe.form_dict.get(name) or (frappe.request.args.get(name) if frappe.request else None) or ""

	challenge = _param("hub.challenge")
	if not challenge:
		return None

	verify_token = frappe.conf.get("meta_webhook_verify_token")
	if not verify_token:
		try:
			verify_token = frappe.db.get_single_value("WhatsApp Settings", "webhook_verify_token", cache=True)
		except Exception:
			verify_token = None

	token_sent = _param("hub.verify_token")
	if not verify_token or token_sent == verify_token:
		return Response(challenge, status=200, mimetype="text/plain")

	return Response("Forbidden", status=403, mimetype="text/plain")


def validate_provider_auth():
	return True
