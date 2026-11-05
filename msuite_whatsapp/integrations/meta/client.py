"""
WhatsApp Cloud API — low-level HTTP client.

Single source of truth for talking to Meta's Graph API. Every send path
(Inbox channel handler, Bulk Messaging, Notifications, Flows, …) goes
through these helpers so we have one place to fix tokens, retries,
timeouts, and error reporting.

  • `send_to_meta(account, body)`     POST  /<phone_id>/messages -> (json, send_path)
  • `post_to_meta(account, body)`     same, returns the json only
  • `fetch_media_url(account, mid)`   GET   /<media_id>
  • `download_media(url, account)`    GET   <signed_url>  (bytes)
  • `verify_token(account)`           GET   /<waba_id>

Errors are normalised into a `MetaAPIError` so callers can decide whether
to surface, log, or retry.

This module replaces `whatsapp.utils.send`, which now re-exports these
symbols for backward compatibility with external importers (notably
`inbox.services.channels.whatsapp`).
"""

from __future__ import annotations

import json
from urllib.parse import urlparse

import frappe
import requests
import urllib3.exceptions
from frappe.utils import cint

from msuite_whatsapp.constants import WHATSAPP_SEND_PATH_CLOUD_API, WHATSAPP_SEND_PATH_MARKETING_MESSAGES
from msuite_whatsapp.constants import (
	WHATSAPP_MEDIA_HOST_SUFFIXES,
	WHATSAPP_MM_ENDPOINT,
	WHATSAPP_MM_FALLBACK_ERROR_CODES,
	WHATSAPP_MM_PRODUCT_POLICY,
	WHATSAPP_MM_SENDABLE_CATEGORY,
	WHATSAPP_MM_SITE_CONFIG_KEY,
)
from msuite_whatsapp.services.domain import LOGGER_NAME, REQUEST_TIMEOUT
from msuite_whatsapp.queries import account_repository as accounts

logger = frappe.logger(LOGGER_NAME)


class MetaAPIError(Exception):
	"""Raised when Meta returns a non-2xx or the response has an `error` field."""

	def __init__(self, message: str, response_json: dict | None = None, status_code: int = 0):
		super().__init__(message)
		self.response_json = response_json or {}
		self.status_code = status_code


# Intentionally kept separate from whatsapp.validators.error_classifier.RETRYABLE_ERROR_CODES.
# That set includes 131047 (re-engagement window) and 131049 (24-48h ecosystem cooldown) which
# cannot succeed via fast 1-15 min retries, and its keyword matching widens retry scope.
# Conversely, this set includes transient codes 4 (server temporary) and 133016 (rate limit)
# that the classifier omits. Do not merge without reconciling retry-window semantics.
# 502 and 504 are omitted: a 502/504 can arrive after Meta already accepted and delivered
# the message, so retrying could send a duplicate.
TRANSIENT_STATUS_CODES = {429, 500, 503}
TRANSIENT_META_CODES = {4, 80007, 130429, 131056, 133016}

_NameResolutionError = getattr(urllib3.exceptions, "NameResolutionError", urllib3.exceptions.NewConnectionError)
NEVER_CONNECTED_ERRORS = (
	urllib3.exceptions.NewConnectionError,
	ConnectionRefusedError,
	_NameResolutionError,
)


def _is_connection_never_established(exc: Exception) -> bool:
	visited = set()
	queue = [exc]
	while queue:
		cur = queue.pop(0)
		if cur is None or id(cur) in visited:
			continue
		visited.add(id(cur))

		if isinstance(cur, NEVER_CONNECTED_ERRORS):
			return True

		for next_node in (
			cur.args[0] if isinstance(cur, BaseException) and cur.args and isinstance(cur.args[0], BaseException) else None,
			getattr(cur, "reason", None),
			getattr(cur, "__cause__", None),
		):
			if isinstance(next_node, BaseException):
				queue.append(next_node)

	return False


def retry_kind(exc: Exception) -> str | None:
	"""Classify whether a send failure is safe to retry.

	Returns 'transient' for failures safe to retry (HTTP 429/500/503, Meta rate limits,
	connect timeouts, or connection errors where the connection was never established),
	or None for terminal failures (e.g. Meta error 131062: BSUID recipients not supported,
	validation errors, permission errors), 502/504 gateway errors (which can arrive after Meta
	already accepted and delivered the message, so retrying could send a duplicate),
	read timeouts, or connection errors where Meta may have already accepted the message.
	"""
	if not exc or not isinstance(exc, Exception):
		return None

	cause = getattr(exc, "__cause__", None)
	chain = (exc, cause)

	if any(isinstance(c, requests.ReadTimeout) for c in chain):
		return None

	if any(isinstance(c, requests.ConnectTimeout) for c in chain):
		return "transient"

	for c in chain:
		if isinstance(c, requests.ConnectionError):
			return "transient" if _is_connection_never_established(c) else None

	if cint(getattr(exc, "status_code", 0)) in TRANSIENT_STATUS_CODES:
		return "transient"

	response_json = getattr(exc, "response_json", None)
	if isinstance(response_json, dict):
		err = response_json.get("error")
		if isinstance(err, dict):
			if any(cint(err.get(k)) in TRANSIENT_META_CODES for k in ("code", "error_subcode")):
				return "transient"

	return None


