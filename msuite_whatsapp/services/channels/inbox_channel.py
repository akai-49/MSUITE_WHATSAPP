"""
WhatsApp channel — parse Meta WhatsApp webhook payloads + send outbound.

Channel-specific mapping/parsing logic lives entirely in this module by
design (INBOX_ARCHITECTURE_AUDIT.md §10) — `services/normalizer.py`
stays free of any per-channel `type` string knowledge so it remains a
genuinely channel-agnostic boundary other channel modules can rely on.

Delivery-status updates (sent / delivered / read / failed) are ingested
by `api/v1/webhook.py:_ingest_whatsapp_statuses`, which mirrors them
directly onto the matching `Channel Message` row by
`platform_message_id` — there is no legacy doctype or shadow field
involved; `Channel Message` is the only source of truth.
"""

from __future__ import annotations

import os
import posixpath
import re
from typing import Any
from urllib.parse import unquote, urlparse

import frappe
from frappe import _
from frappe.utils import cint

from msuite_core.constants import WHATSAPP_INTERACTIVE_BODY_MAX
from msuite_core.utils.files import is_local_file_url, resolve_frappe_path
from msuite_core.utils.phone import customer_phone, is_bsuid  # noqa: F401
from msuite_inbox.inbox.constants import (
	LOGGER_NAME,
	STICKER_MIME,
	ChannelType,
	Direction,
	MessageContentType,
	MessageStatus,
	SenderType,
	SourceType,
)
from msuite_whatsapp.constants import (
	BSUID_AUTH_TEMPLATE_ERROR_MESSAGE,
	CONTACT_ORIGIN_CONTACT_REQUEST,
	DEFAULT_REQUEST_CONTACT_INFO_BODY,
	LOCAL_PRIVATE_FILE_PATH_PREFIX,
	MEDIA_SEND_KINDS,
	META_BUTTON_TYPE_REQUEST_CONTACT_INFO,
	META_ERROR_BSUID_UNSUPPORTED,
	META_ERROR_BSUID_UNSUPPORTED_MSG,
	META_INTERACTIVE_TYPE_REQUEST_CONTACT_INFO,
	META_RECIPIENT_FIELD_BSUID,
	META_RECIPIENT_FIELD_PHONE,
	META_RECIPIENT_TYPE_INDIVIDUAL,
	UNSUPPORTED_BSUID_BUTTON_TYPES,
	UNSUPPORTED_BSUID_OTP_BUTTON_TYPES,
	UNSUPPORTED_BSUID_TEMPLATE_CATEGORIES,
	UNSUPPORTED_BSUID_TEMPLATE_TYPES,
)
from msuite_inbox.inbox.services import ad_referral
from msuite_inbox.inbox.services.normalizer import (
	NormalizedAttachment,
	NormalizedEvent,
	excerpt,
	parse_unix_timestamp,
)
from msuite_whatsapp.integrations.meta.client import retry_kind
from msuite_whatsapp.utils import get_whatsapp_account
from msuite_whatsapp.utils.send import MetaAPIError, download_media, fetch_media_url, send_to_meta

logger = frappe.logger(LOGGER_NAME)


# Inbound Meta `type` string → MessageContentType. Owned entirely by this
# channel module — see module docstring.
WHATSAPP_TYPE_TO_CONTENT_TYPE: dict[str, str] = {
	"text": MessageContentType.TEXT,
	"image": MessageContentType.IMAGE,
	"video": MessageContentType.VIDEO,
	"audio": MessageContentType.AUDIO,
	"document": MessageContentType.DOCUMENT,
	"sticker": MessageContentType.STICKER,
	"location": MessageContentType.LOCATION,
	"contacts": MessageContentType.CONTACTS,
	"reaction": MessageContentType.REACTION,
	"interactive": MessageContentType.INTERACTIVE,
	"button": MessageContentType.INTERACTIVE,
	"order": MessageContentType.ORDER,
}


def whatsapp_content_type(meta_type: str) -> str:
	return WHATSAPP_TYPE_TO_CONTENT_TYPE.get(meta_type, MessageContentType.UNKNOWN)


# Outbound `type` → MessageContentType. Kept in sync with
# WHATSAPP_TYPE_TO_CONTENT_TYPE above so inbound and outbound rows on the
# same conversation render with identical content_types.
_MEDIA_KIND_TO_CONTENT_TYPE = {
	"image": MessageContentType.IMAGE,
	"video": MessageContentType.VIDEO,
	"audio": MessageContentType.AUDIO,
	"document": MessageContentType.DOCUMENT,
	"sticker": MessageContentType.STICKER,
}


def _clean_bsuid(value: Any) -> str:
	"""Stripped `value` if it is a well-formed BSUID, else ""."""
	return value.strip() if is_bsuid(value) else ""


def extract_whatsapp_identity(
	item: dict,
	contacts: list | None = None,
	*,
	phone_key: str = "from",
	user_id_key: str = "from_user_id",
	parent_key: str = "from_parent_user_id",
) -> dict:
	"""Pull the customer's identifiers out of one webhook item. Pure.

	Used for messages (`from`/`from_user_id`), echoes (`to`/`to_user_id`)
	and statuses (`recipient_id`/`recipient_user_id`) via the key params.
	The phone key may be absent for WhatsApp username users (Meta omits the
	key; an empty string is treated the same). The matching `contacts[]`
	entry is the one whose `user_id` or `wa_id` equals the item's ids; a
	lone contact is used as-is (pre-BSUID behaviour), several unmatched
	contacts yield none.

	Args:
		item: one `messages[]` / `message_echoes[]` / `statuses[]` dict.
		contacts: the payload's `contacts[]` (may be None or missing).
		phone_key, user_id_key, parent_key: item keys to read.

	Returns:
		{"phone", "bsuid", "parent_bsuid", "username", "name"}; every value
		a str, "" when unknown. `phone` is returned exactly as Meta sent it.
		Malformed BSUIDs come back as "".
	"""
	bsuid = _clean_bsuid(item.get(user_id_key))
	phone = str(item.get(phone_key) or "")
	if is_bsuid(phone):
		bsuid = bsuid or phone
		phone = ""
	parent = _clean_bsuid(item.get(parent_key))

	if not phone and item.get("type") == "contacts":
		for c in item.get("contacts") or []:
			origin = c.get("origin")
			if origin == CONTACT_ORIGIN_CONTACT_REQUEST or (
				isinstance(origin, dict) and origin.get("type") == CONTACT_ORIGIN_CONTACT_REQUEST
			):
				for p in c.get("phones") or []:
					val = p.get("wa_id") or p.get("phone")
					if val:
						phone = _digits(str(val))
						break
				if phone:
					break

	contact: dict = {}
	entries = [c for c in (contacts or []) if isinstance(c, dict)]
	for c in entries:
		if (bsuid and c.get("user_id") == bsuid) or (phone and _digits(c.get("wa_id")) == _digits(phone)):
			contact = c
			break
	else:
		if len(entries) == 1:
			contact = entries[0]

	if contact:
		bsuid = bsuid or _clean_bsuid(contact.get("user_id"))
		parent = parent or _clean_bsuid(contact.get("parent_user_id"))
	profile = contact.get("profile") or {}
	return {
		"phone": phone,
		"bsuid": bsuid,
		"parent_bsuid": parent,
		"username": str(profile.get("username") or "").strip(),
		"name": str(profile.get("name") or "").strip(),
	}


# ── Inbound parse ────────────────────────────────────────────────────────


def parse_change(value: dict, inbox_name: str) -> list[NormalizedEvent]:
	"""Convert one Meta `entry[].changes[].value` payload into events.

	Meta batches messages, so this returns a list. Empty list when the
	payload is a status update (delivery receipts) — those are handled
	by the legacy webhook so we don't insert duplicates. Each message is
	paired with its own `contacts[]` entry (see extract_whatsapp_identity);
	the sender name falls back from profile name to WhatsApp username.
	"""
	messages = value.get("messages") or []
	if not messages:
		return []

	contacts = value.get("contacts") or []
	events: list[NormalizedEvent] = []
	for message in messages:
		identity = extract_whatsapp_identity(message, contacts)
		sender_name = identity["name"] or identity["username"]
		event = _normalise_message(message, inbox_name, sender_name, identity)
		if event:
			events.append(event)
	return events


