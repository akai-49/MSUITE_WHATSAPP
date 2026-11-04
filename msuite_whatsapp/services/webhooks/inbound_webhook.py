"""WhatsApp's half of the Meta webhook: messages, statuses, calls, history and account events.

The provider's forward arrives at `msuite_whatsapp.api.v1.integrations.webhook.webhook`, which hands
the payload to `feed_whatsapp_payload` here.
"""

from __future__ import annotations

import re
import time

import frappe

from msuite_whatsapp.constants import (
	WHATSAPP_MM_TERMS_DEFAULT_PREFIX,
	WHATSAPP_PRICING_CATEGORY_MARKETING_LITE,
	WHATSAPP_SEND_PATH_CLOUD_API,
	WHATSAPP_SEND_PATH_MARKETING_MESSAGES,
)
from msuite_core.utils.phone import customer_phone, is_bsuid
from msuite_inbox.inbox.api.v1.webhook import _ensure_default_inbox_exists, _STATUS_RANK
from msuite_inbox.inbox.constants import LOGGER_NAME, ChannelType, MessageStatus
from msuite_whatsapp.constants import (
	CHANNEL_MESSAGE_PRICING_CATEGORY_MAX_LEN,
	WHATSAPP_ACCOUNT_EVENT_AD_LINKED,
	WHATSAPP_ACCOUNT_EVENT_MM_TERMS,
	WHATSAPP_AD_ACCOUNT_DEFAULT_PREFIX,
	WHATSAPP_PRICING_CATEGORY_MARKETING,
	WHATSAPP_STATUS_PLAYED,
)
from msuite_inbox.inbox.services.dispatcher import handle as dispatch
from msuite_whatsapp.services.channels import inbox_channel as whatsapp
from msuite_whatsapp.queries.account_repository import find_default_phone_account
from msuite_whatsapp.services.accounts import phone_onboarding_service as phone_onboarding

logger = frappe.logger(LOGGER_NAME)

# ── WhatsApp Webhook Fields and Vocabulary ──────────────────────────────
FIELD_USER_ID_UPDATE = "user_id_update"
FIELD_BUSINESS_USERNAME_UPDATES = "business_username_updates"
FIELD_PHONE_NUMBER_USERNAME_UPDATE = "phone_number_username_update"
FIELD_MESSAGE_TEMPLATE_STATUS_UPDATE = "message_template_status_update"
SYSTEM_TYPE_USER_CHANGED_USER_ID = "user_changed_user_id"
KEY_USER_ID = "user_id"
KEY_PARENT_USER_ID = "parent_user_id"
KEY_USER_ID_UPDATE = "user_id_update"
KEY_PREVIOUS = "previous"
KEY_CURRENT = "current"
KEY_DISPLAY_PHONE_NUMBER = "display_phone_number"
KEY_USERNAME = "username"
KEY_REQUESTED_USERNAME = "requested_username"
KEY_STATUS = "status"
KEY_DECISION = "decision"
KEY_SYSTEM = "system"
KEY_TYPE = "type"
KEY_BODY = "body"
KEY_FROM_USER_ID = "from_user_id"
KEY_FROM_PARENT_USER_ID = "from_parent_user_id"
# Ordering so a late-arriving `delivery` never demotes a message already Read.
# Send route implied by a webhook pricing category (used only to fill a blank Channel Message.send_path).
_SEND_PATH_BY_PRICING_CATEGORY = {
	WHATSAPP_PRICING_CATEGORY_MARKETING_LITE: WHATSAPP_SEND_PATH_MARKETING_MESSAGES,
	WHATSAPP_PRICING_CATEGORY_MARKETING: WHATSAPP_SEND_PATH_CLOUD_API,
}
# Meta's webhook `event` values → our WhatsApp Templates.status options.
# Events with no mapping (FLAGGED, IN_APPEAL, PENDING_DELETION, DELETED)
# aren't valid Select options here — we still record the reason text but
# leave status untouched rather than throw on an invalid Select value.
_TEMPLATE_EVENT_TO_STATUS = {
	"APPROVED": "APPROVED",
	"REJECTED": "REJECTED",
	"PENDING": "PENDING",
	"IN_REVIEW": "PENDING",
	"PAUSED": "PAUSED",
	"DISABLED": "DISABLED",
	"REINSTATED": "APPROVED",
}


