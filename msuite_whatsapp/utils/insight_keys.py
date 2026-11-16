"""Insight keys and batch delete utilities."""

from __future__ import annotations

import hashlib
from typing import Iterable, Sequence
import frappe

from msuite_whatsapp.constants import INSIGHT_DELETE_BATCH


def make_key(*parts) -> str:
	joined = "|".join(str(p) if p is not None else "" for p in parts)
	return hashlib.sha1(joined.encode()).hexdigest()


def delete_in_batches(doctype: str, names: Sequence[str] | Iterable[str], commit: bool = True) -> int:
	if not names:
		return 0

	name_list = list(names)
	total = 0
	for i in range(0, len(name_list), INSIGHT_DELETE_BATCH):
		chunk = name_list[i : i + INSIGHT_DELETE_BATCH]
		frappe.db.delete(doctype, {"name": ("in", chunk)})
		if commit:
			frappe.db.commit()
		total += len(chunk)
	return total