def _normalise_message(
	message: dict, inbox_name: str, sender_name: str, identity: dict | None = None
) -> NormalizedEvent | None:
	"""Map one Meta message object → NormalizedEvent.

	Args:
		message: one Meta `messages[]` item (or echo / history message).
		inbox_name: Inbox the event belongs to.
		sender_name: display name for the sender ("" for business-side rows).
		identity: precomputed extract_whatsapp_identity() result; derived
			from the message alone when None.

	Returns:
		The event, or None when the message is not a chat bubble or carries
		no id / no customer identifier (the latter is logged as a warning).
		`platform_handle` is the phone when present, else the BSUID.
	"""
	meta_type = message.get("type") or ""
	identity = identity or extract_whatsapp_identity(message)
	from_phone = identity["phone"]
	handle_key = from_phone or identity["bsuid"]
	msg_id = message.get("id") or ""
	if not (handle_key and msg_id):
		if msg_id:
			logger.warning("WhatsApp message %s has neither phone nor user id; skipped", msg_id)
		return None

	ctx = message.get("context") or {}
	reply_to = ctx.get("id") if ctx and "forwarded" not in ctx else ""

	text_content, attachments, interactive_payload, source = "", [], {}, SourceType.ORGANIC

	referral = ad_referral.extract(ChannelType.WHATSAPP, message.get("referral"))
	if not referral:
		pending = None
		if from_phone:
			pending = ad_referral.get_pending(ChannelType.WHATSAPP, from_phone)
		if not pending and identity.get("bsuid"):
			pending = ad_referral.get_pending(ChannelType.WHATSAPP, identity["bsuid"])
		if pending:
			referral = dict(pending)
			referral["from_pending"] = True
	if referral:
		source = SourceType.CLICK_TO_WA

	if meta_type == "system":
		# Meta system messages (e.g. user_changed_user_id) are administrative
		# lifecycle events. Their state changes are handled during webhook ingest
		# and must not produce a blank/Unknown chat bubble.
		return None

	if meta_type == "text":
		text_content = (message.get("text") or {}).get("body", "")

	elif meta_type == "reaction":
		reaction = message.get("reaction") or {}
		text_content = reaction.get("emoji", "")
		reply_to = reaction.get("message_id", reply_to)

	elif meta_type == "interactive":
		interactive_payload = message.get("interactive") or {}
		if interactive_payload.get("type") == "call_permission_reply":
			# Handled by _route_call_permission_replies — not a chat message bubble.
			return None
		text_content = _interactive_summary(interactive_payload)
		if not text_content and not interactive_payload.get("button_reply") and not interactive_payload.get("list_reply") and not interactive_payload.get("nfm_reply"):
			return None

	elif meta_type == "button":
		button = message.get("button") or {}
		text_content = button.get("text", "")
		interactive_payload = {"button": button}

	elif meta_type == "order":
		order = message.get("order") or {}
		text_content = "Order received"
		interactive_payload = {"order": order}

	elif meta_type == "location":
		location = message.get("location") or {}
		text_content = f"Location: {location.get('latitude')}, {location.get('longitude')}"
		interactive_payload = {"location": location}

	elif meta_type == "contacts":
		contacts_list = message.get("contacts") or []
		summary_parts = []
		for c in contacts_list:
			c_name = (c.get("name") or {}).get("formatted_name") or ""
			c_phones = ", ".join(p.get("phone") or p.get("wa_id") or "" for p in c.get("phones") or [])
			if c_name and c_phones:
				summary_parts.append(f"{c_name} ({c_phones})")
			elif c_phones:
				summary_parts.append(c_phones)
		text_content = f"Contacts: {'; '.join(summary_parts)}" if summary_parts else "Contacts received"
		interactive_payload = {"contacts": contacts_list}

	elif meta_type in MEDIA_SEND_KINDS:
		media = message.get(meta_type) or {}
		text_content = media.get("caption", "") or ""
		attachments = [
			NormalizedAttachment(
				media_type=meta_type.capitalize(),
				file_url="",  # Resolved by the channel post-parse, see resolve_media.
				file_name=media.get("filename", ""),
				mime_type=media.get("mime_type", ""),
				caption=text_content,
				metadata={
					"media_id": media.get("id", ""),
					"sha256": media.get("sha256", ""),
					# Webhook `url` is rolling out gradually (Nov 2025+); may be absent.
					"media_url": media.get("url", "") or "",
				},
			)
		]

	return NormalizedEvent(
		channel_type=ChannelType.WHATSAPP,
		inbox=inbox_name,
		platform_handle=handle_key,
		display_name=sender_name,
		direction=Direction.INBOUND,
		content_type=whatsapp_content_type(meta_type),
		text_content=text_content,
		platform_message_id=msg_id,
		reply_to_platform_id=reply_to or "",
		platform_timestamp=parse_unix_timestamp(message.get("timestamp")),
		sender_type=SenderType.CUSTOMER,
		sender_name=sender_name,
		sender_phone=from_phone,
		bsuid=identity["bsuid"],
		parent_bsuid=identity["parent_bsuid"],
		username=identity["username"],
		attachments=attachments,
		interactive_payload=interactive_payload or {},
		source=source,
		ad_referral=referral,
		raw_payload=message,
	)


# ── Coexistence (WhatsApp Business app dual-use) parsing ─────────────────
# Meta's history-sync `history_context.status` vocabulary → our
# MessageStatus. PENDING keeps "queued"; ERROR maps to failed; PLAYED
# (voice notes) is as-read-as-it-gets.
_HISTORY_STATUS_TO_MESSAGE_STATUS = {
	"SENT": MessageStatus.SENT,
	"DELIVERED": MessageStatus.DELIVERED,
	"READ": MessageStatus.READ,
	"PLAYED": MessageStatus.READ,
	"PENDING": MessageStatus.QUEUED,
	"ERROR": MessageStatus.FAILED,
}


def _digits(phone: str) -> str:
	return "".join(c for c in (phone or "") if c.isdigit())


def _as_business_authored(
	event: NormalizedEvent, customer_phone: str, status: str, customer_bsuid: str = ""
) -> NormalizedEvent:
	"""Rewrite a parsed message event as business-authored (outbound).

	`_normalise_message` assumes `from` is the customer; for echoes and
	business-sent history messages `from` is OUR number, so the identity
	fields must be re-pointed at the customer or the dispatcher would
	create a Channel Handle / Conversation for the business's own number
	(and `_upsert_conversation` would overwrite customer_phone with it).

	Args:
		event: event to mutate in place.
		customer_phone: the customer's phone ("" when only a BSUID is known).
		status: Meta history status string (SENT/DELIVERED/...).
		customer_bsuid: the customer's BSUID, if known.

	Returns:
		The same event; platform_handle is the phone, else the BSUID.
	"""
	event.platform_handle = customer_phone or customer_bsuid
	event.bsuid = customer_bsuid
	event.parent_bsuid = ""
	event.username = ""
	event.direction = Direction.OUTBOUND
	event.sender_type = SenderType.AGENT
	event.sender_name = "WhatsApp Business App"
	event.sender_phone = ""
	event.display_name = ""
	event.initial_status = _HISTORY_STATUS_TO_MESSAGE_STATUS.get((status or "").upper(), MessageStatus.SENT)
	return event


def parse_smb_echoes(value: dict, inbox_name: str) -> list[NormalizedEvent]:
	"""Coexistence `smb_message_echoes` webhook → outbound mirror events.

	Fired when the business sends a message from the WhatsApp Business
	app (or a linked companion device) on a dual-use number. Mirroring it
	as an outbound Channel Message keeps the inbox thread complete —
	otherwise agents would see only the customer's half of app-side
	exchanges. Dedup is the dispatcher's normal platform_message_id
	check, so a message sent *through* MSuite never doubles up (echoes
	only fire for app-side sends, but belt-and-braces).

	The customer is `to`, or `to_user_id` (BSUID) when the phone is
	withheld; an echo with neither is logged and skipped."""
	events: list[NormalizedEvent] = []
	for echo in value.get("message_echoes") or []:
		customer = extract_whatsapp_identity(
			echo, phone_key="to", user_id_key="to_user_id", parent_key="to_parent_user_id"
		)
		if not (customer["phone"] or customer["bsuid"]):
			logger.warning("WhatsApp echo %s has neither phone nor user id; skipped", echo.get("id") or "")
			continue
		event = _normalise_message(echo, inbox_name, sender_name="")
		if not event:
			continue
		events.append(_as_business_authored(event, customer["phone"], "SENT", customer["bsuid"]))
	return events


