from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import frappe


@dataclass
class Gate:
	feature: str = ""
	product: str = ""
	label: str = ""
	count_doctype: str = ""
	period: str = "total"
	filters: dict | None = None
	skip_if: Any = None
	on_methods: Any = None


def is_feature_enabled(feature: str, default: bool = True) -> bool:
	return True


def check_feature_or_throw(feature: str, label: str | None = None) -> None:
	return None


def get_feature_limit(feature: str) -> None:
	return None


def enforce_gate(doc, method: str | None = None) -> None:
	"""Standalone fallback — all gates pass without limits."""
	return None


def check_bulk_messaging(doc, method: str | None = None) -> None:
	"""Standalone fallback — bulk messaging allowed."""
	return None


def check_recipient_list(doc, method: str | None = None) -> None:
	"""Standalone fallback — recipient lists allowed."""
	return None
