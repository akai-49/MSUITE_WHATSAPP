"""
CRM WhatsApp overrides — keep Frappe CRM untouched, route its calls to us.

The Frappe CRM frontend (`apps/crm/frontend/src/components/Activities/
WhatsAppArea.vue` + `WhatsAppBox.vue`) talks to four whitelisted RPCs:

    crm.api.whatsapp.create_whatsapp_message
    crm.api.whatsapp.send_whatsapp_template
    crm.api.whatsapp.react_on_whatsapp_message
    crm.api.whatsapp.get_whatsapp_messages

We intercept those via `override_whitelisted_methods` in our own
`hooks.py`. CRM's source files stay pristine, so `bench update --apps
crm` never touches our code and we never block their upgrades.

Underneath the override:
  • writes  → `inbox.services.outbound.send_to_phone` so every WhatsApp
              message — whether it originated from the CRM tab or our
              Inbox SPA — lands as a single `Channel Message` row.
  • reads   → `tabChannel Message` projected into the legacy
              `WhatsApp Message` field shape the CRM frontend already
              knows how to render.

No new doctype, no legacy `WhatsApp Message` writes. The handover is
purely at the RPC boundary.
"""

import frappe
from frappe import _

# ── Read surface ────────────────────────────────────────────────────────


_CONTENT_TYPE_MAP = {
	# Channel Message content_type → CRM's lowercase string the
	# `WhatsAppArea.vue` decision tree understands.
	"Text": "text",
	"Image": "image",
	"Video": "video",
	"Audio": "audio",
	"Document": "document",
	"Sticker": "sticker",
	"Location": "location",
	"Contacts": "contact",
	"Reaction": "reaction",
	"Interactive": "text",
	"Template": "text",
	"System": "text",
}


@frappe.whitelist()
def get_whatsapp_messages(reference_doctype, reference_name):
	"""Return all WhatsApp messages on a CRM party in the legacy
	field shape `WhatsAppArea.vue` expects. Reads from `Channel
	Message`; the legacy `WhatsApp Message` doctype is never touched.

	For `CRM Deal`, also pulls the deal's lead's history so the deal
	page shows the full lead thread (matches the original behaviour).
	"""
	if reference_doctype and reference_name:
		if not frappe.has_permission(reference_doctype, "read", doc=reference_name):
			frappe.throw(
				_("No permission to access {0} {1}").format(reference_doctype, reference_name),
				frappe.PermissionError,
			)

	if not frappe.db.exists("DocType", "Channel Message"):
		return []

	refs = [(reference_doctype, reference_name)]
	if reference_doctype == "CRM Deal":
		lead = frappe.db.get_value(reference_doctype, reference_name, "lead")
		if lead:
			refs.append(("CRM Lead", lead))

	seen: set[str] = set()
	messages: list[dict] = []
	for ref_dt, ref_name in refs:
		messages.extend(_messages_for_party(ref_dt, ref_name, seen))

	messages.sort(key=lambda m: m["creation"])

	# Fold reactions onto their parent bubble (matches WhatsApp web).
	by_pid = {m["message_id"]: m for m in messages if m.get("message_id")}
	for r in [m for m in messages if m["content_type"] == "reaction"]:
		parent = by_pid.get(r["reply_to_message_id"])
		if parent:
			parent["reaction"] = r["message"]

	# Resolve reply chains so each is_reply bubble shows the quoted body.
	for m in messages:
		if not m.get("is_reply"):
			continue
		parent = by_pid.get(m["reply_to_message_id"])
		if not parent:
			continue
		m["reply_message"] = parent.get("message") or ""
		m["reply_to"] = parent["name"]
		m["reply_to_type"] = parent["type"]
		m["reply_to_from"] = _from_name_for(parent) if parent.get("from") else _("You")

	for m in messages:
		m["from_name"] = _from_name_for(m) if m.get("from") else _("You")

	# CRM never renders reactions as standalone rows — only as chips.
	return [m for m in messages if m["content_type"] != "reaction"]


# ── Write surface ───────────────────────────────────────────────────────