def parse_history(value: dict, inbox_name: str) -> tuple[list[NormalizedEvent], dict]:
	"""Coexistence `history` webhook → import events + chunk metadata.

	One-time import of up to 180 days of 1:1 chats from the WhatsApp
	Business app, delivered in chunks (phases 0/1/2, `chunk_order`,
	`progress` 0-100). Shape (defensively parsed — Meta nests the thread
	list under `value.history[]` with its own `metadata`):

	    value.history[].metadata: {phase, chunk_order, progress}
	    value.history[].threads[]: {id: <customer phone or BSUID>, messages: [...]}

	Direction: a message whose `from` is our business number is
	business-authored; everything else in the thread came from the
	customer. Every event is flagged `suppress_side_effects` — see
	NormalizedEvent — so importing six months of chats can't trigger
	auto-replies or a lead-creation storm.

	Returns (events, chunk_metadata) — the caller uses metadata.progress
	to advance `WhatsApp Account.coexistence_history_sync`.
	"""
	business_digits = _digits((value.get("metadata") or {}).get("display_phone_number") or "")
	containers = value.get("history")
	if not isinstance(containers, list):
		containers = [value]  # tolerate a flattened shape

	events: list[NormalizedEvent] = []
	chunk_meta: dict = {}
	for container in containers:
		meta = container.get("metadata") or {}
		if "phase" in meta or "progress" in meta:
			chunk_meta = meta
		for thread in container.get("threads") or []:
			thread_id = thread.get("id") or ""
			if not thread_id:
				continue
			# A thread id is the customer's phone, or their BSUID when the
			# phone is withheld (WhatsApp username users).
			thread_bsuid = _clean_bsuid(thread_id)
			customer_phone = "" if thread_bsuid else thread_id
			customer_digits = _digits(customer_phone)
			for msg in thread.get("messages") or []:
				event = _normalise_message(msg, inbox_name, sender_name="")
				if not event:
					continue
				if msg.get("type") == "media_placeholder" and not event.text_content:
					# Media older than 14 days is not synced by Meta —
					# only a placeholder arrives.
					event.text_content = "[Media from WhatsApp Business app — not synced]"
				status = (msg.get("history_context") or {}).get("status") or ""
				from_digits = _digits(msg.get("from") or "")
				if thread_bsuid:
					# Customer rows carry the thread BSUID in from_user_id;
					# a phone-bearing row without it is the business.
					is_business = bool(
						(business_digits and from_digits == business_digits)
						or (from_digits and (msg.get("from_user_id") or "") != thread_bsuid)
					)
				else:
					is_business = bool(
						(business_digits and from_digits == business_digits)
						or (from_digits and customer_digits and from_digits != customer_digits)
					)
				if is_business:
					_as_business_authored(event, customer_phone, status, thread_bsuid or "")
				else:
					event.platform_handle = thread_id
					if thread_bsuid:
						event.bsuid = thread_bsuid
					event.initial_status = MessageStatus.RECEIVED
				event.suppress_side_effects = True
				events.append(event)
	return events, chunk_meta


def _interactive_summary(payload: dict) -> str:
	"""Pull a human-readable line out of an interactive reply for excerpting."""
	if not payload:
		return ""
	kind = payload.get("type")
	if kind == "button_reply":
		return (
			(payload.get("button_reply") or {}).get("title")
			or (payload.get("button_reply") or {}).get("id")
			or ""
		)
	if kind == "list_reply":
		return (
			(payload.get("list_reply") or {}).get("title")
			or (payload.get("list_reply") or {}).get("id")
			or ""
		)
	if kind == "nfm_reply":
		return "Flow response"
	return ""


# ── Media resolution ─────────────────────────────────────────────────────


def resolve_media_for_message(channel_message_name: str) -> None:
	"""Background-job entrypoint — downloads every unresolved attachment
	on an already-persisted Channel Message.

	Queued (not called inline) by `api/v1/webhook.py` right after
	`dispatch()` persists the message, per INBOX_ARCHITECTURE_AUDIT.md
	§9 (Critical): resolving media synchronously on the webhook path
	means every inbound image/video holds Meta's webhook ack open for a
	Graph API round-trip + file download — under load that's exactly
	the kind of slow handler that causes Meta to back off / retry-storm
	the whole webhook.

	Meta's signed media URLs are short-lived (~5 min TTL), so we:
	  1. Call Meta `/{media_id}/` to resolve the signed URL.
	  2. Download the bytes (auth-required HTTP GET) via the same token.
	  3. Save them as a private File row.
	  4. Rewrite the attachment row's `file_url` to the durable Frappe
	     File path (`/private/files/...`).

	Best-effort: any step that fails leaves the attachment without a
	file_url; `metadata.media_id` is retained either way for manual
	re-download. The conversation thread was already persisted by
	`dispatch()` before this job ever ran, so a failure here never loses
	the message — only the inline preview.
	"""
	doc = frappe.get_doc("Channel Message", channel_message_name)
	if not doc.attachments:
		return
	account = doc.whatsapp_account or get_whatsapp_account(account_type="incoming")
	if not account:
		return

	changed = False
	for row in doc.attachments:
		if row.file_url:
			continue

		metadata = row.metadata
		if isinstance(metadata, str):
			try:
				import json

				metadata = json.loads(metadata)
			except Exception:
				metadata = {}

		media_id = (metadata or {}).get("media_id")
		if not media_id:
			continue

		meta = fetch_media_url(account, media_id) or {}
		# Prefer the freshly resolved URL; fall back to the one the webhook carried.
		signed_url = meta.get("url") or (metadata or {}).get("media_url") or ""
		mime_type = meta.get("mime_type") or row.mime_type or ""
		if not signed_url:
			continue

		binary = download_media(signed_url, account)
		if not binary:
			# Meta returned the URL but the download failed (token expired
			# between fetch + download, network blip). Leave file_url empty;
			# metadata still carries media_id for retry.
			continue

		file_doc = _save_media_as_file(
			binary=binary,
			media_id=media_id,
			mime_type=mime_type,
			attachment=row,
		)
		if not file_doc:
			continue
		row.file_url = file_doc.file_url
		row.mime_type = mime_type
		row_metadata = dict(metadata or {})
		row_metadata.setdefault("file_doctype", "File")
		row_metadata.setdefault("file_name", file_doc.name)
		row.metadata = row_metadata
		changed = True

	if changed:
		doc.save(ignore_permissions=True)


# Mapping of mime → reasonable extension. Frappe is fine without one but
# downloads / browsers prefer a real extension for the right preview.
_MIME_EXTENSIONS = {
	"image/jpeg": "jpg",
	"image/png": "png",
	"image/webp": "webp",
	"image/gif": "gif",
	"video/mp4": "mp4",
	"video/3gpp": "3gp",
	"audio/ogg": "ogg",
	"audio/mpeg": "mp3",
	"audio/mp4": "m4a",
	"audio/amr": "amr",
	"application/pdf": "pdf",
}


def _save_media_as_file(
	*, binary: bytes, media_id: str, mime_type: str, attachment
) -> "frappe.Document | None":
	"""Persist downloaded bytes as a Frappe File. Private by default so the
	attachment respects Inbox permissions just like a desk upload would.
	"""
	try:
		ext = _MIME_EXTENSIONS.get((mime_type or "").lower(), "bin")
		original = attachment.file_name or ""
		# Use the customer's filename if Meta gave us one; otherwise build
		# a stable name from the media_id so re-runs collapse onto the same
		# File row.
		file_name = original if original else f"wa-{media_id}.{ext}"

		file_doc = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": file_name,
				"is_private": 1,
				"content": binary,
				"decode": False,
			}
		)
		file_doc.insert(ignore_permissions=True)
		return file_doc
	except Exception:
		logger.exception("Failed to save WhatsApp media to File for media_id=%s", media_id)
		return None


# ── Outbound send ────────────────────────────────────────────────────────


def _is_own_host(hostname: str | None) -> bool:
	"""True for a relative URL or one on this site's own host (site URL or the current request's host).

	What:
		Determines whether a media URL hostname is local to the current Frappe site
		(either matching site URL or the incoming HTTP request host).

	Params:
		hostname (str | None): Host part of the media link, or None for a relative link.

	Returns:
		bool: True if hostname is None/empty or matches current site / request host.

	Raises:
		None.

	Side effects:
		Inspects frappe.utils.get_url() and frappe.local.request.
	"""
	if not hostname:
		return True
	own = {urlparse(frappe.utils.get_url()).hostname}
	request = getattr(frappe.local, "request", None)
	if request is not None:
		own.add(request.host.split(":")[0])
	return hostname in own


