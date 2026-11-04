"""
WhatsApp chat-widget API.

Backs the floating whatsapp-chat bundle that lives on every desk page.
Originally read/wrote the legacy `WhatsApp Message` doctype directly;
now it goes through the inbox stack so the widget and the Inbox UI
render the exact same data.

  • get_all(room, user_no)   — chronological message list for a contact
  • send(...)                — agent sends a text or media reply
  • mark_as_read(room)       — clears unread + sends Meta read receipt

The widget uses the legacy `WhatsApp Contact.name` as `room`. We keep
that contract so the bundle doesn't need a coordinated frontend change,
but the data underneath is Channel Message all the way down.
"""

from __future__ import annotations

import mimetypes

import frappe
from frappe import _

from msuite_inbox.inbox.constants import ChannelType, Direction

# ── Permission helpers ───────────────────────────────────────────────────
#
# Added per WHATSAPP_REFACTOR_PLAN.md §1/§10 — this module previously had
# no authorization checks at all (any authenticated session could read or
# send on an arbitrary phone room), unlike `crud.py` which already gates
# every endpoint. Mirrors `crud.py`'s check_read/check_write pattern.


def _check_read():
	if not frappe.has_permission("Channel Message", "read"):
		frappe.throw(_("No read permission for Channel Message"), frappe.PermissionError)


def _check_write():
	if not frappe.has_permission("Channel Message", "write"):
		frappe.throw(_("No write permission for Channel Message"), frappe.PermissionError)


# ── Helpers ──────────────────────────────────────────────────────────────


def _resolve_phone(room: str, user_no: str | None = None) -> str | None:
	"""Map the widget's `room` value to an E.164 phone.

	`room` is whatever `contacts.get` returned in `name` — that's
	`Channel Handle.name` for the new structure, but legacy widget
	sessions might still pass a `WhatsApp Contact.name`. Try both, then
	fall back to `user_no` or the room value itself.
	"""
	phone = user_no
	if not phone and frappe.db.exists("Channel Handle", room):
		phone = frappe.db.get_value("Channel Handle", room, "platform_handle")
	if not phone and frappe.db.exists("WhatsApp Contact", room):
		phone = frappe.db.get_value("WhatsApp Contact", room, "mobile_no")
	if not phone:
		phone = room
	return (phone or "").lstrip("+").strip() or None


def _open_conversation_for_phone(phone: str) -> str | None:
	"""Most recent conversation for this phone on any WhatsApp inbox."""
	handle = frappe.db.get_value(
		"Channel Handle",
		{"channel_type": ChannelType.WHATSAPP, "platform_handle": phone},
		"name",
	)
	if not handle:
		return None
	return frappe.db.get_value(
		"Conversation",
		{"channel_handle": handle},
		"name",
		order_by="modified desc",
	)


def _content_field(row: dict) -> tuple[str, str | None]:
	"""Map Channel Message row → widget content + caption pair.

	For text rows: content = text_content, caption = None.
	For media rows: content = first attachment URL, caption = text_content
	(which already holds the caption per the dispatcher conventions).
	"""
	if row.get("content_type") in ("Text", "System", "Unknown"):
		return row.get("text_content") or "", None
	attach = frappe.db.get_value(
		"Channel Message Attachment",
		{"parent": row["name"]},
		"file_url",
	)
	return attach or row.get("text_content") or "", row.get("text_content")


# ── Endpoints ────────────────────────────────────────────────────────────


@frappe.whitelist()
def get_all(room: str, user_no: str):
	"""Return chronological messages for the chat-widget room.

	Shape kept identical to the legacy version so the bundle JS doesn't
	need to change:
	    [{creation, sender_user_no, content, caption, content_type}]
	"""
	_check_read()
	phone = _resolve_phone(room, user_no)
	if not phone:
		return []
	conv = _open_conversation_for_phone(phone)
	if not conv:
		return []

	rows = frappe.get_all(
		"Channel Message",
		filters={"conversation": conv},
		fields=["name", "creation", "direction", "content_type", "text_content"],
		order_by="creation asc",
	)

	out = []
	for r in rows:
		content, caption = _content_field(r)
		out.append(
			{
				"creation": r["creation"],
				"sender_user_no": user_no if r["direction"] == Direction.INBOUND else "Administrator",
				"content": content,
				"caption": caption,
				"content_type": (r["content_type"] or "Text").lower(),
			}
		)
	return out