@frappe.whitelist()
def create_whatsapp_message(
	reference_doctype,
	reference_name,
	message,
	to,
	attach,
	reply_to,
	content_type="text",
):
	"""Send a free-text or media message from the CRM WhatsApp tab.

	`reply_to` is a Channel Message name (CRM frontend gets it from
	`get_whatsapp_messages`); we resolve it back to a
	`platform_message_id` so the channel handler can wire Meta's
	`context.message_id` for native reply threading.
	"""
	if reference_doctype and reference_name:
		if not frappe.has_permission(reference_doctype, "read", doc=reference_name):
			frappe.throw(
				_("No permission to access {0} {1}").format(reference_doctype, reference_name),
				frappe.PermissionError,
			)

	# 1. Resolve which channel and platform handle to send to
	channel_type = "WhatsApp"
	platform_handle = to

	if reply_to:
		channel_handle = frappe.db.get_value("Channel Message", reply_to, "channel_handle")
		if channel_handle:
			ch_doc = frappe.db.get_value(
				"Channel Handle", channel_handle, ["channel_type", "platform_handle"], as_dict=True
			)
			if ch_doc:
				channel_type = ch_doc.channel_type
				platform_handle = ch_doc.platform_handle
	else:
		# Get the latest message for this party (Lead/Deal)
		latest_msg = frappe.db.sql(
			"""
            SELECT cm.channel_handle
            FROM `tabChannel Message` cm
            LEFT JOIN `tabConversation` conv ON conv.name = cm.conversation
            WHERE
                (cm.reference_doctype = %(dt)s AND cm.reference_name = %(name)s)
                OR (conv.crm_party_type = %(dt)s AND conv.crm_party = %(name)s)
            ORDER BY cm.creation DESC
            LIMIT 1
            """,
			{"dt": reference_doctype, "name": reference_name},
			as_dict=True,
		)
		if latest_msg:
			ch_doc = frappe.db.get_value(
				"Channel Handle",
				latest_msg[0]["channel_handle"],
				["channel_type", "platform_handle"],
				as_dict=True,
			)
			if ch_doc:
				channel_type = ch_doc.channel_type
				platform_handle = ch_doc.platform_handle

	# If it is Facebook/Instagram, make sure platform_handle is the PSID/IGSID, not phone
	if channel_type in ("Facebook DM", "Instagram DM"):
		if not platform_handle:
			platform_handle = frappe.db.get_value(
				"Channel Handle",
				{
					"crm_party_type": reference_doctype,
					"crm_party": reference_name,
					"channel_type": channel_type,
				},
				"platform_handle",
			)

	payload: dict = {
		"sender_type": "Agent",
		"sender_user": frappe.session.user,
	}
	if reply_to:
		reply_pid = frappe.db.get_value("Channel Message", reply_to, "platform_message_id")
		if reply_pid:
			payload["reply_to_platform_id"] = reply_pid

	if attach and content_type not in ("text", "reaction"):
		payload["type"] = content_type  # image / video / audio / document
		payload["media_url"] = attach
		if message:
			payload["caption"] = message
	elif attach:
		payload["type"] = "document"
		payload["media_url"] = attach
		if message:
			payload["caption"] = message
	else:
		payload["type"] = "text"
		payload["text"] = message or ""

	from msuite_inbox.inbox.services.outbound import send_message

	return send_message(
		channel_type=channel_type,
		platform_handle=platform_handle,
		payload=payload,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
	)


@frappe.whitelist()
def send_whatsapp_template(reference_doctype, reference_name, template, to, body_param=None, attach=None):
	"""Send an approved WhatsApp template via the inbox dispatcher."""
	if reference_doctype and reference_name:
		if not frappe.has_permission(reference_doctype, "read", doc=reference_name):
			frappe.throw(
				_("No permission to access {0} {1}").format(reference_doctype, reference_name),
				frappe.PermissionError,
			)

	from msuite_inbox.inbox.services.outbound import send_message

	payload: dict = {
		"type": "template",
		"template": template,
		"sender_type": "Agent",
		"sender_user": frappe.session.user,
	}
	if body_param:
		payload["body_param"] = body_param
	if attach:
		payload["attach"] = attach

	return send_message(
		channel_type="WhatsApp",
		platform_handle=to,
		payload=payload,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
	)