def _upload_local_media(body: dict, account) -> None:
	"""Swap a media `link` for a Meta media `id` when the file lives on this site.

	What:
		Uploads site-hosted media files (/files/ and /private/files/) to Meta's media
		upload API and replaces the 'link' parameter with 'id' in the outbound body.
		Verifies file existence, path traversal safety, and read permissions on private files.

	Params:
		body (dict): Outbound Meta Cloud API payload; mutated in place.
		account: WhatsApp Account document or doc-like object with .name.

	Returns:
		None.

	Raises:
		frappe.PermissionError: If caller lacks read permission for a private file.
		frappe.ValidationError: If media upload to Meta fails.

	Side effects:
		Uploads file to Meta media API (skipped on cache hit) and mutates body dict.
	"""
	if not isinstance(body, dict):
		return
	kind = body.get("type")
	media = body.get(kind) if kind in MEDIA_SEND_KINDS else None
	if not isinstance(media, dict):
		return
	link = media.get("link")
	if not link:
		return
	parts = urlparse(link)
	# normpath collapses "/files/../x" so a traversal cannot escape the files folders.
	path = posixpath.normpath(unquote(parts.path))
	if not is_local_file_url(path) or not _is_own_host(parts.hostname):
		return
	if not os.path.exists(resolve_frappe_path(path)):
		return
	# Uploading sends the file to Meta, so private files need File read permission (no silent exfiltration).
	if path.startswith(LOCAL_PRIVATE_FILE_PATH_PREFIX):
		file_name = frappe.db.get_value("File", {"file_url": path}, "name")
		if not (file_name and frappe.has_permission("File", "read", doc=file_name)):
			frappe.throw(_("You do not have permission to send this file"), frappe.PermissionError)
	from msuite_whatsapp.integrations.meta.media_provider import upload_media

	media["id"] = upload_media(path, account.name)
	del media["link"]


def send(conversation_doc, payload: dict) -> None:
	"""Send a message defined by `payload` to the conversation's customer.

	Payload shapes (built by the response engine / agent API):
	  {"type": "text", "text": "..."}
	  {"type": "template", "template": "tpl_name", "language": "en", "components": [...]}
	  {"type": "interactive", "text": "...", "buttons": [{"button_text", "payload"}]}
	  {"type": "request_contact_info", "text": "..."}

	The response is dispatched via the inbox dispatcher as an outbound
	Channel Message so the conversation thread stays canonical.
	"""
	if not conversation_doc.channel_handle:
		return
	handle_doc = frappe.get_doc("Channel Handle", conversation_doc.channel_handle)
	_, target_val = _resolve_target(handle_doc)
	# Precedence: when a phone is known, phone in 'to' wins
	conv_phone = customer_phone(getattr(conversation_doc, "customer_phone", None))
	if conv_phone:
		target_val = conv_phone
	payload_phone = customer_phone(payload.get("customer_phone") or payload.get("to"))
	if payload_phone:
		target_val = payload_phone

	from msuite_inbox.inbox.services.dispatcher import is_handle_opted_out
	if is_handle_opted_out(handle_doc):
		return {"ok": False, "error": "Recipient has opted out"}

	if not target_val:
		return

	inbox = frappe.get_doc("Inbox", conversation_doc.inbox)
	# An explicit account on the payload wins (agent-initiated conversation
	# via "New Conversation" dialog). Next, conversation history takes
	# precedence so replies are always dispatched from the same number the contact
	# texted, preserving Meta's 24-hour customer service window.
	whatsapp_account_name = payload.get("whatsapp_account")
	if not whatsapp_account_name:
		# Resolve originating WhatsApp Account from conversation message history
		whatsapp_account_name = frappe.db.get_value(
			"Channel Message",
			{"conversation": conversation_doc.name, "direction": Direction.INBOUND},
			"whatsapp_account",
			order_by="creation desc, platform_timestamp desc",
		)
	if not whatsapp_account_name:
		for ch in getattr(inbox, "channels", []) or []:
			if getattr(ch, "channel_type", None) == ChannelType.WHATSAPP and getattr(ch, "whatsapp_account", None):
				whatsapp_account_name = ch.whatsapp_account
				break
	if not whatsapp_account_name:
		whatsapp_account_name = getattr(inbox, "whatsapp_account", None)

	account = (
		frappe.get_doc("WhatsApp Account", whatsapp_account_name)
		if whatsapp_account_name
		else get_whatsapp_account(account_type="outgoing")
	)
	if not account:
		logger.warning("No WhatsApp Account configured for inbox %s", inbox.name)
		return

	# Catalog sends resolve their catalog through this account (product / carousel bodies).
	payload = {**payload, "whatsapp_account": account.name}
	body = _build_send_body(target_val, payload)
	if not body:
		return
	# Reply-to threading. Meta accepts `context: {message_id}` on every
	# send shape (text, media, interactive, template) except reaction —
	# reaction already carries its parent via `reaction.message_id`.
	reply_to_pid = payload.get("reply_to_platform_id")
	if reply_to_pid and body.get("type") != "reaction":
		body["context"] = {"message_id": reply_to_pid}

	# Step 1: Write-ahead logging - insert Channel Message with initial status Queued
	tracking_id = f"outbound-{frappe.generate_hash(length=12)}"
	rec_result = _record_outbound(
		conversation_doc=conversation_doc,
		handle_doc=handle_doc,
		payload=payload,
		platform_message_id=tracking_id,
		ok=True,
		error=None,
		whatsapp_account=account.name if account else None,
		initial_status=MessageStatus.QUEUED,
	)
	msg_name = rec_result.get("message")
	if not msg_name:
		logger.warning(
			"Failed to write-ahead outbound Channel Message for %s: %s",
			conversation_doc.name,
			rec_result.get("error"),
		)
		return rec_result

	# Step 2: External HTTP POST to Meta Graph API
	# The HTTP layer is shared with the rest of the WhatsApp product —
	# any change to retries, timeouts, or error normalisation happens in
	# one place: `whatsapp.utils.send.send_to_meta`.
	retry = None
	send_path = ""
	try:
		_upload_local_media(body, account)
		resp_data, send_path = send_to_meta(account, body, phone_number_id=payload.get("phone_number_id"))
		platform_message_id = ((resp_data.get("messages") or [{}])[0] or {}).get("id", "")
		ok, error = True, None
	except Exception as e:
		logger.warning("WhatsApp send failed for conversation %s: %s", conversation_doc.name, e)
		platform_message_id, ok, error, send_path = "", False, str(e)[:500], ""
		is_bsuid_unsupported = False
		if hasattr(e, "response_json") and isinstance(e.response_json, dict):
			err_dict = e.response_json.get("error") or {}
			if cint(err_dict.get("code")) == META_ERROR_BSUID_UNSUPPORTED:
				is_bsuid_unsupported = True
		if not is_bsuid_unsupported and str(META_ERROR_BSUID_UNSUPPORTED) in str(e):
			is_bsuid_unsupported = True

		if is_bsuid_unsupported:
			# Meta Error 131062: Business-scoped User ID (BSUID) recipients are not
			# supported for this message. Terminal failure - no retry loops.
			retry = None
			error = META_ERROR_BSUID_UNSUPPORTED_MSG
		else:
			retry = retry_kind(e)

	# Step 3: Latch final sent/failed status and Meta wamid
	try:
		msg = frappe.get_doc("Channel Message", msg_name)
		msg.status = MessageStatus.SENT if ok else MessageStatus.FAILED
		msg.status_error = error or ""
		if not ok and hasattr(msg, "failure_reason"):
			msg.failure_reason = error or ""
		if platform_message_id:
			msg.platform_message_id = platform_message_id
			msg.secondary_platform_message_id = tracking_id
		if ok and send_path:
			msg.send_path = send_path  # route actually used; blank (unknown) on failed sends
		msg.save(ignore_permissions=True)
	except Exception as e:
		logger.exception("Failed to update Channel Message %s after Meta send: %s", msg_name, e)

	return {"message": msg_name, "ok": ok, "error": error, "retry": retry}


def _resolve_target(target: Any) -> tuple[str, str]:
	"""Resolve a send target into (field_name, value).

	Returns ("to", phone) if a phone is known (or target is a phone string).
	Returns ("recipient", bsuid) if the target is BSUID-only.
	Returns ("", "") if target cannot be resolved.
	"""
	if not target:
		return "", ""
	if isinstance(target, str):
		target_clean = target.strip()
		if is_bsuid(target_clean):
			return META_RECIPIENT_FIELD_BSUID, target_clean
		return META_RECIPIENT_FIELD_PHONE, target_clean

	phone = getattr(target, "phone", None) or customer_phone(getattr(target, "platform_handle", None))
	if phone:
		return META_RECIPIENT_FIELD_PHONE, str(phone).strip()

	bsuid = getattr(target, "bsuid", None)
	if not bsuid and is_bsuid(getattr(target, "platform_handle", None)):
		bsuid = target.platform_handle
	if bsuid:
		return META_RECIPIENT_FIELD_BSUID, str(bsuid).strip()

	return "", ""


