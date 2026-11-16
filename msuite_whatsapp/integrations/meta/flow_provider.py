"""
WhatsApp Flow provider — all Meta Graph API calls for Flow lifecycle
management (create, upload JSON, publish, deprecate, delete, preview,
status, sync). No Frappe Document access beyond reading account
credentials — `services/flow_service.py` orchestrates and owns doc state.
"""

from __future__ import annotations

import json

import frappe
import requests
from frappe import _

from msuite_whatsapp.constants import GRAPH_API_URL, GRAPH_API_VERSION
from msuite_whatsapp.queries import account_repository as accounts


def _credentials(whatsapp_account: str) -> tuple[str, str, str, str]:
	"""Returns (base_url, version, waba_id, token).

	Flows are owned by the WhatsApp Business Account (WABA), not the Meta
	Business Manager account — Meta's Flows API is `POST /{WABA-ID}/flows`
	and `GET /{WABA-ID}/flows`. This used to return `business_id`, which
	fails on every real WABA with:
	  "Object with ID '<business_id>' does not exist, cannot be loaded
	   due to missing permissions, or does not support this operation"
	  (Graph error code 100 / subcode 33)
	— confirmed against a live account: the identical request 400s with
	`business_id` and returns `{"success": true, "id": ...}` with
	`waba_id`. Falls back to `business_id` only if `waba_id` was never
	captured on the account, matching the fallback already used in
	`template_provider.py`.
	"""
	account = accounts.get_account_doc(whatsapp_account)
	token = account.get_password("token")
	waba_id = account.waba_id or account.business_id
	return GRAPH_API_URL, GRAPH_API_VERSION, waba_id, token


def _request(method: str, url: str, action: str, **kwargs) -> requests.Response:
	"""Shared HTTP call + error handling for every Graph API call in this
	module. Surfaces Meta's actual `error.message` / `error_user_msg`
	instead of a bare HTTP status line — several of these calls used to
	swallow the response body behind a generic "400 Client Error", which
	makes a real Meta rejection (bad category, invalid token, disabled
	permission, ...) indistinguishable from a network blip."""
	try:
		response = requests.request(method, url, **kwargs)
	except requests.exceptions.RequestException as e:
		frappe.throw(_("Failed to {0}: {1}").format(action, str(e)))
		raise  # frappe.throw always raises; this just satisfies the type checker

	if response.status_code >= 400:
		try:
			error = response.json().get("error", {})
		except ValueError:
			error = {}
		msg = error.get("error_user_msg") or error.get("message") or response.text
		frappe.throw(_("Failed to {0}: {1}").format(action, msg))

	return response


def create_flow(whatsapp_account: str, flow_name: str, categories: list[str]) -> str:
	"""Create a new Flow shell on Meta. Returns the Meta flow_id."""
	base_url, version, waba_id, token = _credentials(whatsapp_account)
	url = f"{base_url}/{version}/{waba_id}/flows"
	payload = {"name": flow_name, "categories": categories}
	headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

	response = _request("POST", url, "create flow", headers=headers, json=payload)
	return response.json().get("id")


def upload_flow_json(whatsapp_account: str, flow_id: str, flow_json: dict) -> None:
	"""Upload the compiled flow.json asset to an existing Meta flow."""
	base_url, version, _waba_id, token = _credentials(whatsapp_account)
	url = f"{base_url}/{version}/{flow_id}/assets"
	headers = {"Authorization": f"Bearer {token}"}
	files = {
		"file": ("flow.json", json.dumps(flow_json), "application/json"),
		"name": (None, "flow.json"),
		"asset_type": (None, "FLOW_JSON"),
	}

	response = _request("POST", url, "upload flow JSON", headers=headers, files=files)

	# A 200 here only means the asset was *accepted for validation* —
	# Meta still returns per-component validation_errors inside a 200
	# body. Surface those now instead of letting Publish fail later with
	# no context linking back to which field/screen is wrong.
	try:
		data = response.json()
	except ValueError:
		data = {}
	validation_errors = data.get("validation_errors") or []
	if validation_errors:
		messages = [
			f"- {e.get('error', 'Unknown error')} ({e.get('error_type', 'unknown')})"
			for e in validation_errors
		]
		frappe.throw(
			_("Flow JSON has validation errors:\n{0}").format("\n".join(messages)),
			title=_("Flow Validation Failed"),
		)


