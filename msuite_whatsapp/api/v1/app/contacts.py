"""
WhatsApp chat-widget contact list.

Backs the floating widget's left-rail rooms list. Reads from the new
inbox structure (Channel Handle + Conversation) instead of the legacy
WhatsApp Contact doctype so:

  • Every WhatsApp conversation auto-appears for the assigned agent.
  • The widget shows the same data the Inbox UI shows.
  • Manually-added contacts via `create()` are upserted as Channel
    Handles, not orphan WhatsApp Contact rows.
"""

from __future__ import annotations

import frappe
from frappe import _

from msuite_inbox.inbox.constants import ChannelType

# Added per WHATSAPP_REFACTOR_PLAN.md §1/§10 — neither endpoint in this
# module had an authorization check; any authenticated user could create
# Channel Handles or read every WhatsApp conversation on the site.


def _check_create():
	if not frappe.has_permission("Channel Handle", "create"):
		frappe.throw(_("No create permission for Channel Handle"), frappe.PermissionError)


def _check_read():
	if not frappe.has_permission("Conversation", "read"):
		frappe.throw(_("No read permission for Conversation"), frappe.PermissionError)


@frappe.whitelist()
def create(contact_name: str, mobile_no: str, email: str | None = None):
	"""Upsert a Channel Handle from the widget's "add contact" dialog.

	`email` was used by the legacy widget to mark which agent should see
	the contact in their queue; we now express that via
	`Conversation.assigned_to` once an actual conversation exists. The
	parameter is accepted for API compatibility but stored only on the
	Channel Handle metadata.
	"""
	_check_create()
	phone = (mobile_no or "").lstrip("+").strip()
	if not phone:
		frappe.throw("mobile_no required")

	existing = frappe.db.get_value(
		"Channel Handle",
		{"channel_type": ChannelType.WHATSAPP, "platform_handle": phone},
		"name",
	)
	if existing:
		if contact_name and not frappe.db.get_value("Channel Handle", existing, "display_name"):
			frappe.db.set_value("Channel Handle", existing, "display_name", contact_name)
		return {"status": "success", "channel_handle": existing}

	doc = frappe.get_doc(
		{
			"doctype": "Channel Handle",
			"channel_type": ChannelType.WHATSAPP,
			"platform_handle": phone,
			"display_name": contact_name or phone,
			"metadata": {"created_by_agent_email": email} if email else None,
		}
	)
	doc.insert(ignore_permissions=True)
	return {"status": "success", "channel_handle": doc.name}


@frappe.whitelist()
def get(email: str | None = None):
	"""Rooms list for the chat widget.

	Returns one row per WhatsApp Conversation (newest-touched first,
	collapsed by Channel Handle so each contact = one room). Shape kept
	identical to the legacy version so the widget JS doesn't change:
	    [{name, contact_name, mobile_no, email, last_message, is_read}]

	When `email` is given we filter to conversations assigned to that
	user — preserves the legacy "show me my contacts" filter. With no
	email, every WA conversation comes back (admin / unassigned view).
	"""
	_check_read()
	filters = {"channel_type": ChannelType.WHATSAPP}
	if email:
		filters["assigned_to"] = email

	convs = frappe.get_all(
		"Conversation",
		filters=filters,
		fields=[
			"name",
			"channel_handle",
			"assigned_to",
			"last_message_excerpt",
			"unread_count",
			"modified",
		],
		order_by="modified desc",
		limit_page_length=500,
	)
	if not convs:
		return []

	handle_names = list({c["channel_handle"] for c in convs if c["channel_handle"]})
	handle_map = {
		h["name"]: h
		for h in frappe.get_all(
			"Channel Handle",
			filters={"name": ("in", handle_names)},
			fields=["name", "platform_handle", "display_name"],
		)
	}

	rows = []
	seen_handles: set[str] = set()
	for c in convs:
		if c["channel_handle"] in seen_handles:
			continue
		seen_handles.add(c["channel_handle"])
		h = handle_map.get(c["channel_handle"]) or {}
		rows.append(
			{
				"name": c["channel_handle"],
				"contact_name": h.get("display_name") or h.get("platform_handle") or "",
				"mobile_no": h.get("platform_handle") or "",
				"email": c["assigned_to"] or "",
				"last_message": c["last_message_excerpt"] or "",
				"is_read": 1 if (c["unread_count"] or 0) == 0 else 0,
			}
		)
	return rows