@frappe.whitelist()
def react_on_whatsapp_message(emoji, reply_to_name):
	# perm: delegated to react_to_message
	"""Send a WhatsApp reaction on an existing Channel Message.

	`reply_to_name` is the Channel Message name (CRM passes it as the
	legacy WhatsApp Message name; the override maps the same field).
	"""
	from msuite_inbox.inbox.api.v1.conversation import react_to_message

	return react_to_message(channel_message=reply_to_name, emoji=emoji)


# ── Internal helpers ────────────────────────────────────────────────────


def _messages_for_party(ref_dt: str, ref_name: str, seen: set[str]) -> list[dict]:
	"""Channel Messages whose reference matches a CRM party, OR whose
	parent Conversation has a Channel Handle bound to that party
	(catches inbound messages that landed before identity resolution
	promoted them to the party)."""
	rows = frappe.db.sql(
		"""
        SELECT DISTINCT cm.name
        FROM `tabChannel Message` cm
        LEFT JOIN `tabConversation` conv ON conv.name = cm.conversation
        WHERE
            (cm.reference_doctype = %(dt)s AND cm.reference_name = %(name)s)
            OR (conv.crm_party_type = %(dt)s AND conv.crm_party = %(name)s)
        ORDER BY cm.creation ASC
        """,
		{"dt": ref_dt, "name": ref_name},
		as_dict=True,
	)
	out: list[dict] = []
	for r in rows:
		if r["name"] in seen:
			continue
		seen.add(r["name"])
		out.append(_project_message(r["name"]))
	return out


def _project_message(message_name: str) -> dict:
	"""Project one Channel Message into the legacy `WhatsApp Message`
	field shape that CRM's WhatsAppArea.vue already understands."""
	cm = frappe.db.get_value(
		"Channel Message",
		message_name,
		[
			"name",
			"direction",
			"content_type",
			"text_content",
			"platform_message_id",
			"reply_to_platform_id",
			"sender_phone",
			"channel_handle",
			"template_name",
			"template_variables",
			"status",
			"failure_reason",
			"creation",
			"reference_doctype",
			"reference_name",
		],
		as_dict=True,
	)

	channel_type = frappe.db.get_value("Channel Handle", cm.channel_handle, "channel_type") or "WhatsApp"

	if cm.direction == "Inbound":
		from_phone, to_phone = cm.sender_phone, ""
	else:
		from_phone = ""
		to_phone = frappe.db.get_value("Channel Handle", cm.channel_handle, "platform_handle") or ""

	# First attachment URL only — CRM UI shows one media per bubble.
	attach = frappe.db.get_value("Channel Message Attachment", {"parent": cm.name}, "file_url") or ""

	is_template = cm.content_type == "Template"
	return {
		"name": cm.name,
		"type": "Incoming" if cm.direction == "Inbound" else "Outgoing",
		"to": to_phone,
		"from": from_phone,
		"content_type": _CONTENT_TYPE_MAP.get(cm.content_type, "text"),
		"message_type": "Template"
		if is_template
		else ("Media" if cm.content_type in ("Image", "Video", "Audio", "Document", "Sticker") else "Text"),
		"attach": attach,
		"template": cm.template_name or "",
		"use_template": 1 if is_template else 0,
		"message_id": cm.platform_message_id or "",
		"is_reply": 1 if cm.reply_to_platform_id else 0,
		"reply_to_message_id": cm.reply_to_platform_id or "",
		"creation": cm.creation,
		"message": cm.text_content or "",
		"status": cm.status or "",
		"reference_doctype": cm.reference_doctype or "",
		"reference_name": cm.reference_name or "",
		"template_parameters": cm.template_variables or "",
		"template_header_parameters": "",
		"failure_reason": cm.failure_reason or "",
		"channel_type": channel_type,
	}


def _from_name_for(message: dict) -> str:
	"""Friendly sender name from the CRM reference. Matches the
	original CRM behaviour (Deal primary contact → lead_name → first
	+ last name on Contact-like docs)."""
	if not (message.get("reference_doctype") and message.get("reference_name")):
		return ""
	try:
		doc = frappe.get_doc(message["reference_doctype"], message["reference_name"])
	except frappe.DoesNotExistError:
		return ""

	if message["reference_doctype"] == "CRM Deal":
		for c in doc.get("contacts") or []:
			if c.is_primary:
				return c.full_name or c.mobile_no or ""
		return doc.get("lead_name") or ""

	return " ".join(filter(None, [doc.get("first_name"), doc.get("last_name")]))
