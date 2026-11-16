"""Order Flow Settings API — Whitelisted endpoints for MSuite UI to configure WhatsApp Order Address Flows."""

from __future__ import annotations

import frappe
from frappe import _

from msuite_whatsapp.services.permissions.checks import check_read, check_write

KEY_SELECTED_FLOW = "msuite_order_address_flow_name"
KEY_AUTO_SEND = "msuite_order_address_auto_send"
KEY_PROMPT_TEXT = "msuite_order_address_prompt_text"

DEFAULT_PROMPT_TEXT = (
	"Thank you for your order! 🛍️\n\n"
	"Please tap below to provide your delivery address and phone number "
	"so we can process your shipment."
)


@frappe.whitelist()
def get_order_flow_settings() -> dict:
	"""Return currently configured order flow settings + list of published flows for dropdown."""
	check_read("WhatsApp Settings")
	published_flows = frappe.get_all(
		"WhatsApp Flow",
		filters={"status": ["in", ["Published", "Draft"]]},
		fields=["name", "flow_name", "flow_id", "status", "whatsapp_account"],
		order_by="modified desc",
	)

	# Only reflect the merchant's explicitly saved choice — never guess by
	# picking "most recently modified flow". WhatsApp Flow has track_changes=1,
	# so any incidental edit/sync on an unrelated flow would otherwise silently
	# hijack this setting on the next page load.
	saved_flow = frappe.db.get_default(KEY_SELECTED_FLOW)
	selected_flow = str(saved_flow).strip() if saved_flow else ""

	raw_auto_send = frappe.db.get_default(KEY_AUTO_SEND)
	auto_send_enabled = (
		True if raw_auto_send is None else str(raw_auto_send).strip() not in ("0", "false", "False")
	)
	prompt_text = frappe.db.get_default(KEY_PROMPT_TEXT) or DEFAULT_PROMPT_TEXT

	return {
		"selected_flow": selected_flow,
		"auto_send_enabled": bool(auto_send_enabled),
		"prompt_text": prompt_text,
		"available_flows": published_flows,
	}


@frappe.whitelist()
def save_order_flow_settings(
	selected_flow: str = "",
	auto_send_enabled: int | bool = 1,
	prompt_text: str = "",
) -> dict:
	"""Persist user settings from MSuite UI."""
	check_write("WhatsApp Settings")
	selected_flow = str(selected_flow).strip()
	if selected_flow and not frappe.db.exists("WhatsApp Flow", selected_flow):
		frappe.throw(_("WhatsApp Flow {0} does not exist").format(selected_flow))
	frappe.db.set_default(KEY_SELECTED_FLOW, selected_flow)
	frappe.db.set_default(KEY_AUTO_SEND, "1" if auto_send_enabled else "0")
	if prompt_text:
		frappe.db.set_default(KEY_PROMPT_TEXT, str(prompt_text).strip())

	frappe.db.commit()
	return {"status": "success", "message": _("Order flow settings saved successfully")}