def is_unsupported_bsuid_template(template_name: str | None, payload: dict | None = None) -> bool:
	"""Check if a template is an authentication/OTP template unsupported for BSUID recipients.

	Meta WhatsApp documentation:
	"BSUID recipients cannot receive authentication templates that use one-tap,
	zero-tap, or copy-code buttons."
	"""
	if payload and payload.get("components"):
		for comp in payload["components"]:
			if comp.get("type") == "button":
				sub_type = (comp.get("sub_type") or "").upper()
				if sub_type in UNSUPPORTED_BSUID_OTP_BUTTON_TYPES or sub_type in UNSUPPORTED_BSUID_BUTTON_TYPES:
					return True

	if not template_name:
		return False

	template = None
	try:
		template = frappe.get_cached_doc("WhatsApp Templates", template_name)
	except Exception:
		pass

	if not template:
		real_name = frappe.db.get_value("WhatsApp Templates", {"template_name": template_name}, "name")
		if real_name:
			try:
				template = frappe.get_cached_doc("WhatsApp Templates", real_name)
			except Exception:
				pass

	if not template:
		return False

	cat = (getattr(template, "category", "") or "").upper()
	if cat in UNSUPPORTED_BSUID_TEMPLATE_CATEGORIES:
		return True

	ttype = (getattr(template, "template_type", "") or "").upper()
	if ttype in UNSUPPORTED_BSUID_TEMPLATE_TYPES:
		return True

	for btn in getattr(template, "buttons", []) or []:
		b_type = (getattr(btn, "button_type", "") or "").upper()
		otp_type = (getattr(btn, "otp_type", "") or "").upper()
		if (
			b_type in UNSUPPORTED_BSUID_BUTTON_TYPES
			or b_type in ("OTP",)
			or otp_type in UNSUPPORTED_BSUID_OTP_BUTTON_TYPES
		):
			return True

	return False


def _build_send_body(target: Any, payload: dict) -> dict | None:
	"""Build the Meta send body for a normalised outbound payload.

	For `type == "template"` the optional keys `limited_time_offer_expiry_ms`
	(int UNIX ms), `coupon_code` (str) and `tap_target` ({"url","title"}) are
	forwarded unchanged to `build_template_meta`, which validates them.
	No DB writes or network calls beyond reading the template/catalog.
	"""
	target_field, target_val = _resolve_target(target)
	if not target_val:
		return None

	kind = payload.get("type")
	if kind == "text":
		text = payload.get("text") or ""
		if not text:
			return None
		if target_field == META_RECIPIENT_FIELD_BSUID:
			return {
				"messaging_product": "whatsapp",
				"recipient_type": META_RECIPIENT_TYPE_INDIVIDUAL,
				"recipient": target_val,
				"type": "text",
				"text": {"body": text},
			}
		return {
			"messaging_product": "whatsapp",
			"to": target_val,
			"type": "text",
			"text": {"body": text},
		}

	if kind == "template":
		template_name = payload.get("template")
		if not template_name:
			return None

		if target_field == META_RECIPIENT_FIELD_BSUID and is_unsupported_bsuid_template(template_name, payload):
			frappe.throw(_(BSUID_AUTH_TEMPLATE_ERROR_MESSAGE), frappe.ValidationError)

		from msuite_whatsapp.utils.template_send import build_template_meta

		catalog_id = None
		if payload.get("catalog"):
			catalog_id = frappe.db.get_value("Meta Product Catalog", payload["catalog"], "catalog_id")

		product = None
		if payload.get("product_retailer_id") and catalog_id:
			product = {"product_retailer_id": payload["product_retailer_id"], "catalog_id": catalog_id}

		carousel_products = None
		if payload.get("product_retailer_ids") and catalog_id:
			carousel_products = [
				{"product_retailer_id": rid, "catalog_id": catalog_id}
				for rid in payload["product_retailer_ids"]
			]

		meta_template = build_template_meta(
			template_name=template_name,
			body_param=payload.get("body_param"),
			attach=payload.get("attach"),
			product_catalog_json=payload.get("product_catalog_json"),
			product=product,
			carousel_products=carousel_products,
			reference_doctype=payload.get("reference_doctype"),
			reference_name=payload.get("reference_name"),
			whatsapp_account=payload.get("whatsapp_account"),
			thumbnail_product_retailer_id=payload.get("thumbnail_product_retailer_id"),
			# Offer extras: validated by build_template_meta, never here.
			limited_time_offer_expiry_ms=payload.get("limited_time_offer_expiry_ms"),
			coupon_code=payload.get("coupon_code"),
			tap_target=payload.get("tap_target"),
		)
		meta_template.pop("_resolved_parameters", None)
		if payload.get("components"):
			meta_template["components"] = payload["components"]

		if target_field == META_RECIPIENT_FIELD_BSUID:
			return {
				"messaging_product": "whatsapp",
				"recipient_type": META_RECIPIENT_TYPE_INDIVIDUAL,
				"recipient": target_val,
				"type": "template",
				"template": meta_template,
			}
		return {
			"messaging_product": "whatsapp",
			"to": target_val,
			"type": "template",
			"template": meta_template,
		}

	if kind in ("request_contact_info",) or (
		kind == "interactive"
		and str(payload.get("interactive_type") or "").strip().lower()
		in (META_INTERACTIVE_TYPE_REQUEST_CONTACT_INFO.lower(), META_BUTTON_TYPE_REQUEST_CONTACT_INFO.lower())
	):
		interactive = {
			"type": META_INTERACTIVE_TYPE_REQUEST_CONTACT_INFO,
			"body": {"text": payload.get("text") or DEFAULT_REQUEST_CONTACT_INFO_BODY},
			"action": {"name": META_INTERACTIVE_TYPE_REQUEST_CONTACT_INFO},
		}
		if target_field == META_RECIPIENT_FIELD_BSUID:
			return {
				"messaging_product": "whatsapp",
				"recipient_type": META_RECIPIENT_TYPE_INDIVIDUAL,
				"recipient": target_val,
				"type": "interactive",
				"interactive": interactive,
			}
		return {
			"messaging_product": "whatsapp",
			"to": target_val,
			"type": "interactive",
			"interactive": interactive,
		}

	if kind == "interactive":
		buttons = payload.get("buttons") or []
		if not buttons:
			return None
		btn_type = str(buttons[0].get("type") or "").strip().lower()
		btn_action = str(buttons[0].get("action") or "").strip().lower()
		contact_info_types = (
			META_INTERACTIVE_TYPE_REQUEST_CONTACT_INFO.lower(),
			META_BUTTON_TYPE_REQUEST_CONTACT_INFO.lower(),
		)
		if len(buttons) == 1 and (btn_type in contact_info_types or btn_action in contact_info_types):
			interactive = {
				"type": META_INTERACTIVE_TYPE_REQUEST_CONTACT_INFO,
				"body": {"text": payload.get("text") or DEFAULT_REQUEST_CONTACT_INFO_BODY},
				"action": {"name": META_INTERACTIVE_TYPE_REQUEST_CONTACT_INFO},
			}
			if target_field == META_RECIPIENT_FIELD_BSUID:
				return {
					"messaging_product": "whatsapp",
					"recipient_type": META_RECIPIENT_TYPE_INDIVIDUAL,
					"recipient": target_val,
					"type": "interactive",
					"interactive": interactive,
				}
			return {
				"messaging_product": "whatsapp",
				"to": target_val,
				"type": "interactive",
				"interactive": interactive,
			}

		button_list = [
			{
				"type": "reply",
				"reply": {
					"id": (btn.get("payload") or btn.get("button_text") or "")[:256],
					"title": (btn.get("button_text") or "")[:20],
				},
			}
			for btn in buttons[:3]
		]
		interactive = {
			"type": "button",
			"body": {"text": payload.get("text") or ""},
			"action": {"buttons": button_list},
		}
		if target_field == META_RECIPIENT_FIELD_BSUID:
			return {
				"messaging_product": "whatsapp",
				"recipient_type": META_RECIPIENT_TYPE_INDIVIDUAL,
				"recipient": target_val,
				"type": "interactive",
				"interactive": interactive,
			}
		return {
			"messaging_product": "whatsapp",
			"to": target_val,
			"type": "interactive",
			"interactive": interactive,
		}

	if kind in MEDIA_SEND_KINDS:
		return _build_media_body(target_val, kind, payload, target_field=target_field)
	if kind == "flow":
		return _build_flow_body(target_val, payload, target_field=target_field)
	if kind == "reaction":
		return _build_reaction_body(target_val, payload, target_field=target_field)
	if kind == "product":
		return _build_product_body(target_val, payload, target_field=target_field)
	if kind == "product_carousel":
		return _build_product_carousel_body(target_val, payload, target_field=target_field)
	if kind == "catalog":
		return _build_catalog_body(target_val, payload, target_field=target_field)
	return None


