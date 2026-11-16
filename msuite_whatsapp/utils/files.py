"""File utilities for resolving Frappe paths and detecting MIME types."""

from __future__ import annotations

import csv
import mimetypes
import os
import re
from typing import Any
import frappe
from frappe import _

from msuite_whatsapp.constants import LOCAL_FILE_URL_PREFIXES


def is_local_file_url(url: str | None) -> bool:
	if not url or not isinstance(url, str):
		return False
	return url.strip().startswith(LOCAL_FILE_URL_PREFIXES)


def resolve_frappe_path(file_path: str) -> str:
	if not file_path:
		return ""
	if file_path.startswith("http://") or file_path.startswith("https://"):
		return file_path
	if file_path.startswith("/files/"):
		return frappe.get_site_path("public", file_path.lstrip("/"))
	if file_path.startswith("/private/files/"):
		return frappe.get_site_path("private", "files", file_path.replace("/private/files/", ""))
	if file_path.startswith("/private/"):
		return frappe.get_site_path("private", file_path.replace("/private/", ""))
	if not os.path.isabs(file_path):
		return frappe.get_site_path("public", file_path.lstrip("/"))
	return file_path


def resolve_file_path(file_url: str) -> str:
	from frappe.utils.file_manager import get_files_path

	file_doc = frappe.db.get_value(
		"File",
		{"file_url": file_url},
		["name", "is_private", "file_name"],
		as_dict=True,
	)
	if not file_doc:
		frappe.throw(_("File {0} not found").format(file_url))

	base = get_files_path(is_private=bool(file_doc.is_private))
	return os.path.join(base, file_doc.file_name or os.path.basename(file_url))


def detect_mime(file_path: str) -> str:
	try:
		import magic
		try:
			mime_str = magic.Magic(mime=True).from_file(file_path)
			if mime_str and mime_str != "application/octet-stream":
				return mime_str
		except Exception:
			pass
	except Exception:
		pass

	guessed, _ = mimetypes.guess_type(file_path)
	if guessed:
		return guessed
	return "application/octet-stream"


def read_file_binary(file_path_or_url: str) -> tuple[str, bytes]:
	abs_path = resolve_frappe_path(file_path_or_url)
	if not os.path.exists(abs_path):
		frappe.throw(_("File not found: {0}").format(file_path_or_url))
	with open(abs_path, "rb") as f:
		return abs_path, f.read()


def parse_csv(file_path: str):
	with open(file_path, encoding="utf-8-sig") as f:
		reader = csv.DictReader(f)
		columns = reader.fieldnames or []
		columns = [c.strip() for c in columns]
		rows = []
		for row in reader:
			cleaned = {k.strip(): v.strip() if v else "" for k, v in row.items() if k is not None}
			rows.append(cleaned)
	return rows, columns


def parse_excel(file_path: str):
	try:
		import openpyxl
	except ImportError:
		frappe.throw(_("openpyxl is required for Excel import. Install with: pip install openpyxl"))

	wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
	try:
		ws = wb.active
		columns = []
		rows = []
		for row_idx, raw_row in enumerate(ws.iter_rows()):
			if row_idx == 0:
				columns = [
					str(c.value).strip() if (c and getattr(c, "value", None) is not None) else f"Column_{i + 1}"
					for i, c in enumerate(raw_row)
				]
				continue
			row = {}
			for i, cell in enumerate(raw_row):
				if i < len(columns):
					val = cell.value if cell else ""
					row[columns[i]] = str(val).strip() if val is not None else ""
			if any(v for v in row.values()):
				rows.append(row)
		return rows, columns
	finally:
		wb.close()


def detect_column(columns, hints):
	col_map = {
		col.lower().strip().replace(".", "").replace(" ", "_").replace("-", "_"): col
		for col in columns
		if col
	}
	for hint in hints:
		if hint in col_map:
			return col_map[hint]
	return None
