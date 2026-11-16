"""
WhatsApp Business Calling API — thin delegator.

All business logic (routing, permissions, active-call management, state
transitions, analytics) lives in `inbox.services.call_service` — calling
is owned by Inbox as part of the Business Communication Platform (see
INBOX_ARCHITECTURE_AUDIT.md §3, "Calling MUST remain inside Inbox").
This file exists only to:

  1. Keep every dotted path the Vue SPA already calls
     (`msuite_whatsapp.api.v1.app.calls.*`) working unchanged.
  2. Own the one thing that's genuinely WhatsApp-API-surface-specific:
     the provider webhook receiver's auth gate.

Architecture: API (here) → Service (`inbox.services.call_service`) →
Repository/Provider (`whatsapp.repositories`, `whatsapp.providers.meta`).
"""

import frappe
from frappe.rate_limiter import rate_limit

from msuite_whatsapp.services.calls import call_service
from msuite_whatsapp.services.permissions.roles import ADMIN, INBOX_AGENT, INBOX_MANAGER, SYSTEM_MANAGER

CALL_ACTION_ROLES = (SYSTEM_MANAGER, ADMIN, INBOX_MANAGER, INBOX_AGENT)


def _require_call_role():
	frappe.only_for(list(CALL_ACTION_ROLES))

# ═══════════════════════════════════════════════════════════════════════
# 1. Webhook Receiver (from Provider)
# ═══════════════════════════════════════════════════════════════════════


@frappe.whitelist(allow_guest=True)
def handle_call_webhook(**kwargs):
	"""Receive forwarded call webhooks from the provider. Authenticated
	via provider auth headers."""
	from msuite_whatsapp.integrations.provider_auth import validate_provider_auth

	validate_provider_auth()

	for call in kwargs.get("call_events", []):
		call_service.process_call_event(call)

	for msg in kwargs.get("permission_events", []):
		call_service.process_permission_event(msg)

	frappe.db.commit()
	return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════════
# 2. Call Actions (Client → Meta)
# ═══════════════════════════════════════════════════════════════════════


@frappe.whitelist()
def answer_call(call_name, sdp="", sdp_type="answer"):
	"""Agent answers an inbound call. Sends pre_accept with SDP answer."""
	_require_call_role()
	return call_service.answer_call(call_name, sdp=sdp, sdp_type=sdp_type)


@frappe.whitelist()
def accept_call(call_name):
	"""Confirm WebRTC connection to Meta after `answer_call`."""
	_require_call_role()
	return call_service.accept_call(call_name)


@frappe.whitelist()
def reject_call(call_name):
	"""Agent rejects an incoming call."""
	_require_call_role()
	return call_service.reject_call(call_name)


@frappe.whitelist()
def terminate_call(call_name):
	"""Agent hangs up an active call."""
	_require_call_role()
	return call_service.terminate_call(call_name)


@frappe.whitelist()
def initiate_outbound_call(whatsapp_account="", to_number="", sdp=None, sdp_type=None):
	"""Agent initiates an outbound call. Calls Meta directly — no provider proxy."""
	_require_call_role()
	return call_service.initiate_outbound_call(
		whatsapp_account=whatsapp_account,
		to_number=to_number,
		sdp=sdp,
		sdp_type=sdp_type,
	)


@frappe.whitelist()
def mark_call_connected(call_name):
	"""Mark an outbound call as Connected — the browser is the source of
	truth for this transition since Meta doesn't emit a webhook for it."""
	_require_call_role()
	return call_service.mark_call_connected(call_name)


# ═══════════════════════════════════════════════════════════════════════
# 3. Call Permissions
# ═══════════════════════════════════════════════════════════════════════


@frappe.whitelist()
def request_call_permission(to_number="", whatsapp_account=None, method="interactive", template_name=None):
	"""Request outbound call permission from a user via an interactive
	request or template message."""
	_require_call_role()
	return call_service.request_call_permission(
		to_number=to_number,
		whatsapp_account=whatsapp_account,
		method=method,
		template_name=template_name,
	)