def _build_reaction_body(target: Any, payload: dict, target_field: str | None = None) -> dict | None:
	"""Meta's reaction send shape:
	    {messaging_product, to/recipient, type:"reaction",
	     reaction: {message_id, emoji}}
	Empty `emoji` removes a previously-sent reaction (Meta semantics)."""
	parent_pid = payload.get("reply_to_platform_id")
	if not parent_pid:
		return None

	if target_field is None:
		target_field, target_val = _resolve_target(target)
	else:
		target_val = target

	if target_field == META_RECIPIENT_FIELD_BSUID:
		return {
			"messaging_product": "whatsapp",
			"recipient_type": META_RECIPIENT_TYPE_INDIVIDUAL,
			"recipient": target_val,
			"type": "reaction",
			"reaction": {
				"message_id": parent_pid,
				"emoji": payload.get("emoji") or "",
			},
		}
	return {
		"messaging_product": "whatsapp",
		"to": target_val,
		"type": "reaction",
		"reaction": {
			"message_id": parent_pid,
			"emoji": payload.get("emoji") or "",
		},
	}


def _resolve_meta_catalog_id(
	catalog_param: str | None = None, whatsapp_account: str | None = None
) -> str:
	param_str = str(catalog_param).strip() if catalog_param else None

	if param_str:
		filters_name = {"name": param_str}
		filters_cid = {"catalog_id": param_str}
		if whatsapp_account:
			filters_name["whatsapp_account"] = whatsapp_account
			filters_cid["whatsapp_account"] = whatsapp_account

		cid = frappe.db.get_value("Meta Product Catalog", filters_name, "catalog_id")
		if cid:
			return str(cid)

		cid = frappe.db.get_value("Meta Product Catalog", filters_cid, "catalog_id")
		if cid:
			return str(cid)

	elif whatsapp_account:
		cid = frappe.db.get_value(
			"Meta Product Catalog", {"whatsapp_account": whatsapp_account}, "catalog_id"
		)
		if cid:
			return str(cid)

	frappe.throw(_("No catalog linked to this WhatsApp number"), frappe.ValidationError)


def _build_product_body(target: Any, payload: dict, target_field: str | None = None) -> dict | None:
	"""Single Product Message — free-form interactive product card. `payload`
	carries `catalog` (a Meta Product Catalog doc name or catalog_id) and
	`product_retailer_id` (an Item's item_code, once synced to that catalog)."""
	from msuite_whatsapp.integrations.meta import message_provider

	retailer_id = payload.get("product_retailer_id")
	catalog_id = _resolve_meta_catalog_id(
		payload.get("catalog"), whatsapp_account=payload.get("whatsapp_account")
	)
	if not retailer_id or not catalog_id:
		return None

	if target_field is None:
		target_field, target_val = _resolve_target(target)
	else:
		target_val = target

	interactive = message_provider.build_product_message(
		catalog_id=str(catalog_id),
		retailer_id=str(retailer_id),
		body_text=payload.get("text"),
		footer_text=payload.get("footer"),
	)
	if target_field == META_RECIPIENT_FIELD_BSUID:
		return {
			"messaging_product": "whatsapp",
			"recipient_type": META_RECIPIENT_TYPE_INDIVIDUAL,
			"recipient": target_val,
			"type": "interactive",
			"interactive": interactive,
		}
	return {
		"messaging_product": "whatsapp",
		"recipient_type": "individual",
		"to": target_val,
		"type": "interactive",
		"interactive": interactive,
	}


def _build_product_carousel_body(target: Any, payload: dict, target_field: str | None = None) -> dict | None:
	"""Interactive Product Carousel — 2-10 product cards, free-form (no
	template). `payload` carries `catalog` (Meta Product Catalog doc name or catalog_id),
	`text` (required body), and `product_retailer_ids` (list of item_codes)."""
	from msuite_whatsapp.integrations.meta import message_provider

	retailer_ids = payload.get("product_retailer_ids") or []
	catalog_id = _resolve_meta_catalog_id(
		payload.get("catalog"), whatsapp_account=payload.get("whatsapp_account")
	)

	if not retailer_ids or not catalog_id:
		return None

	if target_field is None:
		target_field, target_val = _resolve_target(target)
	else:
		target_val = target

	interactive = message_provider.build_product_carousel_message(
		catalog_id=str(catalog_id),
		body_text=payload.get("text") or "",
		retailer_ids=retailer_ids,
	)
	if target_field == META_RECIPIENT_FIELD_BSUID:
		return {
			"messaging_product": "whatsapp",
			"recipient_type": META_RECIPIENT_TYPE_INDIVIDUAL,
			"recipient": target_val,
			"type": "interactive",
			"interactive": interactive,
		}
	return {
		"messaging_product": "whatsapp",
		"recipient_type": "individual",
		"to": target_val,
		"type": "interactive",
		"interactive": interactive,
	}


def _build_catalog_body(target: Any, payload: dict, target_field: str | None = None) -> dict | None:
	"""Catalog message — an `interactive` message that shows a product thumbnail
	header, body text, a fixed "View catalog" button, and opens the connected
	catalog in WhatsApp when tapped. See: catalog-messages.

	`text` is the required body (Meta caps it at 1024 chars). `footer` is
	optional (≤60 chars). `thumbnail_product_retailer_id` is optional — omit it
	and WhatsApp uses the first catalog item's image as the header."""
	body_text = (payload.get("text") or "").strip() or "Browse our catalog and add items to your order."
	if len(body_text) > WHATSAPP_INTERACTIVE_BODY_MAX:
		frappe.throw(f"Catalog message body cannot exceed {WHATSAPP_INTERACTIVE_BODY_MAX} characters.")

	action: dict = {"name": "catalog_message"}
	thumb = payload.get("thumbnail_product_retailer_id")
	if thumb:
		action["parameters"] = {"thumbnail_product_retailer_id": thumb}

	interactive = {
		"type": "catalog_message",
		"body": {"text": body_text},
		"action": action,
	}
	footer = (payload.get("footer") or "").strip()
	if footer:
		if len(footer) > 60:
			frappe.throw("Catalog message footer cannot exceed 60 characters.")
		interactive["footer"] = {"text": footer}

	if target_field is None:
		target_field, target_val = _resolve_target(target)
	else:
		target_val = target

	if target_field == META_RECIPIENT_FIELD_BSUID:
		return {
			"messaging_product": "whatsapp",
			"recipient_type": META_RECIPIENT_TYPE_INDIVIDUAL,
			"recipient": target_val,
			"type": "interactive",
			"interactive": interactive,
		}
	return {
		"messaging_product": "whatsapp",
		"recipient_type": "individual",
		"to": target_val,
		"type": "interactive",
		"interactive": interactive,
	}


def _build_flow_body(target: Any, payload: dict, target_field: str | None = None) -> dict | None:
	"""Build an interactive `flow` message body.

	Pulls flow metadata from the linked `WhatsApp Flow` doc so callers
	only need to pass `flow=<doc name>` plus optional `text`,
	`flow_cta`, `flow_screen`, `flow_token`."""
	flow_name = payload.get("flow")
	if not flow_name:
		return None
	flow_doc = frappe.get_doc("WhatsApp Flow", flow_name)
	if not flow_doc.flow_id:
		frappe.throw(f"WhatsApp Flow {flow_name!r} has no flow_id — create it on Meta first")

	if target_field is None:
		target_field, target_val = _resolve_target(target)
	else:
		target_val = target

	flow_screen = payload.get("flow_screen") or (flow_doc.screens[0].screen_id if flow_doc.screens else "")
	flow_token = payload.get("flow_token") or frappe.generate_hash(length=16)
	parameters: dict[str, Any] = {
		"flow_message_version": "3",
		"flow_id": flow_doc.flow_id,
		"flow_cta": payload.get("flow_cta") or flow_doc.flow_cta or "Open",
		"flow_action": "navigate",
		"flow_action_payload": {"screen": flow_screen},
		"flow_token": flow_token,
	}
	if flow_doc.status != "Published":
		parameters["mode"] = "draft"

	try:
		from msuite_whatsapp.services.flows import flow_response_service

		flow_response_service.mark_sent(flow_doc, target_val, flow_token)
	except Exception as err:
		frappe.log_error(title="whatsapp channel: mark_sent flow failed", message=str(err))

	if target_field == META_RECIPIENT_FIELD_BSUID:
		return {
			"messaging_product": "whatsapp",
			"recipient_type": META_RECIPIENT_TYPE_INDIVIDUAL,
			"recipient": target_val,
			"type": "interactive",
			"interactive": {
				"type": "flow",
				"body": {"text": payload.get("text") or "Please fill out the form"},
				"action": {"name": "flow", "parameters": parameters},
			},
		}
	return {
		"messaging_product": "whatsapp",
		"to": target_val,
		"type": "interactive",
		"interactive": {
			"type": "flow",
			"body": {"text": payload.get("text") or "Please fill out the form"},
			"action": {"name": "flow", "parameters": parameters},
		},
	}