def feed_whatsapp_payload(payload: dict) -> None:
	"""Bridge from the WhatsApp webhook receiver into the inbox.

	Handles four sub-shapes of a WA webhook payload:
	  • value.messages[]   → parse + dispatch into Channel Message (inbound)
	  • value.statuses[]   → mirror Meta delivery state onto the matching
	                         outbound Channel Message (sent/delivered/read/failed)
	  • value.calls[]      → route call events (connect / terminate / status
	                         updates) through the calling module so the
	                         incoming-call overlay fires + the WhatsApp Call
	                         record stays current. Meta puts call events
	                         under `field: "calls"`, not `messages`, so the
	                         messages branch never sees them.
	  • messages[].identity / errors[code=131051] →
	                         customer's WhatsApp identity changed (number
	                         swap, new device). Re-bind the Channel Handle.
	  • field == "phone_number_username_update" →
	                         business username approved/rejected for one of
	                         our numbers; WABA-scoped, stored on its phone row.
	  • field == "message_template_status_update" →
	                         push-based template approval/rejection/pause/
	                         disable from Meta. WABA-scoped (no phone_number_id
	                         in the value), so it's handled before the
	                         per-Inbox resolution below would otherwise drop it.

	No legacy `WhatsApp Message` rows are written — Channel Message is
	the only source of truth.
	"""
	for entry in payload.get("entry") or []:
		entry_waba_id = entry.get("id") or ""
		for change in entry.get("changes") or []:
			field = change.get("field") or ""
			value = change.get("value") or {}
			if field == "account_update":
				_ingest_marketing_account_event(value, entry_waba_id)
			if field == FIELD_MESSAGE_TEMPLATE_STATUS_UPDATE:
				_ingest_template_status_update(value, entry_waba_id)
			elif field == FIELD_USER_ID_UPDATE or KEY_USER_ID_UPDATE in value:
				_handle_user_id_update(value)
			elif field in (FIELD_BUSINESS_USERNAME_UPDATES, FIELD_PHONE_NUMBER_USERNAME_UPDATE):
				phone_onboarding.apply_username_update(value, entry_waba_id)
				_handle_business_username_update(value)
			for msg in value.get("messages") or []:
				if msg.get(KEY_TYPE) == "system" and (msg.get(KEY_SYSTEM) or {}).get(KEY_TYPE) == SYSTEM_TYPE_USER_CHANGED_USER_ID:
					_handle_system_user_changed_user_id(msg)

	for entry in payload.get("entry") or []:
		entry_waba_id = entry.get("id") or ""
		for change in entry.get("changes") or []:
			value = change.get("value") or {}
			field = change.get("field") or ""
			phone_id = (value.get("metadata") or {}).get("phone_number_id") or ""
			inbox_name, resolved_account = _resolve_whatsapp_inbox_and_account(
				phone_id=phone_id,
				waba_id=entry_waba_id,
			)
			if not inbox_name:
				continue

			if value.get("messages"):
				_ingest_whatsapp_messages(value, inbox_name, waba_id=entry_waba_id, account_name=resolved_account)
			if value.get("statuses"):
				_ingest_whatsapp_statuses(value)
			if value.get("calls"):
				_ingest_whatsapp_calls(value)
			# ── Coexistence (WhatsApp Business app dual-use) fields ──
			if value.get("message_echoes"):
				_ingest_smb_message_echoes(value, inbox_name)
			if field == "history" or value.get("history"):
				_ingest_whatsapp_history(value, inbox_name)
			if value.get("state_sync"):
				_ingest_smb_state_sync(value)
			if field == "account_update" and (value.get("event") or "").upper() in (
				"ACCOUNT_OFFBOARDED",
				"ACCOUNT_RECONNECTED",
				"PARTNER_REMOVED",
			):
				_ingest_coexistence_account_event(value, entry_waba_id)
			for msg in value.get("messages") or []:
				if msg.get(KEY_TYPE) == "system" and (msg.get(KEY_SYSTEM) or {}).get(KEY_TYPE) == SYSTEM_TYPE_USER_CHANGED_USER_ID:
					_handle_system_user_changed_user_id(msg)


def _ingest_marketing_account_event(value: dict, entry_waba_id: str) -> None:
	"""Record WABA-scoped Marketing Messages API account events.

	AD_ACCOUNT_LINKED stores the linked ad account id and MM_LITE_TERMS_SIGNED
	flags the MM API terms as accepted, both keyed by WABA id via
	`frappe.db.set_default` (no schema change). Other events are ignored here.
	Side effect: one DB default write; the webhook caller commits.
	"""
	event = (value.get("event") or "").upper()
	info = value.get("waba_info") or {}
	waba_id = str(info.get("waba_id") or entry_waba_id or "").strip()
	if not waba_id:
		return
	if event == WHATSAPP_ACCOUNT_EVENT_AD_LINKED:
		ad_account = str(info.get("ad_account_id") or "").strip()
		if ad_account:
			frappe.db.set_default(f"{WHATSAPP_AD_ACCOUNT_DEFAULT_PREFIX}{waba_id}", ad_account)
	elif event == WHATSAPP_ACCOUNT_EVENT_MM_TERMS:
		frappe.db.set_default(f"{WHATSAPP_MM_TERMS_DEFAULT_PREFIX}{waba_id}", "1")


def _ingest_whatsapp_messages(
	value: dict,
	inbox_name: str,
	waba_id: str = "",
	account_name: str | None = None,
) -> None:
	# Stamp the WhatsApp Account on every event so reports / analytics
	# can filter Channel Messages by account without joining through
	# Inbox.
	phone_id = str((value.get("metadata") or {}).get("phone_number_id") or "").strip()
	wa_account = account_name or ""
	if not wa_account and phone_id:
		wa_account = frappe.db.get_value("WhatsApp Phone Number", {"phone_number_id": phone_id}, "parent")
	if not wa_account and waba_id:
		wa_account = frappe.db.get_value("WhatsApp Account", {"waba_id": waba_id}, "name")
	if not wa_account:
		wa_account = frappe.db.get_value("Inbox", inbox_name, "whatsapp_account") or ""
	if not wa_account:
		wa_account = find_default_phone_account("incoming") or ""
	if not wa_account:
		active_wabas = frappe.get_all("WhatsApp Account", filters={"status": "Active"}, pluck="name")
		if len(active_wabas) == 1:
			wa_account = active_wabas[0]

	events = whatsapp.parse_change(value, inbox_name)
	for event in events:
		event.whatsapp_account = wa_account
		# Media is resolved off the request path (INBOX_ARCHITECTURE_AUDIT.md
		# §9, Critical): a Graph API round-trip + file download inline here
		# would hold Meta's webhook ack open and risks a retry storm under
		# load. Persist the Channel Message immediately with the media_id
		# in metadata; a queued job fetches the file after the fact —
		# best-effort either way, the conversation thread is never blocked.
		try:
			result = dispatch(event)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			logger.exception("WhatsApp inbox dispatch failed: %s", event.platform_message_id)
			continue
		if result.get("message") and event.attachments:
			frappe.enqueue(
				"msuite_whatsapp.services.channels.inbox_channel.resolve_media_for_message",
				queue="short",
				channel_message_name=result["message"],
			)

	# Side-effect: route any interactive `call_permission_reply` messages
	# through the calling module so the WhatsApp Call Permission record
	# flips to Granted / Declined. Meta sends these as ordinary interactive
	# messages in the same webhook payload, so without this hop the badge
	# would stay "Awaiting call permission" forever even after the contact
	# taps Allow on their phone.
	_route_call_permission_replies(value)