@frappe.whitelist()
def check_can_call(to_number="", whatsapp_account=None):
	"""Pre-check before outbound call. Used by the CRM Lead call button."""
	frappe.has_permission("WhatsApp Call", "read", throw=True)
	frappe.has_permission("WhatsApp Call Permission", "read", throw=True)
	return call_service.check_can_call(to_number=to_number, whatsapp_account=whatsapp_account)


@frappe.whitelist()
def get_call_permission_state(to_number="", whatsapp_account=None):
	"""Rich call-permission state for the conversation-header badge."""
	frappe.has_permission("WhatsApp Call", "read", throw=True)
	frappe.has_permission("WhatsApp Call Permission", "read", throw=True)
	return call_service.get_call_permission_state(to_number=to_number, whatsapp_account=whatsapp_account)


@frappe.whitelist()
def grant_call_permission(to_number="", whatsapp_account=None):
	"""Manually grant call permission for a phone number."""
	_require_call_role()
	return call_service.grant_call_permission(to_number=to_number, whatsapp_account=whatsapp_account)


# ═══════════════════════════════════════════════════════════════════════
# 4. Lookup / Analytics Helpers
# ═══════════════════════════════════════════════════════════════════════


@frappe.whitelist()
def get_call_history(phone_number="", limit=5):
	"""Recent call history for a phone number. Used by the Lead dashboard."""
	frappe.has_permission("WhatsApp Call", "read", throw=True)
	return call_service.get_call_history(phone_number=phone_number, limit=limit)


@frappe.whitelist()
def get_call_permission_templates(whatsapp_account=None, to_number=None):
	"""Approved templates with CALL_PERMISSION_REQUEST capability."""
	frappe.has_permission("WhatsApp Call", "read", throw=True)
	return call_service.get_call_permission_templates(whatsapp_account=whatsapp_account, to_number=to_number)


@frappe.whitelist(methods=["GET", "POST"])
@rate_limit(limit=120, seconds=60)
def lookup_caller(phone_number=""):
	"""Resolve a phone number to a CRM Lead or Contact.

	Logged-in users only (audit H1): as a guest endpoint it let anyone map
	phone numbers to customer names. Callers must be able to read
	Conversations (agents) — the overlay treats a failure as "no match".
	"""
	frappe.has_permission("Conversation", "read", throw=True)
	return call_service.lookup_caller(phone_number=phone_number)


@frappe.whitelist()
def save_call_notes(call_name, notes=""):
	"""Save / update notes on a WhatsApp Call record."""
	_require_call_role()
	return call_service.save_call_notes(call_name, notes=notes)


@frappe.whitelist()
def get_call_analytics(whatsapp_account=None, days: int = 30):
	"""Aggregate call counts/duration for the dashboard."""
	frappe.has_permission("WhatsApp Call", "read", throw=True)
	return call_service.call_analytics_summary(whatsapp_account=whatsapp_account, days=days)


@frappe.whitelist()
def get_unread_missed_calls_count():
	"""Count of missed inbound calls not yet acknowledged by the current user."""
	frappe.has_permission("WhatsApp Call", "read", throw=True)
	return call_service.get_unread_missed_calls_count()


@frappe.whitelist()
def acknowledge_missed_calls(phone_number=None):
	"""Mark missed calls as acknowledged for this user."""
	_require_call_role()
	return call_service.acknowledge_missed_calls(phone_number=phone_number)


# ═══════════════════════════════════════════════════════════════════════
# 5. Calling Settings (Meta phone-number-level enablement)
# ═══════════════════════════════════════════════════════════════════════


@frappe.whitelist()
def get_calling_settings(whatsapp_account=None):
	"""Check whether Calling is enabled on this phone number."""
	frappe.has_permission("WhatsApp Call", "read", throw=True)
	return call_service.get_calling_settings(whatsapp_account=whatsapp_account)


@frappe.whitelist()
def enable_calling(whatsapp_account=None):
	"""Attempt to enable Calling on this phone number via Meta's API."""
	_require_call_role()
	return call_service.enable_calling(whatsapp_account=whatsapp_account)

