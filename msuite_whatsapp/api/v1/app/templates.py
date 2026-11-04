"""
WhatsApp Templates API — Vue SPA-facing CRUD.

Relocated from `api/v1/whatsapp/crud.py` (see WHATSAPP_REFACTOR_PLAN.md §9).
The dotted path `msuite_whatsapp.api.v1.app.crud.*` is preserved via
a re-export shim in that module since the SPA calls it by that exact path.
"""

import json
import re

import frappe
from frappe.utils import cint

from msuite_core.services.permissions.checks import (
	check_create,
	check_delete,
	check_read,
	check_write,
	safe_doc_dict,
)

from msuite_whatsapp.constants import WHATSAPP_LTO_TEXT_MAX
from msuite_whatsapp.services.validators.template_validator import get_send_requirements

TEMPLATE_DOCTYPE = "WhatsApp Templates"
_TEMPLATE_SORT_FIELDS = {"template_name", "status", "category", "language", "modified", "creation"}


@frappe.whitelist()
def get_template_metrics() -> dict:
	check_read(TEMPLATE_DOCTYPE)

	total = frappe.db.count(TEMPLATE_DOCTYPE)
	approved = frappe.db.count(TEMPLATE_DOCTYPE, {"status": "APPROVED"})
	pending = frappe.db.count(TEMPLATE_DOCTYPE, {"status": "PENDING"})
	rejected = frappe.db.count(TEMPLATE_DOCTYPE, {"status": "REJECTED"})
	draft = frappe.db.count(TEMPLATE_DOCTYPE, {"status": "Draft"})

	return {
		"total": total,
		"approved": approved,
		"pending": pending,
		"rejected": rejected,
		"draft": draft,
	}


@frappe.whitelist()
def list_templates(
	filters: str = "[]",
	search: str = "",
	limit: int = 100,
	limit_start: int = 0,
	sort_by: str = "modified",
	sort_order: str = "desc",
) -> dict:
	check_read(TEMPLATE_DOCTYPE)

	parsed_filters = json.loads(filters or "[]")

	if search and search.strip():
		parsed_filters.append(["template_name", "like", f"%{search.strip()}%"])

	if sort_by not in _TEMPLATE_SORT_FIELDS:
		sort_by = "modified"
	sort_order = "asc" if sort_order.lower() == "asc" else "desc"

	fields = [
		"name",
		"template_name",
		"status",
		"category",
		"language",
		"header_type",
		"owner",
		"modified",
		"total_sent",
		"total_delivered",
		"total_read",
	]
	rows = frappe.get_all(
		TEMPLATE_DOCTYPE,
		fields=fields,
		filters=parsed_filters,
		order_by=f"{sort_by} {sort_order}",
		limit=cint(limit),
		limit_start=cint(limit_start),
	)
	total = frappe.db.count(TEMPLATE_DOCTYPE, parsed_filters)
	return {"rows": rows, "total": total}


@frappe.whitelist()
def get_whatsapp_template(name: str) -> dict:
	check_read(TEMPLATE_DOCTYPE, name)
	doc = frappe.get_doc(TEMPLATE_DOCTYPE, name)
	doc_dict = doc.as_dict()
	doc_dict["buttons"] = [b.as_dict() for b in doc.buttons]
	return doc_dict


@frappe.whitelist()
def get_whatsapp_template_limits() -> dict:
	"""Return template-editor limits so the UI does not hardcode them.

	Returns: `{"lto_text_max": int}` (WHATSAPP_LTO_TEXT_MAX).
	Raises: PermissionError without read access to WhatsApp Templates.
	"""
	check_read(TEMPLATE_DOCTYPE)
	return {"lto_text_max": WHATSAPP_LTO_TEXT_MAX}


@frappe.whitelist()
def get_template_send_requirements(template: str) -> dict:
	"""Tell the UI which offer values a send of `template` needs.

	Args: template: WhatsApp Templates doc name.
	Returns: see `template_validator.get_send_requirements`.
	Raises: PermissionError without read access; DoesNotExistError if missing.
	"""
	check_read(TEMPLATE_DOCTYPE, template)
	return get_send_requirements(frappe.get_doc(TEMPLATE_DOCTYPE, template))


def _sanitize_payload_buttons(payload: dict):
	if "buttons" in payload and isinstance(payload["buttons"], list):
		for btn in payload["buttons"]:
			if isinstance(btn, dict) and btn.get("button_type") == "Flow":
				flow_val = btn.get("flow")
				if flow_val and not frappe.db.exists("WhatsApp Flow", flow_val):
					matched = frappe.db.get_value(
						"WhatsApp Flow", {"flow_id": flow_val}, "name"
					) or frappe.db.get_value(
						"WhatsApp Flow", {"flow_name": flow_val}, "name"
					)
					if matched:
						btn["flow"] = matched
					else:
						btn["flow"] = None


