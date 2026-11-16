"""Central configuration accessor for msuite_whatsapp."""

from __future__ import annotations
from typing import Any
import frappe


def get_central_config(key: str, default: Any = None) -> Any:
	"""Fetch config value from site_config.json / common_site_config.json or fallback to default."""
	val = frappe.conf.get(key)
	if val is not None:
		return val
	return default


def clear_all() -> None:
	pass


def store_snapshot(data: Any = None) -> None:
	pass
