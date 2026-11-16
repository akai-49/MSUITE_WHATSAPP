"""
WhatsApp Recipient List API — Vue SPA-facing CRUD.

Relocated from `api/v1/whatsapp/crud.py` (see WHATSAPP_REFACTOR_PLAN.md §9).
The dotted path `msuite_whatsapp.api.v1.app.crud.*` is preserved via
a re-export shim in that module since the SPA calls it by that exact path.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint

from msuite_whatsapp.services.permissions.checks import (
	check_create,
	check_delete,
	check_read,
	check_write,
	safe_doc_dict,
)
from msuite_whatsapp.services.validators.recipient_validator import clean_mobile

RECIPIENT_LIST_DOCTYPE = "WhatsApp Recipient List"
RECIPIENT_DOCTYPE = "WhatsApp Recipient"


@frappe.whitelist()
def get_recipient_metrics() -> dict:
	check_read(RECIPIENT_LIST_DOCTYPE)
	total_lists = frappe.db.count(RECIPIENT_LIST_DOCTYPE)
	total_contacts = frappe.db.count(RECIPIENT_DOCTYPE)
	return {"totalLists": total_lists, "totalContacts": total_contacts}


@frappe.whitelist()
def list_recipient_lists(search: str = "", whatsapp_account: str = "", limit: int = 100) -> list:
	check_read(RECIPIENT_LIST_DOCTYPE)
	filters = []
	if search and search.strip():
		filters.append(["list_name", "like", f"%{search.strip()}%"])
	if whatsapp_account and whatsapp_account.strip():
		filters.append(["whatsapp_account", "=", whatsapp_account.strip()])

	rows = frappe.get_all(
		RECIPIENT_LIST_DOCTYPE,
		fields=["name", "list_name", "description", "whatsapp_account", "owner", "creation", "modified"],
		filters=filters,
		order_by="modified desc",
		limit=limit,
	)

	# Per-list recipient counts in one query — the broadcast wizard shows
	# them on the picker cards (it used to read `recipients.length` off
	# rows that never carried child rows, so every card said 0).
	# Raw SQL: get_all refuses string aggregates in SELECT.
	if rows:
		counts = dict(
			frappe.db.sql(
				f"""SELECT parent, COUNT(*) FROM `tab{RECIPIENT_DOCTYPE}`
                WHERE parent IN %(parents)s AND parenttype = 'WhatsApp Recipient List'
                GROUP BY parent""",
				{"parents": [r.name for r in rows]},
			)
		)
		for r in rows:
			r["recipient_count"] = counts.get(r.name, 0)

	return rows


@frappe.whitelist()
def delete_recipient_list(name: str):
	check_delete(RECIPIENT_LIST_DOCTYPE, name)
	frappe.delete_doc(RECIPIENT_LIST_DOCTYPE, name)
	frappe.db.commit()
	return {"status": "success"}


@frappe.whitelist()
def insert_recipient_list(doc: str) -> dict:
	check_create(RECIPIENT_LIST_DOCTYPE)
	data = json.loads(doc or "{}")
	db_doc = frappe.get_doc(safe_doc_dict(data, RECIPIENT_LIST_DOCTYPE))
	db_doc.insert()
	frappe.db.commit()
	return db_doc.as_dict()


@frappe.whitelist()
def get_recipient_list(name: str) -> dict:
	check_read(RECIPIENT_LIST_DOCTYPE, name)
	doc = frappe.get_doc(RECIPIENT_LIST_DOCTYPE, name)
	doc_dict = doc.as_dict()
	doc_dict["recipients"] = [r.as_dict() for r in doc.recipients] if hasattr(doc, "recipients") else []
	return doc_dict


@frappe.whitelist()
def rename_recipient_list(name: str, new_name: str) -> dict:
	check_write(RECIPIENT_LIST_DOCTYPE, name)
	new_name = (new_name or "").strip()
	if not new_name:
		frappe.throw(_("New name is required."))
	if frappe.db.exists(RECIPIENT_LIST_DOCTYPE, new_name):
		frappe.throw(_("A recipient list named {0} already exists.").format(new_name))
	frappe.rename_doc(RECIPIENT_LIST_DOCTYPE, name, new_name)
	frappe.db.set_value(RECIPIENT_LIST_DOCTYPE, new_name, "list_name", new_name)
	frappe.db.commit()
	return {"name": new_name}


@frappe.whitelist()
def bulk_delete_recipient_lists(names) -> dict:
	if isinstance(names, str):
		names = json.loads(names)
	deleted, failed = [], []
	for name in names:
		try:
			check_delete(RECIPIENT_LIST_DOCTYPE, name)
			frappe.delete_doc(RECIPIENT_LIST_DOCTYPE, name, ignore_missing=False)
			deleted.append(name)
		except Exception as e:
			failed.append({"name": name, "error": str(e)[:200]})
	frappe.db.commit()
	return {"deleted": deleted, "failed": failed}


@frappe.whitelist()
def list_recipients(list_name: str, search: str = "", start: int = 0, page_length: int = 50) -> dict:
	"""Paginated, searchable recipients within a single list -- the detail
	page used to dump every row from `get_recipient_list` with no limit."""
	check_read(RECIPIENT_LIST_DOCTYPE, list_name)
	filters = {"parent": list_name}
	or_filters = None
	if search and search.strip():
		like = f"%{search.strip()}%"
		or_filters = [["mobile_number", "like", like], ["recipient_name", "like", like]]

	total = len(
		frappe.get_all(
			RECIPIENT_DOCTYPE,
			filters=filters,
			or_filters=or_filters,
			pluck="name",
		)
	)
	rows = frappe.get_all(
		RECIPIENT_DOCTYPE,
		filters=filters,
		or_filters=or_filters,
		fields=["name", "mobile_number", "recipient_name", "recipient_data"],
		order_by="idx asc",
		start=cint(start),
		page_length=cint(page_length),
	)
	return {"rows": rows, "total": total}


@frappe.whitelist()
def add_recipient(
	list_name: str, mobile_number: str, recipient_name: str | None = None, recipient_data: str | None = None
) -> dict:
	"""Add a single recipient to an existing list."""
	check_write(RECIPIENT_LIST_DOCTYPE, list_name)

	cleaned, error = clean_mobile(mobile_number)
	if error:
		frappe.throw(_("Invalid mobile number: {0}").format(error))
	if frappe.db.exists(RECIPIENT_DOCTYPE, {"parent": list_name, "mobile_number": cleaned}):
		frappe.throw(_("{0} is already in this list.").format(cleaned))

	if recipient_data is not None:
		json.loads(recipient_data or "{}")  # validate shape

	doc = frappe.get_doc(RECIPIENT_LIST_DOCTYPE, list_name)
	doc.append(
		"recipients",
		{
			"mobile_number": cleaned,
			"recipient_name": recipient_name or "",
			"recipient_data": recipient_data or "{}",
		},
	)
	doc.save()
	return {"name": doc.recipients[-1].name, "mobile_number": cleaned}


@frappe.whitelist()
def update_recipient(
	list_name: str,
	recipient: str,
	mobile_number: str | None = None,
	recipient_name: str | None = None,
	recipient_data: str | None = None,
) -> dict:
	"""Edit a single recipient row in place."""
	check_write(RECIPIENT_LIST_DOCTYPE, list_name)
	if not frappe.db.exists(RECIPIENT_DOCTYPE, {"name": recipient, "parent": list_name}):
		frappe.throw(_("Recipient not found in this list."))

	values = {}
	if mobile_number is not None:
		cleaned, error = clean_mobile(mobile_number)
		if error:
			frappe.throw(_("Invalid mobile number: {0}").format(error))
		duplicate = frappe.db.exists(
			RECIPIENT_DOCTYPE,
			{
				"parent": list_name,
				"mobile_number": cleaned,
				"name": ("!=", recipient),
			},
		)
		if duplicate:
			frappe.throw(_("{0} is already used by another recipient in this list.").format(cleaned))
		values["mobile_number"] = cleaned
	if recipient_name is not None:
		values["recipient_name"] = recipient_name
	if recipient_data is not None:
		json.loads(recipient_data or "{}")  # validate shape
		values["recipient_data"] = recipient_data

	if values:
		frappe.db.set_value(RECIPIENT_DOCTYPE, recipient, values, update_modified=False)
		frappe.db.commit()
	return {"name": recipient, **values}


@frappe.whitelist()
def delete_recipients(list_name: str, names) -> dict:
	"""Bulk-delete one or more recipient rows from a list."""
	check_write(RECIPIENT_LIST_DOCTYPE, list_name)
	if isinstance(names, str):
		names = json.loads(names)
	if not names:
		return {"deleted": 0}
	# Count what actually matches — `len(names)` over-reported when the
	# client sent rows that weren't (or no longer were) in this list.
	matching = frappe.get_all(
		RECIPIENT_DOCTYPE,
		filters={"name": ("in", names), "parent": list_name},
		pluck="name",
	)
	if matching:
		frappe.db.delete(RECIPIENT_DOCTYPE, {"name": ("in", matching)})
	frappe.db.commit()
	return {"deleted": len(matching)}


@frappe.whitelist()
def search_importable_doctypes(query: str = "") -> list[str]:
	check_read(RECIPIENT_LIST_DOCTYPE)
	from msuite_whatsapp.services.bulk import recipient_import_service
	return recipient_import_service.search_importable_doctypes(query=query)


@frappe.whitelist()
def get_doctype_import_meta(doctype: str) -> dict:
	check_read(RECIPIENT_LIST_DOCTYPE)
	from msuite_whatsapp.services.bulk import recipient_import_service
	return recipient_import_service.get_doctype_import_meta(doctype)


@frappe.whitelist()
def preview_doctype_recipients(
	doctype: str,
	mobile_field: str,
	name_field: str = "",
	status_values: str | list = None,
	status_field: str = "status",
	filters: str | dict = None,
	limit: int = 5,
) -> dict:
	check_read(RECIPIENT_LIST_DOCTYPE)
	from msuite_whatsapp.services.bulk import recipient_import_service
	return recipient_import_service.preview_doctype_recipients(
		doctype=doctype,
		mobile_field=mobile_field,
		name_field=name_field,
		status_values=status_values,
		status_field=status_field,
		filters=filters,
		limit=limit,
	)


@frappe.whitelist()
def fetch_doctype_recipients(
	doctype: str,
	mobile_field: str,
	name_field: str = "",
	status_values: str | list = None,
	status_field: str = "status",
	filters: str | dict = None,
	limit: int = 0,
	data_fields: str | list = None,
) -> dict:
	check_read(RECIPIENT_LIST_DOCTYPE)
	from msuite_whatsapp.services.bulk import recipient_import_service
	return recipient_import_service.fetch_doctype_recipients(
		doctype=doctype,
		mobile_field=mobile_field,
		name_field=name_field,
		status_values=status_values,
		status_field=status_field,
		filters=filters,
		limit=limit,
		data_fields=data_fields,
	)