@frappe.whitelist()
def save_whatsapp_template(doc: str) -> dict:
	data = json.loads(doc or "{}")
	name = data.get("name")

	if name:
		check_write(TEMPLATE_DOCTYPE, name)
		db_doc = frappe.get_doc(TEMPLATE_DOCTYPE, name)
		payload = safe_doc_dict(data, TEMPLATE_DOCTYPE)
		# Status is owned by Meta (webhook / push results) once a template
		# exists. The editor used to send status="Draft" on every save,
		# silently downgrading APPROVED templates locally.
		payload.pop("status", None)
		payload.pop("id", None)
		payload.pop("rejection_reason", None)
		_sanitize_payload_buttons(payload)
		db_doc.update(payload)
		db_doc.save()
		frappe.db.commit()
		return db_doc.as_dict()
	else:
		check_create(TEMPLATE_DOCTYPE)
		payload = safe_doc_dict(data, TEMPLATE_DOCTYPE)
		_sanitize_payload_buttons(payload)
		db_doc = frappe.get_doc(payload)
		db_doc.insert()
		frappe.db.commit()
		return db_doc.as_dict()


@frappe.whitelist()
def delete_whatsapp_template(name: str, delete_from_whatsapp: int = 1):
	check_delete(TEMPLATE_DOCTYPE, name)
	from frappe.utils import cint

	delete_from_whatsapp = cint(delete_from_whatsapp)

	doc = frappe.get_doc(TEMPLATE_DOCTYPE, name)
	if not delete_from_whatsapp:
		doc.flags.delete_from_msuite_only = True
	doc.delete(force=True)

	frappe.db.commit()
	return {"status": "success"}


@frappe.whitelist()
def bulk_delete_templates(names: str, delete_from_whatsapp: int = 1) -> dict:
	"""Delete multiple templates. Reports failures instead of silently
	no-oping on a name that doesn't exist (frappe.delete_doc defaults to
	ignore_missing=True)."""
	from frappe.utils import cint

	delete_from_whatsapp = cint(delete_from_whatsapp)
	name_list = json.loads(names) if isinstance(names, str) else (names or [])
	deleted, failed = [], []
	for name in name_list:
		if not frappe.has_permission(TEMPLATE_DOCTYPE, "delete", doc=name):
			failed.append(name)
			continue
		try:
			doc = frappe.get_doc(TEMPLATE_DOCTYPE, name)
			if not delete_from_whatsapp:
				doc.flags.delete_from_msuite_only = True
			doc.delete(force=True)
			deleted.append(name)
		except Exception as e:
			frappe.log_error(title="bulk_delete_templates", message=str(e))
			failed.append(name)
	frappe.db.commit()
	return {"deleted": deleted, "failed": failed}


@frappe.whitelist()
def duplicate_template(name: str) -> dict:
	"""Clone a template as a new Draft -- same body/header/footer/buttons,
	fresh name, no Meta id (so it never collides with the original on push).

	Uses frappe.copy_doc rather than hand-listing fields so the legacy
	flat button fields and the buttons child table both come along
	faithfully, the same way Desk's own "Duplicate" would.
	"""
	check_read(TEMPLATE_DOCTYPE, name)
	check_create(TEMPLATE_DOCTYPE)

	source = frappe.get_doc(TEMPLATE_DOCTYPE, name)
	new_doc = frappe.copy_doc(source)

	base_name = re.sub(r"_copy(_\d+)?$", "", source.template_name)
	candidate = f"{base_name}_copy"
	suffix = 1
	while frappe.db.exists(TEMPLATE_DOCTYPE, f"{candidate}-{source.language_code}"):
		suffix += 1
		candidate = f"{base_name}_copy_{suffix}"

	new_doc.template_name = candidate
	new_doc.status = "Draft"
	new_doc.id = ""
	new_doc.actual_name = ""
	new_doc.rejection_reason = ""
	new_doc.total_sent = 0
	new_doc.total_delivered = 0
	new_doc.total_read = 0
	new_doc.insert()
	frappe.db.commit()
	return {"name": new_doc.name}


@frappe.whitelist()
def check_template_duplicate(template_name: str, language: str) -> int:
	check_read(TEMPLATE_DOCTYPE)
	lang_code = language.replace("-", "_")
	target_name = f"{template_name}-{lang_code}"
	return frappe.db.exists(TEMPLATE_DOCTYPE, target_name)