# ── HTTP — outbound message ─────────────────────────────────────────────


def _template_category(account_name: str, template: dict) -> str | None:
	"""Category of the approved template named in a send body, or None if unknown.

	Looks the template up by its Meta name (`actual_name`, else `template_name`)
	and language on the given account. One indexed DB read."""
	name = (template or {}).get("name")
	if not name:
		return None
	language = ((template or {}).get("language") or {}).get("code")
	for name_field in ("actual_name", "template_name"):
		filters = {name_field: name, "whatsapp_account": account_name}
		if language:
			filters["language_code"] = language
		category = frappe.db.get_value("WhatsApp Templates", filters, "category")
		if category:
			return category
	return None


def _should_use_marketing_messages(doc, body: dict) -> bool:
	"""True only when the site opted in AND the body is a known MARKETING template.

	Anything else (text, interactive, utility/auth, unknown template) stays on the Cloud API."""
	from msuite_core.central_config import get_central_config

	if not cint(get_central_config(WHATSAPP_MM_SITE_CONFIG_KEY)):
		return False
	if body.get("type") != "template":
		return False
	return _template_category(doc.name, body.get("template") or {}) == WHATSAPP_MM_SENDABLE_CATEGORY


def _post_json(url: str, token: str, body: dict) -> dict:
	"""POST `body` as JSON and return the parsed response; raise MetaAPIError on failure."""
	headers = {
		"Authorization": f"Bearer {token}",
		"Content-Type": "application/json",
	}
	try:
		resp = requests.post(url, headers=headers, data=json.dumps(body), timeout=REQUEST_TIMEOUT)
	except requests.RequestException as e:
		logger.exception("WhatsApp post_to_meta network error")
		raise MetaAPIError(str(e)) from e

	try:
		data = resp.json() if resp.content else {}
	except ValueError:  # non-JSON gateway/HTML error body
		data = {}
	if not resp.ok or (isinstance(data, dict) and data.get("error")):
		err = (data.get("error") or {}) if isinstance(data, dict) else {}
		msg = err.get("message") or err.get("error_user_msg") or f"HTTP {resp.status_code}"
		raise MetaAPIError(msg, response_json=data, status_code=resp.status_code)
	return data


def _is_safe_to_fallback(exc: MetaAPIError) -> bool:
	"""A Marketing Messages failure is re-sent on /messages only for the documented
	"not onboarded" codes (WHATSAPP_MM_FALLBACK_ERROR_CODES); auth, validation,
	window and transient errors would fail again or risk a duplicate."""
	err = exc.response_json.get("error") if isinstance(exc.response_json, dict) else None
	if not isinstance(err, dict):
		return False
	return cint(err.get("code")) in WHATSAPP_MM_FALLBACK_ERROR_CODES


def send_to_meta(account, body: dict, phone_number_id: str | None = None) -> tuple[dict, str]:
	"""POST a fully-formed message body and report which route carried it.

	Marketing template sends go to `/<phone_id>/marketing_messages` instead of `/messages` when
	the site opted in (`site_config` key WHATSAPP_MM_SITE_CONFIG_KEY); if Meta rejects that call
	(e.g. not onboarded, error 131063) the message is re-sent once on the Cloud API.
	Transient/network failures are never re-sent.

	Args:
	    account:         WhatsApp Account doc-name or doc.
	    body:            Already-built Meta message body -- caller owns the shape.
	    phone_number_id: send from this number of the account; None = default outgoing.

	Returns:
	    (response_json, send_path). send_path is WHATSAPP_SEND_PATH_MARKETING_MESSAGES only when the
	    `/marketing_messages` call succeeded, else WHATSAPP_SEND_PATH_CLOUD_API (including fallback).
	    response_json example: {"messaging_product": "whatsapp", "contacts": [...],
	    "messages": [{"id": "wamid....."}]}.

	Raises:
	    MetaAPIError on non-2xx or `error` in body, or when phone_number_id is not on the account.
	"""
	doc = accounts.get_account_doc(account)
	base_url, version, token = accounts.get_credentials(doc)
	if phone_number_id and phone_number_id not in {p.phone_number_id for p in (getattr(doc, "phones", None) or [])}:
		raise MetaAPIError(f"Number {phone_number_id} is not on WhatsApp Account {doc.name!r}")
	phone_id = phone_number_id or accounts.get_phone_number_id(doc, "outgoing")

	if _should_use_marketing_messages(doc, body):
		mm_body = {**body, "product_policy": WHATSAPP_MM_PRODUCT_POLICY}
		try:
			response = _post_json(f"{base_url}/{version}/{phone_id}/{WHATSAPP_MM_ENDPOINT}", token, mm_body)
			return response, WHATSAPP_SEND_PATH_MARKETING_MESSAGES
		except MetaAPIError as exc:
			if not _is_safe_to_fallback(exc):
				raise
			logger.warning("Marketing Messages API rejected send, falling back to Cloud API: %s", exc)

	return _post_json(f"{base_url}/{version}/{phone_id}/messages", token, body), WHATSAPP_SEND_PATH_CLOUD_API