@frappe.whitelist()
def send(content, user, room, user_no, attachment=None):
	"""Agent reply from the chat-widget composer.

	Routes through `inbox.services.outbound.send_to_phone` so the message
	funnels through the same pipeline as the rest of the platform.
	"""
	_check_write()
	from msuite_inbox.inbox.services.outbound import send_to_phone

	payload: dict = {"sender_type": "Agent", "sender_user": frappe.session.user}
	if attachment:
		payload["media_url"] = content
		payload["type"] = _media_kind_from_path(content)
	else:
		payload["type"] = "text"
		payload["text"] = content

	send_to_phone(phone=user_no, payload=payload)
	return "ok"


def _media_kind_from_path(path: str) -> str:
	mime = mimetypes.guess_type(path)[0] or ""
	if mime.startswith("image/"):
		return "image"
	if mime.startswith("video/"):
		return "video"
	if mime.startswith("audio/"):
		return "audio"
	return "document"


@frappe.whitelist()
def send_template(
	to: str, template: str, reference_doctype: str | None = None, reference_name: str | None = None
):
	"""Send a templated WhatsApp message — backs the desk "Send to WhatsApp"
	menu added by msuite_workspace.js.

	Offer values (countdown expiry, coupon code, tap link) cannot be supplied
	here: a template that needs them fails with the template builder's
	validation error. Send those from the inbox template picker or the
	WhatsApp broadcast wizard.

	Drop-in replacement for the legacy
	`whatsapp_message.send_template` so existing menu wiring keeps working.
	"""
	_check_write()
	from msuite_inbox.inbox.services.outbound import send_to_phone

	send_to_phone(
		phone=to,
		payload={
			"type": "template",
			"template": template,
			"sender_type": "Agent",
			"sender_user": frappe.session.user,
			# The template builder will pull variables from the ref doc
			# automatically when body_param isn't supplied (see
			# whatsapp/utils/template_send.build_template_meta).
		},
		reference_doctype=reference_doctype,
		reference_name=reference_name,
	)
	return "ok"


@frappe.whitelist()
def set_typing(room: str, user: str | None = None, is_typing: int = 0, is_guest: int = 0):
	"""Typing-indicator pub/sub for the chat widget.

	Publishes a realtime event other open clients can subscribe to.
	Stateless — we don't persist typing state, just broadcast it.
	"""
	_check_read()
	frappe.publish_realtime(
		"msuite_widget:typing",
		{"room": room, "user": user or frappe.session.user, "is_typing": int(is_typing)},
		room=room,
	)
	return "ok"


@frappe.whitelist()
def mark_as_read(room: str):
	"""Reset unread + optionally fire Meta read receipts.

	The widget passes a WhatsApp Contact name as `room`. We resolve to
	a Channel Handle / Conversation and zero its unread_count.
	"""
	_check_write()
	if frappe.db.exists("WhatsApp Contact", room):
		try:
			frappe.db.set_value("WhatsApp Contact", room, "is_read", 1, update_modified=False)
		except Exception:
			# Concurrent updates from multiple agents are harmless, but log
			# anything else so a real failure here doesn't go unnoticed.
			frappe.log_error(
				title="WhatsApp mark_as_read failed",
				message=frappe.get_traceback(),
			)

	phone = _resolve_phone(room)
	if phone:
		conv = _open_conversation_for_phone(phone)
		if conv:
			frappe.db.set_value("Conversation", conv, "unread_count", 0, update_modified=False)

	return "ok"


@frappe.whitelist()
def react(room: str, user_no: str, platform_message_id: str, emoji: str = ""):
	"""Send a reaction to a specific inbound/outbound WhatsApp message.

	New capability — addresses the architecture audit's Critical Finding
	that reaction messages were entirely unhandled on the outbound side
	(WHATSAPP_REFACTOR_PLAN.md §14.4). `emoji=""` removes a previously
	sent reaction (Meta's documented un-react behaviour).

	Inbound reaction *parsing* still needs to be added to the Inbox
	module's channel handler — out of scope for the WhatsApp module
	refactor; see IMPLEMENTATION_REPORT.md "Remaining Work".
	"""
	_check_write()
	from msuite_whatsapp.integrations.meta import client, message_provider
	from msuite_whatsapp.queries.account_repository import get_whatsapp_account

	phone = _resolve_phone(room, user_no)
	if not phone:
		frappe.throw(_("Could not resolve a phone number for this room."))

	account = get_whatsapp_account(account_type="outgoing")
	if not account:
		frappe.throw(_("No default outgoing WhatsApp Account configured."))

	body = message_provider.build_reaction_body(phone, platform_message_id, emoji)
	client.post_to_meta(account, body)
	return "ok"