def _route_call_permission_replies(value: dict) -> None:
	"""Forward any call_permission_reply messages to the calling module.

	Idempotent: `call_service.process_permission_event` is safe to
	re-invoke — it upserts the permission row by user_wa_id +
	whatsapp_account.
	"""
	phone_number_id = (value.get("metadata") or {}).get("phone_number_id") or ""
	if not phone_number_id:
		return
	from msuite_whatsapp.services.calls import call_service

	for msg in value.get("messages") or []:
		interactive = msg.get("interactive") or {}
		if interactive.get("type") != "call_permission_reply":
			continue
		# `process_permission_event` expects the phone_number_id on the
		# message itself (set by the provider when forwarding via the
		# dedicated call webhook). Inject it here so the regular-messages
		# path looks identical to the call-webhook path.
		msg_with_pid = dict(msg)
		msg_with_pid["_phone_number_id"] = phone_number_id
		try:
			call_service.process_permission_event(msg_with_pid)
		except Exception:
			logger.exception(
				"call_permission_reply routing failed for msg %s",
				msg.get("id", ""),
			)


def _resolve_whatsapp_account_for_value(value: dict, inbox_name: str) -> str:
	"""Same account-stamping lookup `_ingest_whatsapp_messages` uses."""
	phone_id = (value.get("metadata") or {}).get("phone_number_id") or ""
	wa_account = ""
	if phone_id:
		wa_account = frappe.db.get_value("WhatsApp Phone Number", {"phone_number_id": phone_id}, "parent")
	if not wa_account:
		wa_account = frappe.db.get_value("Inbox", inbox_name, "whatsapp_account") or ""
	return wa_account


def _ingest_smb_message_echoes(value: dict, inbox_name: str) -> None:
	"""Mirror messages the business sent from the WhatsApp Business app."""
	wa_account = _resolve_whatsapp_account_for_value(value, inbox_name)
	events = whatsapp.parse_smb_echoes(value, inbox_name)
	for event in events:
		event.whatsapp_account = wa_account
		try:
			result = dispatch(event)
		except Exception:
			logger.exception("SMB echo dispatch failed: %s", event.platform_message_id)
			continue
		if result.get("message") and event.attachments:
			frappe.enqueue(
				"msuite_whatsapp.services.channels.inbox_channel.resolve_media_for_message",
				queue="short",
				channel_message_name=result["message"],
			)


def _ingest_whatsapp_history(value: dict, inbox_name: str) -> None:
	"""Ingest one chunk of the one-time coexistence history sync.

	Chunks arrive over three phases (0-1 day, 1-90, 90-180); every event
	is dispatched with side effects suppressed (no auto-replies / lead
	storms for months-old messages). Media for messages older than 14
	days is never synced — those arrive as placeholders.

	Error code 2593109 means the business turned history sharing off in
	the app — recorded on the account so the UI can stop saying
	"Requested" forever.
	"""
	wa_account = _resolve_whatsapp_account_for_value(value, inbox_name)

	for err in value.get("errors") or []:
		if str(err.get("code")) == "2593109" and wa_account:
			frappe.db.set_value(
				"WhatsApp Account",
				wa_account,
				"coexistence_history_sync",
				"Declined",
				update_modified=False,
			)
			logger.info("Coexistence history sync declined by business (%s)", wa_account)
			return

	events, chunk_meta = whatsapp.parse_history(value, inbox_name)
	ingested = 0
	for event in events:
		event.whatsapp_account = wa_account
		try:
			result = dispatch(event)
		except Exception:
			logger.exception("History dispatch failed: %s", event.platform_message_id)
			continue
		if result.get("message"):
			ingested += 1
			# Media ids are only valid for messages < 14 days old; the
			# resolver is best-effort and leaves older ones as-is.
			if event.attachments:
				frappe.enqueue(
					"msuite_whatsapp.services.channels.inbox_channel.resolve_media_for_message",
					queue="short",
					channel_message_name=result["message"],
				)

	if wa_account:
		try:
			progress = int(chunk_meta.get("progress") or 0)
		except (TypeError, ValueError):
			progress = 0
		status = "Completed" if progress >= 100 else "Receiving"
		frappe.db.set_value(
			"WhatsApp Account",
			wa_account,
			"coexistence_history_sync",
			status,
			update_modified=False,
		)
	logger.info(
		"Coexistence history chunk ingested: %s events (phase=%s chunk=%s progress=%s)",
		ingested,
		chunk_meta.get("phase"),
		chunk_meta.get("chunk_order"),
		chunk_meta.get("progress"),
	)