def _build_media_body(target: Any, kind: str, payload: dict, target_field: str | None = None) -> dict | None:
	"""Outbound WhatsApp media — supports either a hosted URL (`media_url`)
	or a pre-uploaded media id (`media_id`). Meta requires exactly one.

	Audio and sticker messages cannot carry a caption (Meta API constraint); for all
	other media we forward `caption` when provided. Documents also get a
	`filename` hint.
	"""
	if kind == "sticker" and (payload.get("mime_type") or STICKER_MIME) != STICKER_MIME:
		return None  # Meta only accepts WebP stickers.
	media: dict = {}
	if payload.get("media_id"):
		media["id"] = payload["media_id"]
	elif payload.get("media_url"):
		media["link"] = payload["media_url"]
	else:
		return None  # Nothing to send.

	if kind not in ("audio", "sticker") and payload.get("caption"):
		media["caption"] = payload["caption"]
	if kind == "document" and payload.get("file_name"):
		media["filename"] = payload["file_name"]

	if target_field is None:
		target_field, target_val = _resolve_target(target)
	else:
		target_val = target

	if target_field == META_RECIPIENT_FIELD_BSUID:
		return {
			"messaging_product": "whatsapp",
			"recipient_type": META_RECIPIENT_TYPE_INDIVIDUAL,
			"recipient": target_val,
			"type": kind,
			kind: media,
		}
	return {
		"messaging_product": "whatsapp",
		"to": target_val,
		"type": kind,
		kind: media,
	}


# ── Outbound persistence — split into per-kind shape builders ────────────
#
# Each builder receives the send payload and returns a normalised
# `(content_type, text, attachments, interactive_payload,
#   template_name)` tuple. The dispatch table below maps Meta's
# `payload["type"]` to its builder; adding a new outbound shape is a
# one-row change here plus a small function — no growing if/elif chain.


def _shape_text(payload):
	return (
		MessageContentType.TEXT,
		payload.get("text") or "",
		[],
		{},
		"",
	)


def _extract_body_param_from_components(components) -> dict | None:
	"""Extract template body parameter mapping from Meta components payload.

	Searches components for a 'body' component. When found, maps named parameters
	to their parameter_name and positional parameters to their 1-based string
	index ('1', '2', ...), matching the dictionary keys expected by
	_render_template_body.

	Params:
		components (list | str | None): List or JSON-encoded string of Meta
			template component dicts.

	Returns:
		dict | None: Mapping of parameter placeholder keys to parameter text
			values, or None if no body component is present.

	Raises:
		None.

	Side Effects:
		None.
	"""
	if not components:
		return None

	import json as _json

	comps = components
	if isinstance(comps, str):
		try:
			comps = _json.loads(comps)
		except (ValueError, TypeError):
			comps = None

	if not isinstance(comps, list):
		return None

	body_comp = None
	for comp in comps:
		if isinstance(comp, dict) and str(comp.get("type") or "").strip().lower() == "body":
			body_comp = comp
			break

	if not body_comp:
		return None

	raw_params = body_comp.get("parameters")
	if isinstance(raw_params, str):
		try:
			raw_params = _json.loads(raw_params)
		except (ValueError, TypeError):
			raw_params = []

	if not isinstance(raw_params, list):
		return None

	derived = {}
	for idx, param in enumerate(raw_params, start=1):
		if isinstance(param, dict):
			pname = param.get("parameter_name")
			key = str(pname).strip() if pname else str(idx)
			derived[key] = param.get("text")
		else:
			derived[str(idx)] = param
	return derived


def _shape_template(payload):
	"""Shape an outbound template payload into message row fields.

	When body_param is empty or missing and payload['components'] has a body
	component, derives parameter values from the components before rendering
	the template body so the conversation bubble shows actual sent text.

	Params:
		payload (dict): Outbound WhatsApp template message payload.

	Returns:
		tuple: (MessageContentType.TEMPLATE, text, attachments, interactive_payload, template_name)

	Raises:
		None.

	Side Effects:
		None.
	"""
	template_name = payload.get("template") or ""
	body_param = payload.get("body_param")

	is_empty_body = False
	if not body_param:
		is_empty_body = True
	elif isinstance(body_param, str):
		import json as _json

		try:
			parsed = _json.loads(body_param)
			if isinstance(parsed, dict) and not parsed:
				is_empty_body = True
		except (ValueError, TypeError):
			pass
	elif isinstance(body_param, dict) and not body_param:
		is_empty_body = True

	if is_empty_body and payload.get("components"):
		derived = _extract_body_param_from_components(payload.get("components"))
		if derived is not None:
			body_param = derived

	# Persist the rendered body (not "[Template] <name>") so the
	# conversation list excerpt + message bubble show what the customer
	# actually receives. The Meta send body is built separately by
	# `build_template_meta` and is unaffected.
	rendered = _render_template_body(template_name, body_param)
	return (
		MessageContentType.TEMPLATE,
		rendered or excerpt(f"[Template] {template_name}"),
		[],
		{},
		template_name,
	)


def _shape_interactive(payload):
	return (
		MessageContentType.INTERACTIVE,
		payload.get("text") or "",
		[],
		{"buttons": payload.get("buttons") or []},
		"",
	)


def _shape_flow(payload):
	return (
		MessageContentType.INTERACTIVE,
		excerpt(payload.get("text") or "[Flow]"),
		[],
		{
			"flow": payload.get("flow"),
			"flow_screen": payload.get("flow_screen"),
			"flow_cta": payload.get("flow_cta"),
		},
		"",
	)


def _shape_media(payload):
	"""One builder for image/video/audio/document — Meta treats them
	identically at the storage layer (single attachment, optional
	caption)."""
	kind = payload.get("type")
	caption = payload.get("caption") or ""
	attachment = NormalizedAttachment(
		media_type=kind.capitalize(),
		file_url=payload.get("media_url", ""),
		file_name=payload.get("file_name", ""),
		mime_type=payload.get("mime_type", ""),
		caption=caption,
		metadata={"media_id": payload.get("media_id", "")} if payload.get("media_id") else {},
	)
	return (
		_MEDIA_KIND_TO_CONTENT_TYPE[kind],
		caption,  # caption doubles as the preview
		[attachment],
		{},
		"",
	)


def _shape_reaction(payload):
	"""Reactions are first-class Channel Message rows. The emoji goes
	into `text_content` so the UI can show it as a chip on the parent
	bubble; the link to the parent travels via
	`reply_to_platform_id` (set by the caller)."""
	return (
		MessageContentType.REACTION,
		payload.get("emoji") or "",
		[],
		{},
		"",
	)


def _shape_product(payload):
	sku = payload.get("product_retailer_id")
	item_data = frappe.db.get_value("Item", sku, ["item_name", "image"], as_dict=True) if sku else {}
	return (
		MessageContentType.INTERACTIVE,
		payload.get("text") or excerpt(f"[Product] {sku}"),
		[],
		{
			"catalog": payload.get("catalog"),
			"product_retailer_id": sku,
			"item_name": item_data.get("item_name") if item_data else sku,
			"image": item_data.get("image") if item_data else "",
		},
		"",
	)


def _shape_product_carousel(payload):
	skus = payload.get("product_retailer_ids") or []
	items_meta = []
	for sku in skus:
		item_data = frappe.db.get_value("Item", sku, ["item_name", "image"], as_dict=True) if sku else {}
		items_meta.append(
			{
				"product_retailer_id": sku,
				"item_name": item_data.get("item_name") if item_data else sku,
				"image": item_data.get("image") if item_data else "",
			}
		)
	return (
		MessageContentType.INTERACTIVE,
		payload.get("text") or excerpt("[Product Carousel]"),
		[],
		{
			"catalog": payload.get("catalog"),
			"product_retailer_ids": skus,
			"products": items_meta,
		},
		"",
	)


def _shape_catalog(payload):
	return (
		MessageContentType.INTERACTIVE,
		payload.get("text") or excerpt("[Catalog message]"),
		[],
		{
			"is_catalog_message": True,
			"thumbnail_product_retailer_id": payload.get("thumbnail_product_retailer_id") or "",
			"footer": payload.get("footer") or "",
		},
		"",
	)


