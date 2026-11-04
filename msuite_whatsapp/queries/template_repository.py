"""
WhatsApp Templates repository.

DB-only access for template lookups and upserts. Services call this
module instead of touching `frappe.db` / `frappe.get_doc` directly so
template persistence has one implementation, including the
"upsert without triggering hooks" pattern needed by the Meta sync path
(syncing a template must not re-trigger `after_insert` → `push_to_meta`).
"""

from __future__ import annotations

import frappe

TEMPLATE_DOCTYPE = "WhatsApp Templates"
BUTTON_DOCTYPE = "WhatsApp Button"


def get_by_actual_name(actual_name: str, language_code: str | None = None):
	"""Return the local template doc for a given Meta template name, or None.

	Meta namespaces templates by (name, language) — the same name exists
	once per language. Matching on name alone made a multi-language
	template collapse onto one local doc that flip-flopped its
	language/status on every sync, so pass `language_code` whenever the
	caller has it.
	"""
	filters = {"actual_name": actual_name}
	if language_code:
		filters["language_code"] = language_code
	if frappe.db.exists(TEMPLATE_DOCTYPE, filters):
		return frappe.get_doc(TEMPLATE_DOCTYPE, filters)
	return None


def exists_for_language(template_name: str, language: str, exclude_name: str | None = None) -> bool:
	filters = {"template_name": template_name, "language": language}
	if exclude_name:
		filters["name"] = ("!=", exclude_name)
	return bool(frappe.db.exists(TEMPLATE_DOCTYPE, filters))


def upsert_without_hooks(doc, child_doctype: str = BUTTON_DOCTYPE, child_field: str = "buttons") -> None:
	"""Insert or update a parent document and its children without firing
	document hooks (`validate`, `after_insert`, etc.) — used exclusively by
	the Meta → local sync path so syncing never re-triggers an outbound
	push back to Meta.

	Argument order (doc, child_doctype, child_field) matches the original
	`template_sync.py::_upsert_doc_without_hooks` signature for backward
	compatibility with existing callers/tests.
	"""
	if frappe.db.exists(doc.doctype, doc.name):
		doc.db_update()
		frappe.db.delete(child_doctype, {"parent": doc.name, "parenttype": doc.doctype})
	else:
		doc.db_insert()
	for d in doc.get(child_field):
		d.parent = doc.name
		d.parenttype = doc.doctype
		d.parentfield = child_field
		d.db_insert()


def get_send_fields(template_name: str) -> dict | None:
	"""Lightweight field fetch for the send path (avoids a full doc load)."""
	return frappe.db.get_value(TEMPLATE_DOCTYPE, template_name, "*", as_dict=True)