def _ingest_smb_state_sync(value: dict) -> None:
	"""Contacts from the business's phone app → names for our threads.

	The phone app's address book is the richest name source we'll ever
	get for WhatsApp identities (profile pushnames are self-chosen and
	often junk). Upserted as Channel Handle records (`WhatsApp Contact`
	is deprecated — its controller blocks new inserts): existing handles
	get their display_name enriched, unknown numbers get a fresh handle
	so the name is already there when the contact's first message lands.
	"""
	for item in value.get("state_sync") or []:
		if item.get("type") != "contact":
			continue
		contact = item.get("contact") or {}
		phone = contact.get("phone_number") or ""
		digits = "".join(c for c in phone if c.isdigit())
		if not digits:
			continue
		full_name = (contact.get("full_name") or contact.get("first_name") or "").strip()
		action = item.get("action") or "add"
		if action == "remove" or not full_name:
			continue

		handle = frappe.db.get_value(
			"Channel Handle",
			{"channel_type": ChannelType.WHATSAPP, "platform_handle": digits},
			["name", "display_name"],
			as_dict=True,
		)
		if handle:
			if not handle.display_name or handle.display_name == digits:
				frappe.db.set_value(
					"Channel Handle",
					handle.name,
					"display_name",
					full_name,
					update_modified=False,
				)
				frappe.db.sql(
					"""UPDATE `tabConversation`
					   SET customer_name = %s
					   WHERE channel_handle = %s
					     AND (customer_name IS NULL OR customer_name = '' OR customer_name = %s)""",
					(full_name, handle.name, digits),
				)
		else:
			try:
				frappe.get_doc(
					{
						"doctype": "Channel Handle",
						"channel_type": ChannelType.WHATSAPP,
						"platform_handle": digits,
						"display_name": full_name,
						"match_status": "Unmatched",
					}
				).insert(ignore_permissions=True)
			except Exception:
				logger.exception("Channel Handle upsert from state_sync failed for %s", digits)


def _ingest_coexistence_account_event(value: dict, waba_id: str) -> None:
	"""Track offboard / reconnect / partner-removed on the dual-use account.

	ACCOUNT_OFFBOARDED — the business re-registered or switched devices;
	dual-use pauses until they re-run Embedded Signup (webhook
	ACCOUNT_RECONNECTED follows). PARTNER_REMOVED — the business hit
	"Disconnect Account" in the app's Business Platform settings.
	"""
	if not waba_id:
		return
	wa_account = frappe.db.get_value("WhatsApp Account", {"waba_id": waba_id}, "name")
	if not wa_account:
		return
	event = (value.get("event") or "").upper()
	if event in ("ACCOUNT_OFFBOARDED", "PARTNER_REMOVED"):
		frappe.db.sql(
			"UPDATE `tabWhatsApp Phone Number` SET is_on_biz_app = 0 WHERE parent = %s",
			(wa_account,),
		)
		if event == "PARTNER_REMOVED":
			frappe.db.set_value(
				"WhatsApp Account",
				wa_account,
				"status",
				"Inactive",
				update_modified=False,
			)
		logger.warning("Coexistence %s for WhatsApp Account %s", event, wa_account)
	elif event == "ACCOUNT_RECONNECTED":
		frappe.db.set_value(
			"WhatsApp Account",
			wa_account,
			"status",
			"Active",
			update_modified=False,
		)
		logger.info("Coexistence ACCOUNT_RECONNECTED for WhatsApp Account %s", wa_account)


def _ingest_whatsapp_calls(value: dict) -> None:
	"""Route every `calls[]` event through the calling module.

	Meta sends call lifecycle events as `value.calls[]` (with `field: "calls"`),
	NOT as messages. Each entry has `event` ∈ {`connect`, `terminate`, ...}
	plus `direction` (`USER_INITIATED` / `BUSINESS_INITIATED`), `status`,
	and the WebRTC `session.sdp` for the connect event.

	We inject `_phone_number_id` (the calling service expects it that way —
	same shape as the dedicated call webhook receiver passes) and hand off
	to `call_service.process_call_event`. That function handles:
	  • new inbound calls         → router decides target user, scoped overlay
	  • busy auto-reject          → if the routed agent is on another call
	  • status updates            → Ringing → Connected → Completed
	  • SDP-answer forwarding     → outbound WebRTC handshake
	"""
	phone_number_id = (value.get("metadata") or {}).get("phone_number_id") or ""
	if not phone_number_id:
		logger.warning("calls webhook missing metadata.phone_number_id; skipping")
		return
	from msuite_whatsapp.services.calls import call_service

	for call in value.get("calls") or []:
		if not isinstance(call, dict):
			continue
		# `process_call_event` reads `_phone_number_id` off the event to
		# find the right WhatsApp Account — keep the shape identical to the
		# dedicated call webhook so both entry points behave the same.
		call_with_pid = dict(call)
		call_with_pid["_phone_number_id"] = phone_number_id
		try:
			call_service.process_call_event(call_with_pid)
		except Exception:
			logger.exception(
				"Call event dispatch failed for call_id=%s event=%s",
				call.get("id"),
				call.get("event"),
			)