def post_to_meta(account, body: dict, phone_number_id: str | None = None) -> dict:
	"""POST a message body to Meta (see `send_to_meta`) and return only the parsed JSON response.

	Kept for callers that do not need the send route.

	Raises:
	    MetaAPIError on non-2xx or `error` in body.
	"""
	return send_to_meta(account, body, phone_number_id)[0]


# ── HTTP — inbound media ────────────────────────────────────────────────


def fetch_media_url(account, media_id: str) -> dict:
	"""Resolve a Meta media_id → signed download URL.

	Meta gives us a media_id on inbound media; the actual file URL has to
	be fetched separately and is short-lived (~5 minutes).

	Returns:
	    {"url": str, "mime_type": str, "sha256": str, "file_size": int}
	    — empty values when missing. Never raises on 4xx; logs and returns {}.
	"""
	if not media_id:
		return {}
	doc = accounts.get_account_doc(account)
	base_url, version, token = accounts.get_credentials(doc)
	url = f"{base_url}/{version}/{media_id}/"
	headers = {"Authorization": f"Bearer {token}"}
	try:
		resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
	except requests.RequestException:
		logger.exception("WhatsApp fetch_media_url network error for %s", media_id)
		return {}
	if not resp.ok:
		logger.warning("WhatsApp media_id=%s returned HTTP %s", media_id, resp.status_code)
		return {}
	try:
		return resp.json() or {}
	except Exception:
		return {}


def verify_token(account) -> dict:
	"""Check that the stored token still works against Meta.

	We never hold the Meta app secret here (only the provider does), so a
	real `/debug_token` inspection is off the table. The closest honest
	proxy without it: ask Meta for the WABA itself with the WABA's own
	token. A 401/403 means the token is dead or missing the read scope;
	anything else 2xx means it's at least minimally valid right now.

	Returns {"ok": bool, "error": str} -- never raises.
	"""
	doc = accounts.get_account_doc(account)
	try:
		base_url, version, token = accounts.get_credentials(doc)
	except Exception as e:
		return {"ok": False, "error": str(e)}

	waba_id = doc.waba_id or doc.business_id
	if not waba_id:
		return {"ok": False, "error": "No WABA ID configured on this account."}

	url = f"{base_url}/{version}/{waba_id}"
	headers = {"Authorization": f"Bearer {token}"}
	try:
		resp = requests.get(url, headers=headers, params={"fields": "id,name"}, timeout=REQUEST_TIMEOUT)
	except requests.RequestException as e:
		logger.exception("WhatsApp verify_token network error for %s", doc.name)
		return {"ok": False, "error": f"Network error: {e}"}

	if resp.ok:
		return {"ok": True, "error": ""}

	try:
		err = (resp.json() or {}).get("error", {})
	except Exception:
		err = {}
	msg = err.get("message") or f"HTTP {resp.status_code}"
	return {"ok": False, "error": msg}


def _is_meta_media_url(url: str) -> bool:
	"""True only for https URLs on a Meta media host, so the Bearer token never goes elsewhere."""
	try:
		parsed = urlparse(url)
		host = (parsed.hostname or "").lower()
	except ValueError:
		return False
	return parsed.scheme == "https" and any(
		host == suffix or host.endswith("." + suffix) for suffix in WHATSAPP_MEDIA_HOST_SUFFIXES
	)


def download_media(media_url: str, account) -> bytes | None:
	"""Download the actual media bytes from the signed URL.

	Returns None on failure — caller decides whether that's fatal.
	"""
	if not media_url:
		return None
	if not _is_meta_media_url(media_url):
		logger.warning("WhatsApp download_media refused non-Meta URL host")
		return None
	doc = accounts.get_account_doc(account)
	_, _, token = accounts.get_credentials(doc)
	headers = {"Authorization": f"Bearer {token}"}
	try:
		resp = requests.get(media_url, headers=headers, timeout=REQUEST_TIMEOUT)
	except requests.RequestException:
		logger.exception("WhatsApp download_media failed for %s", media_url)
		return None
	if not resp.ok:
		logger.warning("WhatsApp download_media HTTP %s for %s", resp.status_code, media_url)
		return None
	return resp.content
