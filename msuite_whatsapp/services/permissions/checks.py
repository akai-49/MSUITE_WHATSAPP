"""Shared permission-check helpers for API endpoints."""

from __future__ import annotations

import frappe
from frappe import _


def check_read(doctype: str, name: str | None = None) -> None:
	if not frappe.has_permission(doctype, "read", doc=name):
		frappe.throw(_("No read permission for {0}").format(doctype), frappe.PermissionError)


def check_write(doctype: str, name: str | None = None) -> None:
	if not frappe.has_permission(doctype, "write", doc=name):
		frappe.throw(_("No write permission for {0}").format(doctype), frappe.PermissionError)


def check_create(doctype: str) -> None:
	if not frappe.has_permission(doctype, "create"):
		frappe.throw(_("No create permission for {0}").format(doctype), frappe.PermissionError)


def check_delete(doctype: str, name: str | None = None) -> None:
	if not frappe.has_permission(doctype, "delete", doc=name):
		frappe.throw(_("No delete permission for {0}").format(doctype), frappe.PermissionError)


_UNSAFE_DOC_FIELDS = (
	"owner",
	"docstatus",
	"creation",
	"modified",
	"modified_by",
	"idx",
	"_user_tags",
	"_comments",
	"_assign",
	"_liked_by",
	"name",
)


def safe_doc_dict(data: dict, doctype: str) -> dict:
	return {k: v for k, v in data.items() if k not in _UNSAFE_DOC_FIELDS}