def _ingest_whatsapp_statuses(value: dict) -> None:
	"""Mirror Meta status updates onto the matching outbound Channel Message.

	We `frappe.get_doc(...).save()` rather than `set_value` so the
	Channel Message.on_update controller fires and publishes the
	`msuite_inbox:message_status` realtime event. That's the only way
	the inbox UI hears about the transition.

	Rows are matched by message id only, so a status without `recipient_id`
	(sent to a BSUID) or without `contacts` (every `failed` status) still
	applies. A `recipient_user_id` is recorded on the phone handle, see
	_learn_bsuid_from_status.
	"""
	for status_row in value.get("statuses") or []:
		platform_message_id = status_row.get("id")
		new_status = status_row.get("status")
		if not (platform_message_id and new_status):
			continue
		# `played` (voice) is a read-equivalent: Channel Message.status has no
		# "played" option, so store READ and keep the play time in platform_payload.
		is_played = str(new_status).lower() == WHATSAPP_STATUS_PLAYED
		if is_played:
			new_status = MessageStatus.READ
		msg_name = frappe.db.get_value(
			"Channel Message",
			{"platform_message_id": platform_message_id},
			"name",
		)
		if not msg_name:
			recipient_phone = status_row.get("recipient_id")
			if recipient_phone and not is_bsuid(recipient_phone) and new_status:
				formatted_status = "Read" if new_status.lower() == "read" else ("Delivered" if new_status.lower() == "delivered" else ("Failed" if new_status.lower() == "failed" else new_status.capitalize()))
				recip_rows = frappe.db.sql(
					"""
					SELECT name, status FROM `tabWhatsApp Recipient`
					WHERE parenttype = 'Bulk WhatsApp Message'
					  AND (mobile_number = %s OR REPLACE(mobile_number, '+', '') = %s)
					ORDER BY modified DESC LIMIT 5
					""",
					(recipient_phone, recipient_phone),
					as_dict=True,
				)
				for rrow in recip_rows:
					cur_rank = _STATUS_RANK.get(str(rrow.status).lower(), 0)
					target_rank = _STATUS_RANK.get(new_status.lower(), 0)
					if target_rank >= cur_rank:
						frappe.db.set_value("WhatsApp Recipient", rrow.name, "status", formatted_status, update_modified=False)
			continue
		try:
			doc = frappe.get_doc("Channel Message", msg_name)
			# Meta doesn't guarantee delivery order — a late "delivered" must
			# not demote a message already marked "read". Statuses outside
			# the ranked lifecycle (e.g. "failed") are always applied.
			new_rank = _STATUS_RANK.get(new_status)
			if new_rank is None or _STATUS_RANK.get(doc.status, -1) < new_rank:
				doc.status = new_status
			error_summary = _format_status_error(status_row)
			doc.status_error = error_summary
			if error_summary:
				doc.failure_reason = error_summary
			meta_conv = (status_row.get("conversation") or {}).get("id")
			if meta_conv:
				doc.meta_conversation_id = meta_conv
			_apply_pricing_category(doc, status_row)
			if is_played:
				_record_played_at(doc, status_row.get("timestamp"))
			doc.save(ignore_permissions=True)
			_learn_bsuid_from_status(getattr(doc, "channel_handle", None), status_row, value.get("contacts"))
		except Exception:
			logger.exception(
				"Channel Message status update failed: %s -> %s",
				platform_message_id,
				new_status,
			)


def _extract_pricing_category(status_row: dict) -> str:
	"""Return the pricing category of a status webhook row, or "" when Meta did not send one.

	Uses `pricing.category`; falls back to `conversation.origin.type` only when that is
	`marketing_lite`. Tolerates absent/null/non-dict `pricing` and `conversation`. The value is
	stripped and truncated to the Channel Message field length.
	"""
	pricing = status_row.get("pricing")
	category = pricing.get("category") if isinstance(pricing, dict) else None
	if not (category and str(category).strip()):
		conversation = status_row.get("conversation")
		origin = conversation.get("origin") if isinstance(conversation, dict) else None
		origin_type = origin.get("type") if isinstance(origin, dict) else None
		category = origin_type if origin_type == WHATSAPP_PRICING_CATEGORY_MARKETING_LITE else None
	return str(category or "").strip()[:CHANNEL_MESSAGE_PRICING_CATEGORY_MAX_LEN]


def _apply_pricing_category(doc, status_row: dict) -> None:
	"""Record pricing category and corroborate the send route on a Channel Message doc (no save).

	Never overwrites a non-blank `pricing_category` or `send_path` with blank. A blank `send_path`
	is inferred from the category (`marketing_lite` -> marketing_messages, `marketing` -> cloud_api);
	an existing non-blank `send_path` is kept and a disagreement is logged.

	Args:
	    doc:        Channel Message document being updated.
	    status_row: One entry of the webhook `statuses` array.
	"""
	category = _extract_pricing_category(status_row)
	if not category:
		return
	# getattr: tolerate a site that has not run migrate for the new columns yet.
	if getattr(doc, "pricing_category", None) != category:
		doc.pricing_category = category
	inferred_path = _SEND_PATH_BY_PRICING_CATEGORY.get(category)
	if not inferred_path:
		return
	current_path = getattr(doc, "send_path", None)
	if not current_path:
		doc.send_path = inferred_path
	elif current_path != inferred_path:
		logger.warning(
			"Channel Message send_path %s disagrees with webhook pricing category %s",
			current_path,
			category,
		)


def _learn_bsuid_from_status(handle_name: str | None, status_row: dict, contacts: list | None) -> None:
	"""Store a status's `recipient_user_id` on the message's Channel Handle.

	Meta sends the BSUID on sent/delivered/read statuses even while the
	phone is still visible, so recording it now keeps the thread when the
	phone later disappears. Conservative: only when the status also names
	the phone (`recipient_id`) and it equals the handle's phone, the handle
	has no BSUID yet, and no other WhatsApp handle holds it.

	Side effects: one `frappe.db.set_value` on Channel Handle. Never raises
	(failures are logged) so status ingestion is unaffected.
	"""
	identity = whatsapp.extract_whatsapp_identity(
		status_row,
		contacts,
		phone_key="recipient_id",
		user_id_key="recipient_user_id",
		parent_key="recipient_parent_user_id",
	)
	if not (handle_name and identity["bsuid"] and identity["phone"]):
		return
	try:
		handle = frappe.db.get_value(
			"Channel Handle", handle_name, ["channel_type", "platform_handle", "bsuid"], as_dict=True
		)
		if not handle or handle.channel_type != ChannelType.WHATSAPP or handle.bsuid:
			return
		if handle.platform_handle != identity["phone"]:
			return
		if frappe.db.exists("Channel Handle", {"channel_type": ChannelType.WHATSAPP, "bsuid": identity["bsuid"]}):
			return
		values = {"bsuid": identity["bsuid"]}
		if identity["parent_bsuid"]:
			values["parent_bsuid"] = identity["parent_bsuid"]
		frappe.db.set_value("Channel Handle", handle_name, values, update_modified=False)
	except Exception:
		logger.exception("Recording BSUID from status failed for handle %s", handle_name)


