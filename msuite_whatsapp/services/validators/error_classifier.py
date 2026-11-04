"""
Meta WhatsApp Cloud API Error Classifier — categorizes Meta error codes,
subcodes, and exception types into human-readable descriptions and retryability flags.
"""

from __future__ import annotations

import re
from typing import Any

# Intentionally kept separate from whatsapp.providers.meta.client.TRANSIENT_META_CODES.
# This classifier includes 131047 (re-engagement window) and 131049 (24-48h ecosystem cooldown)
# which require deferred/manual handling rather than immediate fast backoff, and matches keywords.
# client.TRANSIENT_META_CODES specifically gates short-interval automation retries (and includes
# codes 4 and 133016 which this set lacks). Do not merge without reconciling retry-window semantics.
# Error codes known to be transient / temporary (RETRYABLE)
RETRYABLE_ERROR_CODES = {
	130429,  # Rate Limit Exceeded
	131016,  # Service Temporarily Unavailable
	131047,  # Re-engagement Window / Rate Limit
	131049,  # Ecosystem Engagement Limit (24–48h cooldown)
	131056,  # Message Rate Limit Hit
	80007,   # Meta Server Busy
	500,     # Internal Server Error
	502,     # Bad Gateway
	503,     # Service Unavailable
	504,     # Gateway Timeout
	429,     # Too Many Requests
}

# Error codes that require deferred 24-48h cooldown rather than fast backoff
DEFERRED_RETRY_ERROR_CODES = {
	131049,  # Ecosystem Engagement Limit
}


def is_ecosystem_limit_error(code: str | int) -> bool:
	"""Check if an error code represents Meta's per-user ecosystem limit (131049)."""
	try:
		return int(code) in DEFERRED_RETRY_ERROR_CODES
	except (ValueError, TypeError):
		return False

# Detailed human-friendly descriptions for Meta API error codes
META_ERROR_CATALOG: dict[int, str] = {
	130429: "Rate Limit Exceeded — Account or phone speed limit reached",
	131016: "Service Temporarily Unavailable — Meta WhatsApp servers busy",
	131026: "Message Undeliverable — Phone number invalid or not active on WhatsApp",
	131047: "User Blocked / Spammer — Recipient blocked this business or rate limit reached",
	131049: "Ecosystem Engagement Limit — User reached Meta's marketing message frequency cap. Retry after 24–48 hours",
	131051: "Unsupported Device — Recipient WhatsApp version cannot display this message type",
	131052: "Media Upload Failed — Header image/video URL timed out or exceeded size limit",
	131053: "Media Format Unsupported — File format not supported by WhatsApp",
	131009: "Parameter Mismatch — Number of variables supplied does not match template",
	132001: "Template Not Found — Template name or language code not found on Meta WABA",
	132012: "Template Disabled — Template paused by Meta due to low quality rating",
	133004: "Account Restricted — WABA restricted due to payment failure or policy violations",
	190: "Token Expired — Meta access token expired or revoked",
	100: "Invalid Parameter — Invalid request parameters or credentials",
	80007: "Meta Infrastructure Error — Internal Meta server hiccup",
}


def classify_meta_error(err_obj: Any) -> tuple[str, str, bool]:
	"""Classify an exception or error dict into `(error_code, failure_reason, is_retryable)`.

	Args:
		err_obj: A MetaAPIError instance, generic Exception, or dict response from Meta.

	Returns:
		Tuple of (error_code_str, failure_reason_str, is_retryable_bool)
	"""
	error_code = ""
	reason = ""
	is_retryable = False

	# Extract error details from MetaAPIError or dict
	if hasattr(err_obj, "response_json") and isinstance(err_obj.response_json, dict):
		meta_err = err_obj.response_json.get("error", {})
		code_val = meta_err.get("code") or getattr(err_obj, "status_code", 0)
		if code_val:
			error_code = str(code_val)
		msg = meta_err.get("error_user_msg") or meta_err.get("message") or str(err_obj)
		reason = msg
	elif isinstance(err_obj, dict):
		meta_err = err_obj.get("error", {})
		code_val = meta_err.get("code")
		if code_val:
			error_code = str(code_val)
		reason = meta_err.get("error_user_msg") or meta_err.get("message") or str(err_obj)
	else:
		reason = str(err_obj)

	# Try extracting numeric code from string error if not yet found
	if not error_code and reason:
		code_match = re.search(r"\b(13\d{4}|80007|429|500|502|503|504)\b", reason)
		if code_match:
			error_code = code_match.group(1)

	# Resolve catalog description if available
	numeric_code = int(error_code) if error_code.isdigit() else 0
	if numeric_code in META_ERROR_CATALOG:
		catalog_msg = META_ERROR_CATALOG[numeric_code]
		if catalog_msg not in reason:
			reason = f"{catalog_msg} ({reason})"

	# Determine retryability
	if numeric_code in RETRYABLE_ERROR_CODES:
		is_retryable = True
	elif any(keyword in reason.lower() for keyword in ["timeout", "connection refused", "rate limit", "try again"]):
		is_retryable = True

	if not error_code:
		error_code = "UNKNOWN"

	return error_code, reason[:500], is_retryable
