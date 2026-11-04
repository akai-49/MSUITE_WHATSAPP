"""
WhatsApp Flow service — lifecycle orchestration (create/publish/sync).

Extracted from the 960-line `whatsapp_flow.py` controller — the single
largest fat-controller finding in the architecture audit. The compiler
(`providers.meta.flow_compiler`) and Meta HTTP calls
(`providers.meta.flow_provider`) are pure/HTTP-only; this module is the
only place that reads/writes the `WhatsApp Flow` document. See
WHATSAPP_REFACTOR_PLAN.md §4/§5/§6/§7.
"""

from __future__ import annotations

import json

import frappe
from frappe import _

from msuite_whatsapp.integrations.meta import flow_compiler, flow_provider

FLOW_DOCTYPE = "WhatsApp Flow"

# Meta's fixed Flow category enum (WhatsApp Manager → Flows → Create flow →
# Categories). Validated server-side since a stale/hand-typed value only
# surfaces as an opaque 400 from Meta at create time otherwise.
VALID_CATEGORIES = {
	"SIGN_UP",
	"SIGN_IN",
	"APPOINTMENT_BOOKING",
	"LEAD_GENERATION",
	"CONTACT_US",
	"CUSTOMER_SUPPORT",
	"SURVEY",
	"SHOPPING",
	"OTHER",
}


def get_categories(doc) -> list[str]:
	"""Parse the `category` field's JSON array, tolerating the old
	single-string value from before categories became multi-select."""
	raw = doc.category
	if not raw:
		return ["OTHER"]
	try:
		parsed = json.loads(raw)
	except (ValueError, TypeError):
		return [raw]
	if isinstance(parsed, list):
		return [c for c in parsed if c] or ["OTHER"]
	return [str(parsed)]


def set_categories(doc, categories: list[str]) -> None:
	doc.category = json.dumps(categories or ["OTHER"])


def validate_categories(doc) -> None:
	invalid = [c for c in get_categories(doc) if c not in VALID_CATEGORIES]
	if invalid:
		frappe.throw(
			_("Invalid Flow categories: {0}. Allowed: {1}").format(
				", ".join(invalid),
				", ".join(sorted(VALID_CATEGORIES)),
			)
		)


def generate_flow_json(doc) -> dict:
	"""Compile this doc's screens/fields into Meta Flow JSON."""
	return flow_compiler.compile_flow(doc.screens, doc.fields, doc.data_api_version)


def create_on_whatsapp(doc) -> None:
	"""Create the flow shell on Meta, then upload the compiled flow.json."""
	if doc.flow_id:
		frappe.throw(_("Flow already exists on WhatsApp. Use update instead."))

	try:
		doc.flow_id = flow_provider.create_flow(doc.whatsapp_account, doc.flow_name, get_categories(doc))
	except Exception as e:
		error_str = str(e)
		if "unique within one WhatsApp business account" in error_str:
			remote_flows = flow_provider.list_remote_flows(doc.whatsapp_account)
			matching = next(
				(
					rf
					for rf in remote_flows
					if (rf.get("name") or "").strip().lower() == doc.flow_name.strip().lower()
				),
				None,
			)
			if matching and matching.get("id"):
				doc.flow_id = str(matching["id"])
				remote_status = (matching.get("status") or "DRAFT").upper()
				doc.status = "Published" if remote_status in ("PUBLISHED", "DEPRECATED") else "Draft"
				doc.flags.ignore_validate = True
				doc.save(ignore_permissions=True)

				if remote_status not in ("PUBLISHED", "DEPRECATED"):
					try:
						upload_flow_json(doc)
					except Exception as upload_err:
						frappe.log_error(title="upload_flow_json fallback error", message=str(upload_err))

				frappe.msgprint(
					_("Linked existing Meta Flow '{0}' (ID: {1}, Status: {2}).").format(
						doc.flow_name, doc.flow_id, doc.status
					),
					indicator="green",
				)
				return
		raise

	doc.flags.ignore_validate = True
	doc.save(ignore_permissions=True)

	upload_flow_json(doc)
	frappe.msgprint(_("Flow created successfully on WhatsApp"), indicator="green")


def upload_flow_json(doc) -> None:
	"""Upload a freshly-compiled flow.json to the existing Meta flow."""
	if not doc.flow_id:
		frappe.throw(_("Flow must be created on WhatsApp first"))
	if doc.status == "Published":
		frappe.msgprint(
			_("Flow is already published on Meta; structure is locked and cannot be re-uploaded."),
			indicator="orange",
		)
		return
	flow_json = generate_flow_json(doc)
	flow_provider.upload_flow_json(doc.whatsapp_account, doc.flow_id, flow_json)
	frappe.msgprint(_("Flow JSON uploaded successfully"))