def _record_played_at(doc, timestamp) -> None:
	"""Merge `played_at` (Meta's status timestamp, or now) into doc.platform_payload JSON.

	Side effect: mutates `doc.platform_payload`; caller saves.
	"""
	try:
		payload = frappe.parse_json(doc.platform_payload) if doc.platform_payload else {}
	except Exception:
		payload = {}
	if not isinstance(payload, dict):
		payload = {}
	payload["played_at"] = str(timestamp or int(time.time()))
	doc.platform_payload = payload


def _ingest_template_status_update(value: dict, waba_id: str) -> None:
	"""Apply a push-based template lifecycle event from Meta.

	Lets the template list reflect approval/rejection/pause/disable the
	moment Meta decides it, instead of only on the next manual
	"Sync from Meta" click.
	"""
	meta_template_id = str(value.get("message_template_id") or "")
	event = (value.get("event") or "").upper()
	reason = value.get("reason") or ""
	if not (meta_template_id and event):
		return

	name = frappe.db.get_value("WhatsApp Templates", {"id": meta_template_id}, "name")
	if not name:
		logger.info(
			"Template status update for unknown id=%s (waba=%s, event=%s) — "
			"run Sync from Meta to pick it up.",
			meta_template_id,
			waba_id,
			event,
		)
		return

	updates = {}
	new_status = _TEMPLATE_EVENT_TO_STATUS.get(event)
	if new_status:
		updates["status"] = new_status
	if reason:
		updates["rejection_reason"] = reason
	elif new_status == "APPROVED":
		updates["rejection_reason"] = ""
	if not updates:
		return

	frappe.db.set_value("WhatsApp Templates", name, updates, update_modified=False)
	logger.info("Template %s -> %s (event=%s)", name, new_status or event, event)


def apply_bsuid_update(previous_bsuid: str, current_bsuid: str, parent_bsuid: str = "") -> bool:
	"""Apply a BSUID change from previous_bsuid to current_bsuid on a WhatsApp Channel Handle.

	Rules:
	  1. Validates previous_bsuid and current_bsuid using is_bsuid. Malformed
	     values or injection strings are logged as warnings and skipped.
	  2. If previous_bsuid == current_bsuid, no-op (returns True).
	  3. Updates matching Channel Handle only when its existing bsuid matches
	     previous_bsuid exactly. Never rewrites or merges an unrelated handle.
	  4. If no handle matches previous_bsuid:
	     - Checks if a handle already owns current_bsuid (duplicate delivery);
	       logs info and returns True.
	     - Otherwise logs info and returns False (no-op).
	  5. If another handle already owns current_bsuid: logs warning and skips
	     to prevent uniqueness violations or invalid merges.
	  6. If the matching handle is BSUID-only (platform_handle == previous_bsuid),
	     also updates platform_handle and display_name (if matching previous_bsuid)
	     to current_bsuid. If the handle has a real phone number, platform_handle
	     is never modified.

	Args:
		previous_bsuid: The old business-scoped user id.
		current_bsuid: The new business-scoped user id.
		parent_bsuid: Optional parent business-scoped user id.

	Returns:
		bool: True if an update was applied or was already in place (idempotent),
		      False otherwise.
	"""
	prev = str(previous_bsuid or "").strip()
	curr = str(current_bsuid or "").strip()
	parent = str(parent_bsuid or "").strip()

	if not (is_bsuid(prev) and is_bsuid(curr)):
		logger.warning("WhatsApp BSUID update: invalid or malformed BSUID previous=%r, current=%r; skipped", prev, curr)
		return False

	if prev == curr:
		logger.info("WhatsApp BSUID update: previous equals current BSUID (%s); no-op", prev)
		return True

	matching = frappe.db.get_value(
		"Channel Handle",
		{"channel_type": ChannelType.WHATSAPP, "bsuid": prev},
		["name", "platform_handle", "bsuid", "parent_bsuid", "phone", "username", "display_name"],
		as_dict=True,
	)

	if not matching:
		existing = frappe.db.get_value(
			"Channel Handle",
			{"channel_type": ChannelType.WHATSAPP, "bsuid": curr},
			["name", "platform_handle", "bsuid"],
			as_dict=True,
		)
		if existing:
			logger.info(
				"WhatsApp BSUID update: handle %s already has current BSUID %s (duplicate delivery); no-op",
				existing.name,
				curr,
			)
			return True
		logger.info("WhatsApp BSUID update: no matching Channel Handle for previous BSUID %s; no-op", prev)
		return False

	conflict = frappe.db.get_value(
		"Channel Handle",
		{"channel_type": ChannelType.WHATSAPP, "bsuid": curr, "name": ("!=", matching.name)},
		"name",
	)
	if conflict:
		logger.warning(
			"WhatsApp BSUID update: cannot update handle %s to BSUID %s because handle %s already owns it; skipped",
			matching.name,
			curr,
			conflict,
		)
		return False

	updates = {"bsuid": curr}
	if parent and is_bsuid(parent):
		updates["parent_bsuid"] = parent

	if matching.platform_handle == prev:
		# BSUID-only placeholder handle
		ph_conflict = frappe.db.get_value(
			"Channel Handle",
			{"channel_type": ChannelType.WHATSAPP, "platform_handle": curr, "name": ("!=", matching.name)},
			"name",
		)
		if ph_conflict:
			logger.warning(
				"WhatsApp BSUID update: cannot update platform_handle on %s; %s already has %s",
				matching.name,
				ph_conflict,
				curr,
			)
			return False
		updates["platform_handle"] = curr
		if matching.display_name == prev:
			updates["display_name"] = curr

	frappe.db.set_value("Channel Handle", matching.name, updates, update_modified=True)
	frappe.clear_document_cache("Channel Handle", matching.name)
	logger.info("WhatsApp BSUID update applied on handle %s: %s -> %s", matching.name, prev, curr)
	return True