def _shape_request_contact_info(payload):
	return (
		MessageContentType.INTERACTIVE,
		payload.get("text") or "Request Contact Info",
		[],
		{"type": "request_contact_info", "action": "request_contact_info"},
		"",
	)


# Map payload `type` → shape builder. Centralised so adding a new
# outbound kind is one line + one function.
_OUTBOUND_SHAPE_BUILDERS = {
	"text": _shape_text,
	"template": _shape_template,
	"interactive": _shape_interactive,
	"request_contact_info": _shape_request_contact_info,
	"flow": _shape_flow,
	"reaction": _shape_reaction,
	"product": _shape_product,
	"product_carousel": _shape_product_carousel,
	"catalog": _shape_catalog,
	# Media kinds share one builder — Meta treats them identically.
	"image": _shape_media,
	"video": _shape_media,
	"audio": _shape_media,
	"document": _shape_media,
	"sticker": _shape_media,
}


def _record_outbound(
	conversation_doc,
	handle_doc,
	payload: dict,
	platform_message_id: str | None = None,
	ok: bool = True,
	error: str | None = None,
	whatsapp_account: str | None = None,
	initial_status: str | None = None,
):
	"""Persist an outbound message via the dispatcher so all side
	effects fire (idempotency, realtime, identity resolution).

	Per-kind formatting is delegated to the dispatch table above —
	this function only assembles the `NormalizedEvent` envelope and
	latches the final `sent`/`failed` status after the row lands.
	"""
	from msuite_inbox.inbox.services.dispatcher import handle as dispatcher_handle

	kind = payload.get("type") or "text"
	builder = _OUTBOUND_SHAPE_BUILDERS.get(kind, _shape_text)
	content_type, text, attachments, interactive_payload, template_name = builder(payload)

	sender_type = payload.get("sender_type") or SenderType.BOT
	sender_user = payload.get("sender_user") or (
		frappe.session.user if sender_type == SenderType.AGENT else ""
	)
	if not platform_message_id:
		platform_message_id = f"outbound-{frappe.generate_hash(length=12)}"

	status_to_use = initial_status or (MessageStatus.SENT if ok else MessageStatus.FAILED)

	bsuid_val = getattr(handle_doc, "bsuid", None) or (
		handle_doc.platform_handle if is_bsuid(handle_doc.platform_handle) else ""
	)
	parent_bsuid_val = getattr(handle_doc, "parent_bsuid", "") or ""

	event = NormalizedEvent(
		channel_type=ChannelType.WHATSAPP,
		inbox=conversation_doc.inbox,
		platform_handle=handle_doc.platform_handle,
		display_name=handle_doc.display_name or "",
		direction=Direction.OUTBOUND,
		initial_status=status_to_use,
		content_type=content_type,
		text_content=text,
		platform_message_id=platform_message_id,
		reply_to_platform_id=payload.get("reply_to_platform_id") or "",
		sender_type=sender_type,
		sender_user=sender_user,
		sender_name=payload.get("sender_name") or sender_user or ("Bot" if sender_type == SenderType.BOT else "Agent"),
		bsuid=bsuid_val,
		parent_bsuid=parent_bsuid_val,
		attachments=attachments,
		interactive_payload=interactive_payload,
		template_name=template_name,
		reference_doctype=payload.get("reference_doctype") or "",
		reference_name=payload.get("reference_name") or "",
		whatsapp_account=whatsapp_account or getattr(conversation_doc, "whatsapp_account", "") or "",
		raw_payload={"send_payload": payload, "ok": ok, "error": error},
	)

	for attempt in range(2):
		try:
			result = dispatcher_handle(event)
			if result.get("message") and initial_status is None:
				# Save via the controller (not db.set_value) so the
				# on_update hook fires and latches sent_at / failed_at.
				msg = frappe.get_doc("Channel Message", result["message"])
				msg.status = MessageStatus.SENT if ok else MessageStatus.FAILED
				msg.status_error = error or ""
				msg.save(ignore_permissions=True)
			return {"message": result.get("message"), "ok": ok, "error": error}
		except Exception as e:
			err_str = str(e)
			if attempt == 0 and ("1020" in err_str or "Record has changed" in err_str or "TimestampMismatch" in err_str):
				logger.warning("Retrying WhatsApp _record_outbound after optimistic lock conflict on %s: %s", conversation_doc.name, e)
				try:
					frappe.db.rollback()
					conversation_doc.reload()
					handle_doc.reload()
				except Exception:
					pass
				continue
			logger.exception("WhatsApp _record_outbound dispatch failed")
			return {"message": None, "ok": False, "error": error or str(e)[:500]}


# ── Template body rendering (for local display, NOT the Meta payload) ────


def _render_template_body(template_name: str, body_param) -> str:
	"""Return the template body with `body_param` values substituted in.

	Supports the two parameter formats WhatsApp Cloud API accepts:
	  • POSITIONAL: `{{1}}`, `{{2}}` placeholders → indexed by string keys
	                `"1"`, `"2"` in `body_param`.
	  • NAMED:      `{{order_id}}` placeholders → looked up by key in
	                `body_param`.

	`body_param` may be a dict already, a JSON string, or empty.

	Empty / missing values render as the original `{{x}}` so it's
	obvious to the agent which slot didn't get a value (rather than
	silently producing a sentence with holes).
	"""
	if not template_name:
		return ""
	tpl = frappe.db.get_value(
		"WhatsApp Templates",
		template_name,
		["template", "parameter_format"],
		as_dict=True,
	)
	if not tpl or not tpl.template:
		return ""

	import json as _json
	import re as _re

	params = body_param
	if isinstance(params, str):
		try:
			params = _json.loads(params)
		except (ValueError, TypeError):
			params = {}
	if not isinstance(params, dict):
		params = {}

	def _sub(match: "_re.Match") -> str:
		key = match.group(1).strip()
		if key in params and params[key] not in (None, ""):
			return str(params[key])
		return match.group(0)  # leave the placeholder visible

	rendered = _re.sub(r"\{\{\s*([^}]+?)\s*\}\}", _sub, tpl.template)
	rendered = rendered.strip()
	# Some Approved-template bodies are stored with surrounding quotes
	# (a Meta payload artifact). Strip them so the bubble shows the
	# plain message — never the quote characters.
	if len(rendered) >= 2 and rendered[0] == rendered[-1] and rendered[0] in ('"', "'"):
		rendered = rendered[1:-1].strip()
	return rendered


# ── What Inbox asks this channel for, through the msuite_inbox_channels hook ──


def find_default_phone_account(direction: str = "incoming") -> str | None:
	from msuite_whatsapp.queries.account_repository import find_default_phone_account as find

	return find(direction)


def get_display_phone_number(account: str | None) -> str:
	from msuite_whatsapp.queries.account_repository import get_display_phone_number as display

	return display(account)


def capture_flow_response(message_doc, event) -> None:
	from msuite_whatsapp.services.flows import flow_response_service

	flow_response_service.capture_from_message(message_doc, event)


def handle_inbound_order(conversation_doc, message_doc) -> None:
	from msuite_whatsapp.services.orders import order_flow_service

	order_name = order_flow_service.record_inbound_cart_order(conversation_doc, message_doc)
	order_flow_service.send_order_address_flow(conversation_doc, message_doc, order_name=order_name)


def update_bulk_recipient_status(message_doc) -> None:
	"""Copy a Channel Message's status onto the recipient row of the blast that sent it."""
	from msuite_whatsapp.services.bulk.bulk_send_service import row_parent

	# Get phone number from Channel Handle
	phone = frappe.db.get_value("Channel Handle", message_doc.channel_handle, "platform_handle")
	if not phone:
		return

	if not frappe.db.exists("Bulk WhatsApp Message", message_doc.reference_name):
		return

	# Convert status to match select options (Queued, Sent, Delivered, Read, Failed)
	status_label = message_doc.status.capitalize() if message_doc.status else ""
	if status_label == "Read":
		status_label = "Read"
	elif status_label == "Delivered":
		status_label = "Delivered"
	elif status_label == "Failed":
		status_label = "Failed"
	elif status_label == "Sent":
		status_label = "Sent"
	elif status_label == "Queued":
		status_label = "Queued"

	# Update this blast's recipient row — its own rows (Individual, or a
	# Recipient List snapshotted per blast since audit H11); the shared
	# list only for legacy never-snapshotted blasts.
	parent, parenttype = row_parent(message_doc.reference_name)
	frappe.db.sql(
		"""
            UPDATE `tabWhatsApp Recipient`
            SET status = %s
            WHERE parenttype = %s AND parent = %s AND (mobile_number = %s OR REPLACE(mobile_number, '+', '') = REPLACE(%s, '+', ''))
		""",
		(status_label, parenttype, parent, phone, phone),
	)