def publish_flow(doc) -> None:
	if not doc.flow_id:
		frappe.throw(_("Flow must be created on WhatsApp first"))
	if doc.status == "Published":
		frappe.throw(_("Flow is already published"))

	flow_provider.publish_flow(doc.whatsapp_account, doc.flow_id)
	doc.status = "Published"
	doc.save()
	frappe.msgprint(_("Flow published successfully"))


def deprecate_flow(doc) -> None:
	if not doc.flow_id:
		frappe.throw(_("Flow must be created on WhatsApp first"))

	flow_provider.deprecate_flow(doc.whatsapp_account, doc.flow_id)
	doc.status = "Deprecated"
	doc.save()
	frappe.msgprint(_("Flow deprecated successfully"))


def delete_from_whatsapp(doc) -> None:
	if not doc.flow_id:
		frappe.throw(_("Flow does not exist on WhatsApp"))

	flow_provider.delete_flow(doc.whatsapp_account, doc.flow_id)
	doc.flow_id = None
	doc.status = "Draft"
	doc.save()
	frappe.msgprint(_("Flow deleted from WhatsApp"))


def get_flow_preview(doc) -> str:
	if not doc.flow_id:
		frappe.throw(_("Flow must be created on WhatsApp first"))

	preview_url = flow_provider.get_preview_url(doc.whatsapp_account, doc.flow_id)
	if not preview_url:
		frappe.throw(_("Preview URL not available"))

	doc.preview_url = preview_url
	doc.save()
	return preview_url


def send_test(doc, phone_number: str, message: str | None = None) -> None:
	"""Send a test flow message via the inbox pipeline.

	Generates the flow_token ourselves (instead of letting the channel
	handler auto-generate one) and records a `WhatsApp Flow Response` in
	`Sent` status against it *before* sending — Meta's nfm_reply only
	echoes the token back, so without this the reply can't be matched
	to this flow/contact. See `flow_response_service.py`.
	"""
	if not doc.flow_id:
		frappe.throw(_("Flow must be created on WhatsApp first"))

	from msuite_whatsapp.services.flows import flow_response_service

	flow_token = frappe.generate_hash(length=16)
	flow_response_service.mark_sent(doc, phone_number, flow_token)

	from msuite_inbox.inbox.services.outbound import send_to_phone

	send_to_phone(
		phone=phone_number,
		payload={
			"type": "flow",
			"flow": doc.name,
			"flow_cta": doc.flow_cta or "Open Form",
			"text": message or f"Test: {doc.flow_name}",
			"sender_type": "Bot",
			"flow_token": flow_token,
		},
		whatsapp_account=doc.whatsapp_account,
		reference_doctype=doc.doctype,
		reference_name=doc.name,
	)
	frappe.msgprint(_("Test flow sent to {0}").format(phone_number), indicator="green")


def get_flow_status(doc) -> dict:
	"""Fetch status + validation errors from Meta and persist status locally."""
	if not doc.flow_id:
		frappe.throw(_("Flow must be created on WhatsApp first"))

	data = flow_provider.get_flow_status(doc.whatsapp_account, doc.flow_id)

	if data.get("status"):
		doc.status = data["status"].title()
		doc.save()

	validation_errors = data.get("validation_errors", [])
	if validation_errors:
		error_messages = [
			f"- {error.get('error', 'Unknown error')} at {error.get('error_type', 'unknown')}"
			for error in validation_errors
		]
		frappe.msgprint(
			_("Flow Validation Errors:\n{0}").format("\n".join(error_messages)),
			title=_("Validation Errors"),
			indicator="red",
		)
	else:
		frappe.msgprint(
			_("Flow Status: {0}\nJSON Version: {1}").format(
				data.get("status", "Unknown"),
				data.get("json_version", "Unknown"),
			),
			title=_("Flow Status"),
			indicator="green" if data.get("status") == "PUBLISHED" else "blue",
		)

	return data


def sync_from_whatsapp(doc) -> dict:
	"""Pull status/category/JSON from Meta into the local doc."""
	if not doc.flow_id:
		frappe.throw(_("Flow ID is required to sync"))

	data = flow_provider.get_flow_details(doc.whatsapp_account, doc.flow_id)

	if data.get("status"):
		doc.status = data["status"].title()
	if data.get("categories"):
		set_categories(doc, data["categories"])
	if data.get("json_version"):
		doc.data_api_version = data["json_version"]
	if data.get("preview", {}).get("preview_url"):
		doc.preview_url = data["preview"]["preview_url"]

	flow_json = flow_provider.fetch_flow_json(doc.whatsapp_account, doc.flow_id)
	if flow_json:
		doc.flow_json = json.dumps(flow_json, indent=2)

	doc.save()
	frappe.msgprint(_("Flow synced successfully from WhatsApp"), indicator="green")
	return data