def _handle_user_id_update(value: dict) -> None:
	"""Handle a Meta user_id_update webhook change value.

	Processes BSUID rotation events from Meta where previous and current
	BSUIDs are provided.

	Args:
		value: The change value dictionary from Meta's user_id_update webhook.
	"""
	if not isinstance(value, dict):
		logger.warning("WhatsApp user_id_update: non-dict value received; skipped")
		return

	updates = value.get(KEY_USER_ID_UPDATE) or []
	if isinstance(updates, dict):
		updates = [updates]
	elif not isinstance(updates, list):
		logger.warning("WhatsApp user_id_update: unreadable user_id_update payload; skipped")
		return

	for item in updates:
		if not isinstance(item, dict):
			continue
		user_id_dict = item.get(KEY_USER_ID)
		if not isinstance(user_id_dict, dict):
			continue
		prev = user_id_dict.get(KEY_PREVIOUS) or ""
		curr = user_id_dict.get(KEY_CURRENT) or ""
		parent_dict = item.get(KEY_PARENT_USER_ID)
		parent_curr = ""
		if isinstance(parent_dict, dict):
			parent_curr = parent_dict.get(KEY_CURRENT) or ""
		elif isinstance(parent_dict, str):
			parent_curr = parent_dict

		apply_bsuid_update(prev, curr, parent_curr)


def _handle_system_user_changed_user_id(message: dict) -> None:
	"""Handle a WhatsApp system message of type user_changed_user_id.

	Extracts previous and current BSUID from the system message payload
	or body text and applies the BSUID update.

	Args:
		message: One message dictionary from value.messages.
	"""
	if not isinstance(message, dict):
		return

	system = message.get(KEY_SYSTEM) or {}
	if not isinstance(system, dict) or system.get(KEY_TYPE) != SYSTEM_TYPE_USER_CHANGED_USER_ID:
		return

	curr = str(system.get(KEY_USER_ID) or message.get(KEY_FROM_USER_ID) or "").strip()
	parent = str(system.get(KEY_PARENT_USER_ID) or message.get(KEY_FROM_PARENT_USER_ID) or "").strip()

	prev = ""
	if system.get("previous_user_id"):
		prev = str(system.get("previous_user_id")).strip()
	elif system.get("old_user_id"):
		prev = str(system.get("old_user_id")).strip()
	elif isinstance(system.get(KEY_USER_ID), dict):
		prev = str(system.get(KEY_USER_ID, {}).get(KEY_PREVIOUS) or "").strip()

	if not prev:
		body = str(system.get(KEY_BODY) or "").strip()
		match = re.search(
			r"changed from\s+([A-Za-z]{2}\.(?:ENT\.)?[A-Za-z0-9]{1,128})\s+to\s+([A-Za-z]{2}\.(?:ENT\.)?[A-Za-z0-9]{1,128})",
			body,
			re.IGNORECASE,
		)
		if match:
			prev = match.group(1).strip()
			if not curr:
				curr = match.group(2).strip()

	if prev and curr:
		apply_bsuid_update(prev, curr, parent)
	else:
		logger.warning(
			"WhatsApp system message user_changed_user_id could not extract BSUID: prev=%r, curr=%r",
			prev,
			curr,
		)


def _handle_business_username_update(value: dict) -> None:
	"""Handle business_username_updates and legacy phone_number_username_update webhooks.

	Stores the approved/updated username on the matching WhatsApp Channel Handle.
	Never touches platform_handle.

	Args:
		value: The change value dictionary from Meta's username webhook.
	"""
	if not isinstance(value, dict):
		return

	display_phone = str(value.get(KEY_DISPLAY_PHONE_NUMBER) or "").strip()
	phone_digits = "".join(c for c in display_phone if c.isdigit())
	if not phone_digits:
		logger.warning("WhatsApp username update: missing or empty display_phone_number in %r", value)
		return

	status = str(value.get(KEY_STATUS) or "").lower()
	decision = str(value.get(KEY_DECISION) or "").upper()

	if decision == "REJECTED":
		logger.info("WhatsApp username update rejected for phone %s; no-op", display_phone)
		return

	if status == "deleted":
		new_username = ""
	else:
		new_username = str(value.get(KEY_USERNAME) or value.get(KEY_REQUESTED_USERNAME) or "").strip()

	handles = frappe.get_all(
		"Channel Handle",
		filters={"channel_type": ChannelType.WHATSAPP, "phone": phone_digits},
		fields=["name", "platform_handle", "phone", "username"],
	)
	if not handles:
		handles = frappe.get_all(
			"Channel Handle",
			filters={
				"channel_type": ChannelType.WHATSAPP,
				"platform_handle": ["in", [display_phone, phone_digits, f"+{phone_digits}"]],
			},
			fields=["name", "platform_handle", "phone", "username"],
		)

	valid_handles = [h for h in handles if customer_phone(h.platform_handle) and not is_bsuid(h.platform_handle)]

	if not valid_handles:
		logger.info("WhatsApp username update: no matching Channel Handle for phone %s; no-op", display_phone)
		return

	for h in valid_handles:
		if (h.username or "") == new_username:
			logger.info(
				"WhatsApp username update: handle %s already has username %r (idempotent); no-op",
				h.name,
				new_username,
			)
			continue
		frappe.db.set_value("Channel Handle", h.name, {"username": new_username}, update_modified=True)
		frappe.clear_document_cache("Channel Handle", h.name)
		logger.info("WhatsApp username update: updated handle %s username to %r", h.name, new_username)


