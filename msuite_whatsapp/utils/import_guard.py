"""Allowed import DocTypes guard."""

from __future__ import annotations

import frappe
from frappe import _

DEFAULT_IMPORT_DOCTYPES = ("CRM Lead", "CRM Deal", "Contact", "Customer", "Lead")


def allowed_import_doctypes() -> list[str]:
	if frappe.db.exists("DocType", "MSuite Allowed Import DocType") and frappe.db.exists("DocType", "MSuite Settings"):
		try:
			configured = frappe.get_all(
				"MSuite Allowed Import DocType",
				filters={"parenttype": "MSuite Settings", "parentfield": "allowed_import_doctypes"},
				pluck="ref_doctype",
				order_by="idx asc",
			)
			if configured:
				return [d for d in dict.fromkeys(configured) if frappe.db.exists("DocType", d)]
		except Exception:
			pass
	return [d for d in DEFAULT_IMPORT_DOCTYPES if frappe.db.exists("DocType", d)]


def importable_doctypes(query: str = "") -> list[str]:
	q = (query or "").strip().lower()
	return [
		d
		for d in allowed_import_doctypes()
		if (not q or q in d.lower()) and frappe.has_permission(d, "read")
	]


def assert_importable(doctype: str) -> None:
	if not doctype or doctype not in allowed_import_doctypes():
		frappe.throw(
			_("Importing from {0} is not allowed.").format(doctype or "-"),
			frappe.PermissionError,
		)
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("No read permission for {0}").format(doctype), frappe.PermissionError)
