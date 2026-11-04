"""WhatsApp phone-number onboarding: status -> request OTP -> verify OTP -> register.

Credentials come from the `WhatsApp Account` (encrypted token) the number
belongs to, not from env vars: msuite is multi-tenant. The 2-step-verification
PIN and the OTP are passed straight to Meta and never stored or logged.

Every public function returns `{"ok": True, "data": {...}}` or
`{"ok": False, "error": {"code", "message", "retry_after"?}}` - Meta failures
are data, not exceptions, so the SPA can render them. Caller mistakes
(bad method, malformed code/PIN, foreign phone id) raise `frappe.ValidationError`.

Error codes per Meta's Cloud API error-codes page. request_code/verify_code
only document HTTP statuses (400 invalid, 422 expired, 429 rate limited), so
those are mapped by status; 136025 is treated as rate limiting.
"""

from __future__ import annotations

import re

import frappe
import requests
from frappe import _

from msuite_core.constants import LOGGER_NAME
from msuite_whatsapp.queries import account_repository as accounts

STATUS_FIELDS = "verified_name,code_verification_status,display_phone_number,quality_rating"
CODE_METHODS = ("SMS", "VOICE")
REQUEST_TIMEOUT_SEC = 20
_SIX_DIGITS = re.compile(r"^\d{6}$")

logger = frappe.logger(LOGGER_NAME)

# Meta error code / subcode -> our code. Subcode wins over code.
_RATE_LIMITED = {4, 80007, 130429, 133008, 133009, 133016, 136025, 613}
_ERROR_BY_CODE = {
	133005: ("pin_mismatch", "Wrong two-step verification PIN. Enter the number's existing PIN, or reset it in WhatsApp Manager."),
	133006: ("reverification_needed", "This number must be verified before it can be registered."),
	133010: ("not_registered", "This number is not registered yet. Register it first."),
	133015: ("cooldown", "This number was recently deleted. Wait about 5 minutes and try again."),
	190: ("token_invalid", "The WhatsApp access token is invalid or expired. Reconnect the account."),
	0: ("token_invalid", "The WhatsApp access token is invalid or expired. Reconnect the account."),
}
_RATE_MESSAGE = "Too many attempts for this number. Wait before trying again."


def _validate_digits(value: str, label: str) -> str:
	value = (value or "").strip()
	if not _SIX_DIGITS.match(value):
		frappe.throw(_("{0} must be exactly 6 digits.").format(label), frappe.ValidationError)
	return value


def _resolve(account: str, phone_number_id: str) -> tuple[str, str]:
	"""(graph_base, token) after checking the number belongs to the account."""
	phone_number_id = (phone_number_id or "").strip()
	if not phone_number_id.isdigit():
		frappe.throw(_("Invalid phone number id."), frappe.ValidationError)
	owned = frappe.db.exists(
		accounts.PHONE_CHILD_DOCTYPE, {"parent": account, "phone_number_id": phone_number_id}
	)
	if not phone_number_id or not owned:
		frappe.throw(_("Phone number does not belong to this account."), frappe.ValidationError)
	base, version, token = accounts.get_credentials(account)
	return f"{base}/{version}", token


def _failure(code: str, message: str, **extra) -> dict:
	return {"ok": False, "error": {"code": code, "message": message, **extra}}


def _map_error(resp: requests.Response, op: str) -> dict:
	try:
		raw = resp.json()
	except ValueError:
		raw = None
	err = (raw.get("error") if isinstance(raw, dict) else None) or {}
	code, sub = err.get("code"), err.get("error_subcode")
	details = (err.get("error_data") or {}).get("details") or err.get("error_user_msg") or err.get("message")
	text = (details or "").lower()

	if resp.status_code == 429 or sub in _RATE_LIMITED or code in _RATE_LIMITED:
		retry = resp.headers.get("Retry-After")
		extra = {"retry_after": int(retry)} if retry and retry.isdigit() else {}
		return _failure("rate_limited", details or _RATE_MESSAGE, **extra)
	known = sub if sub in _ERROR_BY_CODE else code
	if known in _ERROR_BY_CODE:
		mapped, message = _ERROR_BY_CODE[known]
		return _failure(mapped, message)
	if resp.status_code == 422 or "expired" in text:
		return _failure("expired_code", "That code has expired. Request a new one.")
	if "wait" in text and ("request" in text or "code" in text):
		return _failure("cooldown", details)
	if op == "verify_code" and ("invalid" in text or "incorrect" in text or "wrong" in text):
		return _failure("invalid_code", "That code is incorrect. Check it and try again.")
	return _failure("meta_error", details or _("Meta rejected the request."))


def _call(method: str, url: str, token: str, account: str, *, params=None, json=None) -> dict:
	op = url.rstrip("/").rsplit("/", 1)[-1]
	try:
		resp = requests.request(
			method,
			url,
			params=params,
			json=json,
			headers={"Authorization": f"Bearer {token}"},
			timeout=REQUEST_TIMEOUT_SEC,
		)
	except requests.RequestException as e:
		logger.warning("whatsapp onboarding: network error %s", type(e).__name__)
		return _failure("network_error", _("Could not reach Meta. Try again."))
	if not resp.ok:
		result = _map_error(resp, op)
		if result["error"]["code"] == "token_invalid":
			accounts.set_reauth_flag(account, needs_reauth=True, error="Token rejected during phone onboarding")
		return result
	try:
		return {"ok": True, "data": resp.json() or {}}
	except ValueError:
		return _failure("meta_error", _("Meta returned an unreadable response."))


