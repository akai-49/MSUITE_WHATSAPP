"""
Recipient import service — cross-doctype import, CSV/Excel ingestion,
and export for `WhatsApp Recipient List`.

Extracted from `utils/bulk_messaging.py` (see WHATSAPP_REFACTOR_PLAN.md §5).
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint

from msuite_whatsapp.queries import recipient_repository as recipients
from msuite_whatsapp.utils.files import detect_column, parse_csv, parse_excel, resolve_file_path
from msuite_whatsapp.services.validators.recipient_validator import clean_mobile

# Column names that indicate a mobile number field
_MOBILE_HINTS = {
	"mobile",
	"mobile_no",
	"mobile_number",
	"phone",
	"phone_no",
	"phone_number",
	"whatsapp",
	"whatsapp_number",
	"contact",
	"contact_no",
	"contact_number",
	"cell",
	"tel",
	"number",
}


_NAME_HINTS = (
	"full_name",
	"lead_name",
	"customer_name",
	"contact_name",
	"recipient_name",
	"display_name",
	"name",
	"first_name",
)


def search_importable_doctypes(query: str = "") -> list[str]:
	"""Return the allow-listed DocTypes matching query (see utils/import_guard)."""
	from msuite_whatsapp.utils.import_guard import importable_doctypes

	return importable_doctypes(query)


def get_doctype_import_meta(doctype: str) -> dict:
	"""Inspect a DocType to return metadata for importing recipients:
	- List of fields (with label, fieldname, fieldtype, options)
	- Suggested default mobile_field, name_field, status_field
	- Available status_options (fetched dynamically from Link DocType or Select options)
	"""
	if not doctype or not frappe.db.exists("DocType", doctype):
		frappe.throw(_("DocType {0} does not exist").format(doctype))

	from msuite_whatsapp.utils.import_guard import assert_importable

	assert_importable(doctype)  # allow-list (audit C5); also checks read below
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("No read permission for {0}").format(doctype), frappe.PermissionError)

	meta = frappe.get_meta(doctype)
	excluded_types = {
		"Section Break",
		"Column Break",
		"Tab Break",
		"HTML",
		"Fold",
		"Heading",
		"Table",
		"Button",
		"Password",
	}

	fields = []
	for df in meta.fields:
		if not df.fieldname or df.fieldtype in excluded_types:
			continue
		fields.append(
			{
				"fieldname": df.fieldname,
				"label": df.label or df.fieldname,
				"fieldtype": df.fieldtype,
				"options": df.options,
			}
		)

	for std in ["name", "owner", "creation", "modified"]:
		if not any(f["fieldname"] == std for f in fields):
			fields.append({"fieldname": std, "label": std.title(), "fieldtype": "Data", "options": None})

	# Detect mobile field
	mobile_field = ""
	for f in fields:
		fn = f["fieldname"].lower()
		if any(h in fn for h in ["mobile_no", "mobile_number", "whatsapp_no", "phone", "contact_no", "cell"]):
			mobile_field = f["fieldname"]
			break
	if not mobile_field:
		for f in fields:
			if f["fieldtype"] == "Phone":
				mobile_field = f["fieldname"]
				break

	# Detect name field
	name_field = ""
	for hint in ["lead_name", "full_name", "customer_name", "contact_name", "display_name", "first_name", "title"]:
		match = next((f["fieldname"] for f in fields if f["fieldname"].lower() == hint), None)
		if match:
			name_field = match
			break
	if not name_field:
		for f in fields:
			if any(h in f["fieldname"].lower() for h in ["lead_name", "full_name", "customer_name", "name"]):
				name_field = f["fieldname"]
				break
	if not name_field:
		name_field = "name"

	# Detect status field
	status_field = ""
	for f in fields:
		fn = f["fieldname"].lower()
		if fn == "status" or "status" in fn or fn == "sales_stage":
			status_field = f["fieldname"]
			break

	# Resolve status options
	status_options = []
	if status_field:
		sf_meta = next((f for f in fields if f["fieldname"] == status_field), None)
		if sf_meta:
			if sf_meta["fieldtype"] == "Select" and sf_meta["options"]:
				status_options = [opt.strip() for opt in str(sf_meta["options"]).split("\n") if opt.strip()]
			elif sf_meta["fieldtype"] == "Link" and sf_meta["options"]:
				target_dt = sf_meta["options"]
				if frappe.db.exists("DocType", target_dt):
					try:
						status_options = frappe.get_all(target_dt, pluck="name", order_by="name asc", limit=100)
					except Exception:
						status_options = []

			if not status_options:
				try:
					distinct_vals = frappe.db.sql(
						f"SELECT DISTINCT `{status_field}` FROM `tab{doctype}` WHERE `{status_field}` IS NOT NULL AND `{status_field}` != '' ORDER BY `{status_field}` LIMIT 100",
						pluck=True,
					)
					status_options = [str(v) for v in distinct_vals if v]
				except Exception:
					pass

	return {
		"doctype": doctype,
		"fields": fields,
		"defaults": {
			"mobile_field": mobile_field,
			"name_field": name_field,
			"status_field": status_field,
		},
		"status_options": status_options,
	}


def preview_doctype_recipients(
	doctype: str,
	mobile_field: str,
	name_field: str = "",
	status_values: str | list = None,
	status_field: str = "status",
	filters: str | dict = None,
	limit: int = 5,
) -> dict:
	"""Preview matching records count and sample rows for DocType import."""
	if not doctype or not frappe.db.exists("DocType", doctype):
		frappe.throw(_("DocType {0} does not exist").format(doctype))
	from msuite_whatsapp.utils.import_guard import assert_importable

	assert_importable(doctype)  # allow-list (audit C5); also checks read below
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("No read permission for {0}").format(doctype), frappe.PermissionError)

	if isinstance(status_values, str):
		status_values = json.loads(status_values) if status_values.startswith("[") else ([status_values] if status_values else [])
	if isinstance(filters, str):
		filters = json.loads(filters) if filters else {}

	query_filters = dict(filters or {})

	if status_values and status_field:
		if len(status_values) == 1:
			query_filters[status_field] = status_values[0]
		else:
			query_filters[status_field] = ["in", status_values]

	if mobile_field not in query_filters:
		query_filters[mobile_field] = ["is", "set"]

	total_count = frappe.db.count(doctype, query_filters)

	fields_to_fetch = ["name", mobile_field]
	if name_field and name_field not in fields_to_fetch:
		fields_to_fetch.append(name_field)
	if status_field and status_field not in fields_to_fetch:
		fields_to_fetch.append(status_field)

	sample_docs = frappe.get_list(
		doctype,
		filters=query_filters,
		fields=fields_to_fetch,
		limit=cint(limit) or 5,
		order_by="modified desc",
	)

	sample_rows = []
	for d in sample_docs:
		raw_mobile = str(d.get(mobile_field) or "")
		cleaned, err = clean_mobile(raw_mobile)
		sample_rows.append(
			{
				"doc_name": d.get("name"),
				"mobile_number": cleaned or raw_mobile,
				"recipient_name": str(d.get(name_field) or "") if name_field else "",
				"status": str(d.get(status_field) or "") if status_field else "",
				"is_valid": err is None and bool(cleaned),
				"error": err or "",
			}
		)

	return {
		"total_count": total_count,
		"sample_rows": sample_rows,
	}


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
	"""Fetch normalized, validated recipient rows from a DocType to populate recipient list."""
	if not doctype or not frappe.db.exists("DocType", doctype):
		frappe.throw(_("DocType {0} does not exist").format(doctype))
	from msuite_whatsapp.utils.import_guard import assert_importable

	assert_importable(doctype)  # allow-list (audit C5); also checks read below
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("No read permission for {0}").format(doctype), frappe.PermissionError)

	if isinstance(status_values, str):
		status_values = json.loads(status_values) if status_values.startswith("[") else ([status_values] if status_values else [])
	if isinstance(filters, str):
		filters = json.loads(filters) if filters else {}
	if isinstance(data_fields, str):
		data_fields = json.loads(data_fields) if data_fields else []

	query_filters = dict(filters or {})
	if status_values and status_field:
		if len(status_values) == 1:
			query_filters[status_field] = status_values[0]
		else:
			query_filters[status_field] = ["in", status_values]

	if mobile_field not in query_filters:
		query_filters[mobile_field] = ["is", "set"]

	meta = frappe.get_meta(doctype)
	fields_to_fetch = ["name", mobile_field]
	if name_field and name_field not in fields_to_fetch:
		fields_to_fetch.append(name_field)
	if status_field and status_field not in fields_to_fetch:
		fields_to_fetch.append(status_field)

	auto_vars = [
		"email",
		"email_id",
		"company_name",
		"organization_name",
		"territory",
		"city",
		"country",
		"designation",
	]
	for av in auto_vars:
		if meta.has_field(av) and av not in fields_to_fetch:
			fields_to_fetch.append(av)

	if data_fields:
		for df in data_fields:
			if meta.has_field(df) and df not in fields_to_fetch:
				fields_to_fetch.append(df)

	records = frappe.get_list(
		doctype,
		filters=query_filters,
		fields=fields_to_fetch,
		limit=cint(limit) if limit else None,
		order_by="modified desc",
	)

	recipients_list = []
	seen = set()
	skipped_invalid = 0
	skipped_duplicate = 0

	for rec in records:
		raw_mobile = str(rec.get(mobile_field) or "")
		cleaned, err = clean_mobile(raw_mobile)
		if err or not cleaned:
			skipped_invalid += 1
			continue
		if cleaned in seen:
			skipped_duplicate += 1
			continue
		seen.add(cleaned)

		rec_data = {}
		if status_field and rec.get(status_field):
			rec_data["status"] = str(rec.get(status_field))
		if rec.get("name"):
			rec_data["source_id"] = str(rec.get("name"))
			rec_data["source_doctype"] = doctype

		for f in fields_to_fetch:
			if f not in ("name", mobile_field, name_field) and rec.get(f) is not None:
				val = str(rec.get(f)).strip()
				if val:
					rec_data[f.lower().replace(" ", "_")] = val

		rec_name = str(rec.get(name_field) or "").strip() if name_field else ""

		recipients_list.append(
			{
				"mobile_number": cleaned,
				"recipient_name": rec_name,
				"recipient_data": json.dumps(rec_data) if rec_data else "{}",
				"name": "",
				"local_id": str(rec.get("name") or "") + "_" + cleaned,
			}
		)

	return {
		"recipients": recipients_list,
		"total_fetched": len(records),
		"total_valid": len(recipients_list),
		"skipped_invalid": skipped_invalid,
		"skipped_duplicate": skipped_duplicate,
	}


def import_from_doctype(
	list_name: str,
	doctype: str,
	mobile_field: str,
	name_field=None,
	filters=None,
	limit=None,
	data_fields=None,
) -> int:
	"""Import recipients from a Frappe DocType into a Recipient List."""
	if filters and isinstance(filters, str):
		filters = json.loads(filters)
	if data_fields and isinstance(data_fields, str):
		data_fields = json.loads(data_fields)

	doc = frappe.get_doc("WhatsApp Recipient List", list_name)
	count = doc.import_list_from_doctype(doctype, mobile_field, name_field, filters, limit, data_fields)
	doc.save()
	return count


def parse_recipient_file(file_url: str, list_name: str | None = None) -> dict:
	"""
	Parse a CSV or Excel file and return structured preview data.

	Args:
	    file_url: uploaded file URL
	    list_name: optional -- if given, rows whose number already exists
	               in this list are flagged as duplicates too (useful when
	               previewing an append-mode import).

	Returns dict:
	  mobile_column: auto-detected mobile column name
	  name_column: auto-detected name column (or "")
	  variable_columns: list of remaining columns
	  rows: list of {row_idx, data: {col: val}, is_valid, error}
	  summary: {total, valid, invalid, duplicate}
	"""
	if list_name:
		frappe.has_permission("WhatsApp Recipient List", "read", doc=list_name, throw=True)
	else:
		frappe.has_permission("WhatsApp Recipient List", "read", throw=True)

	file_path = resolve_file_path(file_url)
	ext = file_path.rsplit(".", 1)[-1].lower()

	if ext == "csv":
		rows, columns = parse_csv(file_path)
	elif ext in ("xlsx", "xls"):
		rows, columns = parse_excel(file_path)
	else:
		frappe.throw(_("Unsupported file type: {0}. Use CSV or Excel (.xlsx/.xls).").format(ext))

	if not columns:
		frappe.throw(_("File has no columns."))
	if not rows:
		frappe.throw(_("File has no data rows."))

	mobile_col = detect_column(columns, _MOBILE_HINTS)
	name_col = detect_column(columns, _NAME_HINTS)
	variable_cols = [c for c in columns if c != mobile_col and c != name_col]

	if not mobile_col:
		mobile_col = columns[0]
		variable_cols = [c for c in columns[1:] if c != name_col]

	existing_mobiles = _existing_recipient_mobiles(list_name) if list_name else set()

	result_rows = []
	valid_count = 0
	duplicate_count = 0
	seen_at = {}
	for idx, row in enumerate(rows, start=1):
		mobile_raw = row.get(mobile_col, "")
		mobile, error = clean_mobile(mobile_raw)
		is_duplicate = False

		if mobile and not error:
			if mobile in existing_mobiles:
				error = f"Already in list ({mobile_raw})"
				is_duplicate = True
			elif mobile in seen_at:
				error = f"Duplicate of row {seen_at[mobile]}"
				is_duplicate = True
			else:
				seen_at[mobile] = idx

		is_valid = error is None
		if is_valid:
			valid_count += 1
		if is_duplicate:
			duplicate_count += 1

		result_rows.append(
			{
				"row_idx": idx,
				"data": row,
				"is_valid": is_valid,
				"is_duplicate": is_duplicate,
				"error": error or "",
			}
		)

	return {
		"columns": columns,
		"mobile_column": mobile_col,
		"name_column": name_col or "",
		"variable_columns": variable_cols,
		"rows": result_rows,
		"summary": {
			"total": len(result_rows),
			"valid": valid_count,
			"invalid": len(result_rows) - valid_count,
			"duplicate": duplicate_count,
		},
	}


def _existing_recipient_mobiles(list_name: str) -> set[str]:
	"""Digit-normalized mobile numbers already in a list, for dup checks."""
	cleaned = set()
	for n in recipients.existing_mobiles(list_name):
		mobile, error = clean_mobile(n)
		if mobile and not error:
			cleaned.add(mobile)
	return cleaned


def import_recipients_from_file(
	list_name: str,
	file_url: str,
	mobile_column: str,
	name_column: str = "",
	variable_columns="[]",
	selected_rows="[]",
	append_mode: int = 0,
) -> dict:
	"""
	Import validated rows from a parsed file into a Recipient List.

	Args:
	    list_name: WhatsApp Recipient List name
	    file_url: uploaded file URL
	    mobile_column: column name for mobile numbers
	    name_column: column name for names (optional)
	    variable_columns: JSON list of variable column names
	    selected_rows: JSON list of row indices (1-based) to import
	    append_mode: 1 = append to existing, 0 = replace all

	Returns:
	    dict with imported and skipped counts
	"""
	frappe.has_permission("WhatsApp Recipient List", "write", doc=list_name, throw=True)

	if isinstance(variable_columns, str):
		variable_columns = json.loads(variable_columns)
	if isinstance(selected_rows, str):
		selected_rows = json.loads(selected_rows)

	selected_set = set(int(r) for r in selected_rows)

	file_path = resolve_file_path(file_url)
	ext = file_path.rsplit(".", 1)[-1].lower()
	if ext == "csv":
		rows, _cols = parse_csv(file_path)
	else:
		rows, _cols = parse_excel(file_path)

	doc = frappe.get_doc("WhatsApp Recipient List", list_name)

	seen = set() if not cint(append_mode) else _existing_recipient_mobiles(list_name)
	if not cint(append_mode):
		doc.recipients = []

	imported = 0
	skipped = 0

	for idx, row in enumerate(rows, start=1):
		if idx not in selected_set:
			skipped += 1
			continue

		mobile, error = clean_mobile(row.get(mobile_column, ""))
		if error or mobile in seen:
			skipped += 1
			continue
		seen.add(mobile)

		recipient_data = {}
		for col in variable_columns:
			val = row.get(col)
			if val is not None and str(val).strip():
				recipient_data[col] = str(val).strip()

		doc.append(
			"recipients",
			{
				"mobile_number": mobile,
				"recipient_name": row.get(name_column, "") if name_column else "",
				"recipient_data": json.dumps(recipient_data) if recipient_data else "{}",
			},
		)
		imported += 1

	doc.save()
	return {"imported": imported, "skipped": skipped}


def export_recipients_csv(list_name: str) -> None:
	"""Stream every recipient in a list as a downloadable CSV.

	Writes directly to `frappe.response` (binary file download) — callers
	must be a whitelisted endpoint, not a regular function return.
	"""
	import csv
	import io

	if not frappe.has_permission("WhatsApp Recipient List", "read", doc=list_name):
		frappe.throw(_("No read permission for WhatsApp Recipient List"), frappe.PermissionError)

	rows = recipients.list_recipients(
		list_name,
		fields=["mobile_number", "recipient_name", "recipient_data"],
	)
	data_keys = get_recipient_data_keys(list_name)

	buffer = io.StringIO()
	writer = csv.writer(buffer)
	writer.writerow(["mobile_number", "recipient_name", *data_keys])
	for r in rows:
		row_data = {}
		if r.recipient_data:
			try:
				row_data = json.loads(r.recipient_data)
			except (json.JSONDecodeError, TypeError):
				pass
		writer.writerow([r.mobile_number, r.recipient_name or "", *[row_data.get(k, "") for k in data_keys]])

	frappe.response["type"] = "binary"
	frappe.response["filename"] = f"{list_name}_recipients.csv"
	frappe.response["filecontent"] = buffer.getvalue().encode("utf-8")


def generate_sample_csv_content() -> str:
	"""Generate a standard CSV sample template string for bulk recipient upload."""
	import csv
	import io

	buffer = io.StringIO()
	writer = csv.writer(buffer)
	# Headers: mandatory mobile_number, optional recipient_name, and sample dynamic variables
	writer.writerow(["mobile_number", "recipient_name", "company", "city"])
	writer.writerow(["+919876543210", "John Doe", "Acme Corp", "Mumbai"])
	writer.writerow(["+12025550123", "Jane Smith", "Global Tech", "New York"])
	writer.writerow(["+447911123456", "David Brown", "Apex Ltd", "London"])
	return buffer.getvalue()


def download_sample_csv_template() -> None:
	# perm: static template download
	"""Stream a sample CSV template for recipient bulk upload.

	Writes directly to `frappe.response` (binary file download).
	"""
	csv_text = generate_sample_csv_content()
	frappe.response["type"] = "binary"
	frappe.response["filename"] = "whatsapp_recipients_sample.csv"
	frappe.response["filecontent"] = csv_text.encode("utf-8-sig")


def get_recipient_data_keys(list_name: str) -> list[str]:
	"""
	Extract all unique data keys from recipient_data across a Recipient List.
	Used by the variable mapping UI to show available per-recipient fields.
	"""
	frappe.has_permission("WhatsApp Recipient List", "read", doc=list_name, throw=True)
	keys = []
	for r in recipients.recipient_data_samples(list_name, limit=100):
		if not r.recipient_data:
			continue
		try:
			data = json.loads(r.recipient_data)
			for k in data:
				if k not in keys:
					keys.append(k)
		except (json.JSONDecodeError, TypeError):
			pass
	return keys


# ── File parsing helpers ─────────────────────────────────────────────────