def get_whatsapp_flows(whatsapp_account: str) -> list[dict]:
	"""List every Flow on the WABA, flagging which already exist locally."""
	flows = flow_provider.list_remote_flows(whatsapp_account)
	for flow in flows:
		existing = frappe.db.exists(FLOW_DOCTYPE, {"flow_id": flow["id"]})
		flow["exists_locally"] = bool(existing)
		flow["local_name"] = existing if existing else None
	return flows


def import_flow_from_whatsapp(whatsapp_account: str, flow_id: str, flow_name: str | None = None) -> str:
	"""Import a flow from WhatsApp into Frappe."""
	existing = frappe.db.exists(FLOW_DOCTYPE, {"flow_id": flow_id})
	if existing:
		frappe.throw(_("Flow already exists: {0}").format(existing))

	data = flow_provider.get_flow_details(whatsapp_account, flow_id)

	flow_doc = frappe.get_doc(
		{
			"doctype": FLOW_DOCTYPE,
			"flow_name": flow_name or data.get("name", f"Imported Flow {flow_id}"),
			"whatsapp_account": whatsapp_account,
			"flow_id": flow_id,
			"status": data.get("status", "Draft").title(),
			"category": json.dumps(data["categories"]) if data.get("categories") else json.dumps(["OTHER"]),
			"data_api_version": data.get("json_version", "6.0"),
			"preview_url": data.get("preview", {}).get("preview_url", ""),
		}
	)

	flow_json = flow_provider.fetch_flow_json(whatsapp_account, flow_id)
	if flow_json:
		flow_doc.flow_json = json.dumps(flow_json, indent=2)
		_apply_remote_rows(flow_doc, flow_json)

	flow_doc.flags.ignore_validate = True
	flow_doc.insert(ignore_permissions=True)

	frappe.msgprint(_("Flow imported successfully: {0}").format(flow_doc.name), indicator="green")
	return flow_doc.name


def sync_all_flows(whatsapp_account: str) -> dict:
	"""Sync all flows from the WABA — imports new ones, updates existing ones."""
	flows = flow_provider.list_remote_flows(whatsapp_account)
	result = {"imported": 0, "updated": 0, "skipped": 0}

	for flow in flows:
		flow_id = flow.get("id")
		flow_name = flow.get("name")
		existing = frappe.db.exists(FLOW_DOCTYPE, {"flow_id": flow_id})

		try:
			if existing:
				_update_synced_flow(existing, flow, whatsapp_account, flow_id)
				result["updated"] += 1
			else:
				_import_synced_flow(flow_name, flow, whatsapp_account, flow_id)
				result["imported"] += 1
		except Exception as e:
			frappe.log_error(f"Failed to sync flow {flow_id}: {e!s}")
			result["skipped"] += 1

	return result


def _update_synced_flow(existing_name: str, flow: dict, whatsapp_account: str, flow_id: str) -> None:
	flow_doc = frappe.get_doc(FLOW_DOCTYPE, existing_name)
	flow_doc.status = flow.get("status", "Draft").title()
	if flow.get("categories"):
		set_categories(flow_doc, flow["categories"])

	flow_json = flow_provider.fetch_flow_json(whatsapp_account, flow_id)
	if flow_json:
		flow_doc.flow_json = json.dumps(flow_json, indent=2)
		flow_doc.data_api_version = flow_json.get("version", "6.0")
		flow_doc.screens = []
		flow_doc.fields = []
		_apply_remote_rows(flow_doc, flow_json)

	flow_doc.flags.ignore_validate = True
	flow_doc.save(ignore_permissions=True)


def _import_synced_flow(flow_name: str, flow: dict, whatsapp_account: str, flow_id: str) -> None:
	flow_doc = frappe.get_doc(
		{
			"doctype": FLOW_DOCTYPE,
			"flow_name": flow_name or f"Flow {flow_id}",
			"whatsapp_account": whatsapp_account,
			"flow_id": flow_id,
			"status": flow.get("status", "Draft").title(),
			"category": json.dumps(flow["categories"]) if flow.get("categories") else json.dumps(["OTHER"]),
		}
	)

	flow_json = flow_provider.fetch_flow_json(whatsapp_account, flow_id)
	if flow_json:
		flow_doc.flow_json = json.dumps(flow_json, indent=2)
		flow_doc.data_api_version = flow_json.get("version", "6.0")
		_apply_remote_rows(flow_doc, flow_json)

	flow_doc.flags.ignore_validate = True
	flow_doc.insert(ignore_permissions=True)


def _apply_remote_rows(flow_doc, flow_json: dict) -> None:
	"""Parse a remote Flow JSON into screen/field child rows on the doc."""
	screen_rows, field_rows = flow_compiler.parse_flow_json_to_rows(flow_json)
	for row in screen_rows:
		flow_doc.append("screens", row)
	for row in field_rows:
		flow_doc.append("fields", row)
