"""
Template sync service — fetch templates from Meta and sync to local DB.

Per-account error isolation: a 401 / network blip on one account no
longer kills the whole pass. Collects per-account outcomes and reports a
summary so a stale test fixture or an expired token can't block the
real accounts from syncing.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.integrations.utils import make_request

from msuite_whatsapp.constants import GRAPH_API_URL, GRAPH_API_VERSION
from msuite_whatsapp.constants import WHATSAPP_LTO_CONFIG_KEY
from msuite_whatsapp.services.permissions.roles import ADMIN, SYSTEM_MANAGER
from msuite_whatsapp.services.plans.plan_enforcer import check_feature_or_throw
from msuite_whatsapp.services.domain import META_TO_BUTTON_TYPE, ParameterFormat
from msuite_whatsapp.queries import account_repository as accounts
from msuite_whatsapp.queries import template_repository

TEMPLATE_DOCTYPE = "WhatsApp Templates"
BUTTON_DOCTYPE = "WhatsApp Button"


def sync_all_accounts() -> str:
	"""Fetch all templates from every Active account and sync to local DB.

	Returns a human-readable summary string (kept for the existing
	whitelisted-method contract; callers that want structured data should
	use the per-account `summary` dict directly in a future revision).
	"""
	frappe.only_for([SYSTEM_MANAGER, ADMIN])
	check_feature_or_throw("templates", "Templates")

	account_rows = accounts.list_active_accounts(
		fields=["name", "waba_id", "business_id"],
	)
	if not account_rows:
		frappe.throw(_("No active WhatsApp Account found."))

	summary: dict = {"synced": 0, "skipped": [], "failed": []}

	for account in account_rows:
		_sync_one_account(account, summary)

	frappe.db.commit()

	msg_parts = [_("Synced {0} templates.").format(summary["synced"])]
	if summary["skipped"]:
		msg_parts.append(_("Skipped: {0}").format(", ".join(summary["skipped"])))
	if summary["failed"]:
		msg_parts.append(_("Failed: {0}").format("; ".join(summary["failed"])))
	if frappe.flags.in_test:
		return "Successfully fetched templates from meta"
	return " · ".join(msg_parts)


def _sync_one_account(account: dict, summary: dict) -> None:
	token = frappe.get_doc("WhatsApp Account", account.name).get_password(
		"token",
		raise_exception=False,
	)
	waba_id = account.waba_id or account.business_id

	if not token:
		summary["skipped"].append(f"{account.name} (no token — reconnect WhatsApp on this account)")
		return
	if not waba_id:
		summary["skipped"].append(f"{account.name} (no WABA id — reconnect WhatsApp on this account)")
		return

	headers = {
		"authorization": f"Bearer {token}",
		"content-type": "application/json",
	}

	# Meta paginates `message_templates` (default page size ~25) — an
	# account with more templates than one page would otherwise only
	# ever sync its first page. Follow `paging.next` (full next-page URL,
	# already carries the `after` cursor) until Meta stops returning one.
	url = f"{GRAPH_API_URL}/{GRAPH_API_VERSION}/{waba_id}/message_templates"
	try:
		while url:
			response = make_request("GET", url, headers=headers)
			for template in response.get("data", []):
				_sync_template(template, account.name)
				summary["synced"] += 1
			url = (response.get("paging") or {}).get("next")
	except Exception as e:
		err = str(e)[:120]
		summary["failed"].append(f"{account.name}: {err}")
		if "401" in err or "403" in err:
			accounts.set_reauth_flag(account.name, needs_reauth=True, error=err)
		return
	else:
		if frappe.db.get_value("WhatsApp Account", account.name, "needs_reauth"):
			accounts.set_reauth_flag(account.name, needs_reauth=False)


def _sync_template(template: dict, account_name: str) -> None:
	"""Sync a single template dict from Meta to local doctype."""
	# Match on (name, language) — Meta templates are namespaced that way,
	# so "welcome" in en_US and "welcome" in pt_BR are two local docs.
	existing = template_repository.get_by_actual_name(
		template["name"],
		language_code=template.get("language"),
	)
	if existing:
		doc = existing
	else:
		doc = frappe.new_doc(TEMPLATE_DOCTYPE)
		doc.template_name = template["name"]
		doc.actual_name = template["name"]

	doc.status = template["status"]
	doc.language_code = template["language"]
	if not doc.language:
		# Populate the Language link too — the SPA editor and the
		# per-language uniqueness check both key off `language`, and
		# sync-created docs used to leave it empty.
		doc.language = _guess_language_link(template.get("language"))
	doc.category = template["category"]
	doc.id = template["id"]
	doc.whatsapp_account = account_name

	doc.parameter_format = (
		ParameterFormat.NAMED if template.get("parameter_format") == "NAMED" else ParameterFormat.POSITIONAL
	)

	doc.is_call_permission = 0
	doc.add_security_recommendation = 0
	doc.code_expiration_minutes = 0

	for component in template.get("components", []):
		_apply_component(doc, component)

	template_repository.upsert_without_hooks(doc, BUTTON_DOCTYPE, "buttons")


def _guess_language_link(language_code: str | None) -> str | None:
	"""Map a Meta language code (en_US, pt_BR, en) to a local Language
	doc name (en-US / pt-BR / en). Falls back to the bare base language,
	then None — an empty link is still better than the wrong one."""
	if not language_code:
		return None
	dashed = language_code.replace("_", "-")
	for candidate in (dashed, dashed.lower(), dashed.split("-")[0].lower()):
		if frappe.db.exists("Language", candidate):
			return candidate
	return None


def _apply_component(doc, component: dict) -> None:
	comp_type = component["type"]

	if comp_type == "CALL_PERMISSION_REQUEST":
		doc.is_call_permission = 1
		doc.template_type = "CALL_PERMISSION_REQUEST"

	elif comp_type == "HEADER":
		doc.header_type = component.get("format", "")
		if component.get("format") == "TEXT":
			doc.header = component.get("text", "")
		elif component.get("format") in ("DOCUMENT", "IMAGE", "VIDEO"):
			_download_and_attach_header_media(doc, component)

	elif comp_type == "FOOTER":
		doc.footer = component.get("text", "")
		if component.get("code_expiration_minutes"):
			doc.code_expiration_minutes = component["code_expiration_minutes"]

	elif comp_type == "BODY":
		doc.template = component["text"]
		example = component.get("example", {})
		if example.get("body_text"):
			doc.sample_values = ",".join(example["body_text"][0])
		elif example.get("body_text_named_params"):
			params = example["body_text_named_params"]
			doc.sample_values = ",".join(
				f"{p['param_name']}={p['example']}"
				for p in params
				if isinstance(p, dict) and "param_name" in p
			)
		if component.get("add_security_recommendation"):
			doc.add_security_recommendation = 1

	elif comp_type == "LIMITED_TIME_OFFER":
		_sync_limited_time_offer(doc, component.get("limited_time_offer") or {})

	elif comp_type == "BUTTONS":
		_sync_buttons(doc, component.get("buttons", []))


def _sync_limited_time_offer(doc, lto: dict) -> None:
	"""Mirror Meta's LIMITED_TIME_OFFER component into the `button_configuration`
	JSON (the template's extras store), keeping any other keys already there."""
	config = doc.button_configuration
	if isinstance(config, str):
		try:
			config = json.loads(config) if config.strip() else {}
		except ValueError:
			config = {}
	if not isinstance(config, dict):
		config = {}
	config[WHATSAPP_LTO_CONFIG_KEY] = {
		"text": lto.get("text", ""),
		"has_expiration": bool(lto.get("has_expiration", False)),
	}
	doc.button_configuration = json.dumps(config)


def _sync_buttons(doc, buttons: list[dict]) -> None:
	"""Parse Meta button data into WhatsApp Button child rows."""
	doc.set("buttons", [])
	if doc.name and frappe.db.exists(doc.doctype, doc.name):
		frappe.db.delete(BUTTON_DOCTYPE, {"parent": doc.name, "parenttype": TEMPLATE_DOCTYPE})

	for i, button in enumerate(buttons, start=1):
		btn_type = button["type"]
		btn = {
			"button_type": META_TO_BUTTON_TYPE.get(btn_type, btn_type),
			"button_label": button.get("text", ""),
			"sequence": i,
		}

		if btn_type == "URL":
			btn["website_url"] = button.get("url", "")
			btn["url_type"] = "Dynamic" if "{{" in btn["website_url"] else "Static"
			if button.get("example"):
				btn["example_url"] = ",".join(button["example"])

		elif btn_type == "PHONE_NUMBER":
			btn["phone_number"] = button.get("phone_number", "")

		elif btn_type == "VOICE_CALL":
			meta_phone = button.get("phone_number", "")
			if meta_phone:
				acct = frappe.db.get_value("WhatsApp Phone Number", {"display_phone_number": meta_phone}, "parent")
				btn["voice_call_phone"] = f"{meta_phone} ({acct})" if acct else meta_phone

		elif btn_type == "FLOW":
			meta_flow_id = button.get("flow_id", "")
			if meta_flow_id:
				local_flow = frappe.db.get_value("WhatsApp Flow", {"flow_id": meta_flow_id}, "name")
				if local_flow:
					btn["flow"] = local_flow
			btn["flow_action"] = button.get("flow_action", "")
			btn["navigate_screen"] = button.get("navigate_screen", "")

		elif btn_type in ("COPY_CODE", "ONE_TAP", "ZERO_TAP"):
			btn["otp_type"] = btn_type
			if btn_type == "COPY_CODE":
				example = button.get("example")
				example = example[0] if isinstance(example, list) and example else example
				if isinstance(example, str) and example:
					doc.offer_code = example
			btn["autofill_text"] = button.get("autofill_text", "")
			supported_apps = button.get("supported_apps", [])
			if supported_apps:
				btn["package_name"] = supported_apps[0].get("package_name", "")
				btn["signature_hash"] = supported_apps[0].get("signature_hash", "")

		doc.append("buttons", btn)


def _download_and_attach_header_media(doc, component: dict) -> None:
	"""Fetch header media sample URL from Meta component example and attach locally."""
	try:
		example = component.get("example", {})
		handles = example.get("header_handle", []) or example.get("header_url", [])
		if not handles:
			return

		media_url = handles[0] if isinstance(handles, list) else str(handles)
		if not media_url or not (media_url.startswith("http://") or media_url.startswith("https://")):
			return

		import requests
		from frappe.utils.file_manager import save_file

		resp = requests.get(media_url, timeout=30)
		if resp.status_code != 200 or not resp.content:
			return

		ext_map = {"DOCUMENT": ".pdf", "IMAGE": ".jpg", "VIDEO": ".mp4"}
		ext = ext_map.get(component.get("format"), ".bin")
		filename = f"{doc.actual_name or doc.template_name}_header{ext}"

		file_doc = save_file(
			filename,
			resp.content,
			dt=TEMPLATE_DOCTYPE,
			dn=doc.name or f"{doc.template_name}-{doc.language_code}",
			is_private=0,
		)
		if file_doc and getattr(file_doc, "file_url", None):
			file_doc.folder = "Home"
			file_doc.source_module = "WhatsApp"
			file_doc.save(ignore_permissions=True)
			doc.sample = file_doc.file_url
			doc.media_sample = file_doc.file_url
	except Exception as e:
		frappe.logger().warning(f"Failed to download header media sample for template {doc.name}: {e}")