def _format_status_error(status_row: dict) -> str:
	errors = status_row.get("errors") or []
	if not errors:
		return ""
	err = errors[0]
	return f"[{err.get('code', '')}] {err.get('title', '')}: {err.get('message', '')}"[:500]


def _resolve_whatsapp_inbox_and_account(
	phone_id: str | None = None,
	waba_id: str | None = None,
) -> tuple[str, str | None]:
	"""Resolve (inbox_name, account_name) for a given phone_number_id and/or waba_id.

	Ensures that inbound traffic is routed to the WhatsApp Account's dedicated Inbox,
	creating the inbox if it does not exist yet, rather than incorrectly dumping messages
	into another account's inbox or crashing on missing doctypes.
	"""
	account_name = None
	phone_id = str(phone_id).strip() if phone_id else None
	waba_id = str(waba_id).strip() if waba_id else None

	try:
		if phone_id:
			account_name = frappe.db.get_value("WhatsApp Phone Number", {"phone_number_id": phone_id}, "parent")

		if not account_name and waba_id:
			account_name = frappe.db.get_value("WhatsApp Account", {"waba_id": waba_id}, "name")

		if not account_name:
			account_name = find_default_phone_account("incoming")
			if not account_name:
				active_waba = frappe.get_all("WhatsApp Account", filters={"status": "Active"}, pluck="name")
				if len(active_waba) == 1:
					account_name = active_waba[0]

		if account_name:
			# 1. Match inbox directly linked to this WhatsApp Account
			inbox = frappe.db.get_value(
				"Inbox",
				{"whatsapp_account": account_name, "channel_type": ChannelType.WHATSAPP, "status": "Active"},
				"name",
			)
			if not inbox:
				inbox = frappe.db.get_value(
					"Inbox",
					{"whatsapp_account": account_name, "channel_type": ChannelType.WHATSAPP},
					"name",
				)

			# 2. Match inbox by canonical per-account name
			if not inbox:
				try:
					from msuite_inbox.inbox.services.inbox_connector import per_account_whatsapp_inbox_name
					cand = per_account_whatsapp_inbox_name(account_name)
					if frappe.db.exists("Inbox", cand):
						inbox = cand
				except Exception:
					pass

			# 3. Match any active WhatsApp Inbox with unassigned account
			if not inbox:
				inbox = frappe.db.get_value(
					"Inbox",
					{"channel_type": ChannelType.WHATSAPP, "whatsapp_account": ("in", ["", None]), "status": "Active"},
					"name",
				)

			# 4. Check for standard "WhatsApp Inbox"
			if not inbox and frappe.db.exists("Inbox", "WhatsApp Inbox"):
				inbox = "WhatsApp Inbox"

			# 5. Check for ANY active WhatsApp Inbox
			if not inbox:
				inbox = frappe.db.get_value(
					"Inbox",
					{"channel_type": ChannelType.WHATSAPP, "status": "Active"},
					"name",
				)

			# 6. Create dedicated inbox if none exists
			if not inbox:
				try:
					from msuite_inbox.inbox.services.inbox_connector import per_account_whatsapp_inbox_name
					inbox = per_account_whatsapp_inbox_name(account_name)
				except Exception:
					inbox = f"{account_name} - WhatsApp"[:80]
				_ensure_default_inbox_exists(inbox, ChannelType.WHATSAPP, whatsapp_account=account_name)

			return inbox, account_name

	except Exception:
		logger.exception(
			"Failed to resolve dedicated WhatsApp inbox for phone_id=%s waba_id=%s",
			phone_id,
			waba_id,
		)

	# Global fallback: return any active WhatsApp inbox or ensure "WhatsApp Inbox"
	fallback = frappe.db.get_value("Inbox", {"channel_type": ChannelType.WHATSAPP, "status": "Active"}, "name")
	if not fallback:
		fallback = "WhatsApp Inbox"
		try:
			_ensure_default_inbox_exists(fallback, ChannelType.WHATSAPP)
		except Exception:
			pass

	return fallback, account_name


def _find_whatsapp_inbox(payload: dict) -> str | None:
	"""Resolve a WhatsApp Inbox from a webhook payload."""
	phone_id = None
	waba_id = None
	try:
		for entry in payload.get("entry") or []:
			waba_id = entry.get("id") or None
			for change in entry.get("changes") or []:
				phone_id = (change.get("value") or {}).get("metadata", {}).get("phone_number_id")
				if phone_id:
					break
			if phone_id or waba_id:
				break
	except Exception:
		pass
	inbox, _ = _resolve_whatsapp_inbox_and_account(phone_id=phone_id, waba_id=waba_id)
	return inbox