def publish_flow(whatsapp_account: str, flow_id: str) -> None:
	base_url, version, _waba_id, token = _credentials(whatsapp_account)
	url = f"{base_url}/{version}/{flow_id}/publish"
	headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
	_request("POST", url, "publish flow", headers=headers)


def deprecate_flow(whatsapp_account: str, flow_id: str) -> None:
	base_url, version, _waba_id, token = _credentials(whatsapp_account)
	url = f"{base_url}/{version}/{flow_id}/deprecate"
	headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
	_request("POST", url, "deprecate flow", headers=headers)


def delete_flow(whatsapp_account: str, flow_id: str) -> None:
	"""Delete a Flow from Meta. Only DRAFT flows can be deleted — a
	Published flow must be deprecated instead (Meta returns a clear error
	in that case, now surfaced verbatim via `_request`)."""
	base_url, version, _waba_id, token = _credentials(whatsapp_account)
	url = f"{base_url}/{version}/{flow_id}"
	headers = {"Authorization": f"Bearer {token}"}
	_request("DELETE", url, "delete flow", headers=headers)


def get_preview_url(whatsapp_account: str, flow_id: str) -> str | None:
	base_url, version, _waba_id, token = _credentials(whatsapp_account)
	url = f"{base_url}/{version}/{flow_id}?fields=preview.invalidate(false)"
	headers = {"Authorization": f"Bearer {token}"}

	response = _request("GET", url, "get preview", headers=headers)
	return response.json().get("preview", {}).get("preview_url")


def get_flow_status(whatsapp_account: str, flow_id: str) -> dict:
	"""Fetch status + validation errors from Meta for an existing flow."""
	base_url, version, _waba_id, token = _credentials(whatsapp_account)
	fields = "id,name,status,categories,validation_errors,json_version,data_api_version,data_channel_uri,preview,whatsapp_business_account"
	url = f"{base_url}/{version}/{flow_id}?fields={fields}"
	headers = {"Authorization": f"Bearer {token}"}

	response = _request("GET", url, "get flow status", headers=headers)
	return response.json()


def get_flow_details(whatsapp_account: str, flow_id: str) -> dict:
	"""Lighter status fetch used by the sync path (no validation_errors)."""
	base_url, version, _waba_id, token = _credentials(whatsapp_account)
	fields = "id,name,status,categories,json_version,preview"
	url = f"{base_url}/{version}/{flow_id}?fields={fields}"
	headers = {"Authorization": f"Bearer {token}"}

	response = _request("GET", url, "sync flow", headers=headers)
	return response.json()


def fetch_flow_json(whatsapp_account: str, flow_id: str) -> dict | None:
	"""Download the `flow.json` asset from an existing Meta flow, if present.

	Best-effort: unlike the other calls in this module, a failure here
	doesn't block the caller (sync should still update status/category
	even if the JSON asset can't be fetched), so it logs and returns None
	rather than throwing.
	"""
	base_url, version, _waba_id, token = _credentials(whatsapp_account)
	url = f"{base_url}/{version}/{flow_id}/assets"
	headers = {"Authorization": f"Bearer {token}"}

	try:
		response = requests.get(url, headers=headers)
		response.raise_for_status()
		data = response.json()
		for asset in data.get("data", []):
			if asset.get("name") == "flow.json":
				download_url = asset.get("download_url")
				if download_url:
					asset_response = requests.get(download_url, headers=headers)
					if asset_response.status_code == 200:
						return asset_response.json()
		return None
	except Exception as e:
		frappe.log_error(title="WhatsApp Flow fetch_flow_json", message=str(e))
		return None


def list_remote_flows(whatsapp_account: str) -> list[dict]:
	"""List every Flow on the WABA (not just ones imported locally)."""
	base_url, version, waba_id, token = _credentials(whatsapp_account)
	url = f"{base_url}/{version}/{waba_id}/flows?fields=id,name,status,categories"
	headers = {"Authorization": f"Bearer {token}"}

	response = _request("GET", url, "fetch flows", headers=headers)
	return response.json().get("data", [])
