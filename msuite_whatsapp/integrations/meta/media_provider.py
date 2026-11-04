"""
WhatsApp media upload provider.

Uploads files to Meta's media API and returns a media_id that can be
used in template messages, interactive messages, and media messages.
Cache-aware — `WhatsApp Media Cache` dedups by (account, file hash) so
the same image used across multiple templates/sends is only uploaded
to Meta once within the TTL window.

This module replaces `whatsapp.utils.media`, which now re-exports these
symbols for backward compatibility.
"""

from __future__ import annotations

import hashlib
import os

import frappe
from frappe import _
from frappe.utils import add_days, now_datetime

from msuite_core.constants import GRAPH_API_URL, GRAPH_API_VERSION
from msuite_core.utils.files import detect_mime, resolve_frappe_path
from msuite_whatsapp.services.domain import LOGGER_NAME, WHATSAPP_MEDIA_CACHE_TTL_DAYS
from msuite_whatsapp.queries import account_repository as accounts

logger = frappe.logger(LOGGER_NAME)

MEDIA_CACHE_DOCTYPE = "WhatsApp Media Cache"

# Meta-supported MIME types per media category
SUPPORTED_TYPES = {
	"image": {"image/jpeg", "image/png"},
	"video": {"video/mp4", "video/3gpp"},
	"document": {
		"application/pdf",
		"application/vnd.ms-excel",
		"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
		"application/msword",
		"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
	},
	"audio": {"audio/aac", "audio/mp4", "audio/mpeg", "audio/amr", "audio/ogg"},
}


def upload_media(file_path_or_url: str, whatsapp_account: str) -> str:
	"""
	Upload a file to Meta's media API and return the media_id.

	Handles both Frappe file paths (/files/..., /private/files/...) and
	absolute filesystem paths. Detects MIME type automatically.

	Args:
	    file_path_or_url: Frappe file path or absolute path
	    whatsapp_account: WhatsApp Account document name

	Returns:
	    media_id string from Meta

	Raises:
	    frappe.ValidationError: if file not found or unsupported type
	"""
	import requests

	abs_path = resolve_frappe_path(file_path_or_url)

	if not os.path.exists(abs_path):
		frappe.throw(_("File not found: {0}").format(file_path_or_url))

	mime_type = detect_mime(abs_path)
	file_hash = _hash_file(abs_path)

	account = accounts.get_account_doc(whatsapp_account)
	whatsapp_account = account.name

	cached = _get_cached_media_id(whatsapp_account, file_hash)
	if cached:
		logger.info(f"Media cache hit: {file_path_or_url} → {cached}")
		return cached

	token = account.get_password("token")
	phone_id = accounts.get_phone_number_id(account, "outgoing")

	# Upload to Meta: POST /{phone_number_id}/media
	url = f"{GRAPH_API_URL}/{GRAPH_API_VERSION}/{phone_id}/media"

	with open(abs_path, "rb") as f:
		response = requests.post(
			url,
			headers={"Authorization": f"Bearer {token}"},
			files={"file": (os.path.basename(abs_path), f, mime_type)},
			data={"messaging_product": "whatsapp"},
			timeout=60,
		)

	result = response.json()

	if "error" in result:
		err = result["error"]
		logger.error(f"Media upload failed: {err.get('message')}")
		frappe.throw(
			_("Media upload failed: {0}").format(
				err.get("error_user_msg") or err.get("message", "Unknown error")
			)
		)

	media_id = result.get("id")
	if not media_id:
		frappe.throw(_("Media upload returned no ID. Response: {0}").format(str(result)))

	logger.info(f"Media uploaded: {file_path_or_url} → {media_id}")
	_cache_media_id(whatsapp_account, file_hash, media_id, mime_type)
	return media_id


def get_media_header_param(file_path_or_url: str, header_type: str, whatsapp_account: str) -> dict:
	"""
	Build a header parameter dict for a template message.

	Uploads the file to Meta and returns the parameter dict with media_id.
	Handles IMAGE, VIDEO, and DOCUMENT header types.

	Args:
	    file_path_or_url: Frappe file path or URL
	    header_type: "IMAGE", "VIDEO", or "DOCUMENT"
	    whatsapp_account: WhatsApp Account document name

	Returns:
	    Dict like {"type": "image", "image": {"id": "MEDIA_ID"}}
	"""
	media_id = upload_media(file_path_or_url, whatsapp_account)
	media_type = header_type.lower()  # IMAGE → image, VIDEO → video, DOCUMENT → document

	return {
		"type": media_type,
		media_type: {"id": media_id},
	}


# ── Cache helpers ─────────────────────────────────────────────────────────


def _hash_file(abs_path: str) -> str:
	"""SHA-256 of file contents, read in chunks to handle large media."""
	digest = hashlib.sha256()
	with open(abs_path, "rb") as f:
		for chunk in iter(lambda: f.read(65536), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _get_cached_media_id(whatsapp_account: str, file_hash: str) -> str | None:
	cutoff = add_days(now_datetime(), -WHATSAPP_MEDIA_CACHE_TTL_DAYS)
	return frappe.db.get_value(
		MEDIA_CACHE_DOCTYPE,
		{
			"whatsapp_account": whatsapp_account,
			"file_hash": file_hash,
			"uploaded_at": [">", cutoff],
		},
		"media_id",
		order_by="uploaded_at desc",
	)


def _cache_media_id(whatsapp_account: str, file_hash: str, media_id: str, mime_type: str) -> None:
	doc = frappe.new_doc(MEDIA_CACHE_DOCTYPE)
	doc.whatsapp_account = whatsapp_account
	doc.file_hash = file_hash
	doc.media_id = media_id
	doc.mime_type = mime_type
	doc.uploaded_at = now_datetime()
	doc.insert(ignore_permissions=True)