def get_status(account: str, phone_number_id: str) -> dict:
	base, token = _resolve(account, phone_number_id)
	result = _call("GET", f"{base}/{phone_number_id}", token, account, params={"fields": STATUS_FIELDS})
	if result["ok"]:
		d = result["data"]
		updates = {k: d[k] for k in ("verified_name", "display_phone_number", "quality_rating") if d.get(k)}
		if updates:
			frappe.db.set_value(
				accounts.PHONE_CHILD_DOCTYPE,
				{"parent": account, "phone_number_id": phone_number_id},
				updates,
				update_modified=False,
			)
			frappe.clear_document_cache(accounts.ACCOUNT_DOCTYPE, account)
		result["data"] = {k: d.get(k) for k in STATUS_FIELDS.split(",")}
	return result


def request_code(account: str, phone_number_id: str, method: str = "SMS", language: str = "en_US") -> dict:
	method = (method or "").upper()
	if method not in CODE_METHODS:
		frappe.throw(_("code_method must be SMS or VOICE."), frappe.ValidationError)
	if not re.match(r"^[a-z]{2,3}([_-][A-Za-z0-9]{2,4})?$", language or ""):
		frappe.throw(_("Invalid language code."), frappe.ValidationError)
	base, token = _resolve(account, phone_number_id)
	return _call(
		"POST",
		f"{base}/{phone_number_id}/request_code",
		token,
		account,
		json={"code_method": method, "language": language},
	)


def verify_code(account: str, phone_number_id: str, code: str) -> dict:
	code = _validate_digits(code, _("Code"))
	base, token = _resolve(account, phone_number_id)
	return _call("POST", f"{base}/{phone_number_id}/verify_code", token, account, json={"code": code})


def register(account: str, phone_number_id: str, pin: str) -> dict:
	pin = _validate_digits(pin, _("PIN"))
	base, token = _resolve(account, phone_number_id)
	return _call(
		"POST",
		f"{base}/{phone_number_id}/register",
		token,
		account,
		json={"messaging_product": "whatsapp", "pin": pin},
	)


def _save_username(account: str, phone_number_id: str, username: str, status: str) -> None:
	frappe.db.set_value(
		accounts.PHONE_CHILD_DOCTYPE,
		{"parent": account, "phone_number_id": phone_number_id},
		{"username": username, "username_status": status},
		update_modified=False,
	)
	frappe.clear_document_cache(accounts.ACCOUNT_DOCTYPE, account)


def get_username(account: str, phone_number_id: str) -> dict:
	"""Pull the number's business username from Meta onto its phone row.

	A Graph failure returns the error and leaves the stored value untouched; a
	successful reply with no username clears it (the number has none).
	A pending change shows as PENDING while `username` keeps the live name.
	"""
	base, token = _resolve(account, phone_number_id)
	result = _call("GET", f"{base}/{phone_number_id}/username", token, account)
	if not result["ok"]:
		return result
	d = result["data"]
	username = d.get("username") or ""
	status = "PENDING" if d.get("requested_username") else ((d.get("status") or "").upper() if username else "")
	_save_username(account, phone_number_id, username, status)
	return {
		"ok": True,
		"data": {"username": username, "username_status": status, "requested_username": d.get("requested_username")},
	}


def apply_username_update(value: dict, waba_id: str) -> bool:
	"""Handle a `phone_number_username_update` webhook value. Meta identifies the
	number by display number only, so match digits-only within the WABA's phones.
	Returns True when a phone row was updated."""
	target = re.sub(r"\D", "", value.get("display_phone_number") or "")
	decision = (value.get("decision") or "").upper()
	if not target or decision not in ("APPROVED", "REJECTED") or not waba_id:
		return False
	parents = frappe.get_all(accounts.ACCOUNT_DOCTYPE, filters={"waba_id": waba_id}, pluck="name")
	rows = frappe.get_all(
		accounts.PHONE_CHILD_DOCTYPE,
		filters={"parent": ["in", parents or [""]]},
		fields=["parent", "phone_number_id", "display_phone_number", "username"],
	)
	for row in rows:
		if re.sub(r"\D", "", row.display_phone_number or "") != target:
			continue
		if decision == "APPROVED":
			_save_username(row.parent, row.phone_number_id, value.get("requested_username") or "", "ACTIVE")
		else:  # a rejected change keeps any existing username (and drops its PENDING flag)
			_save_username(row.parent, row.phone_number_id, row.username or "", "ACTIVE" if row.username else "REJECTED")
		return True
	logger.warning("whatsapp username update: no phone row matched for waba %s", waba_id)
	return False


def sync_account_usernames(account: str) -> None:
	"""Background job: refresh the username of every phone on the account.
	Meta may not expose usernames to every account yet, so failures are logged, not raised."""
	for phone_number_id in frappe.get_all(accounts.PHONE_CHILD_DOCTYPE, filters={"parent": account}, pluck="phone_number_id"):
		try:
			result = get_username(account, phone_number_id)
		except Exception:
			frappe.log_error(title=f"WhatsApp username sync failed: {account}")
			continue
		if not result["ok"]:
			logger.info("whatsapp username sync skipped for %s: %s", phone_number_id, result["error"]["code"])
