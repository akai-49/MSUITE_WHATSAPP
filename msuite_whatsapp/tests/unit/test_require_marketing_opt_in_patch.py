"""Migrate patch: default WhatsApp Settings.require_marketing_opt_in to 1 without overwriting an admin's choice."""

import unittest
from unittest.mock import patch

from msuite_whatsapp.patches import default_require_marketing_opt_in as patch_mod

DB = "frappe.db"


class TestDefaultRequireMarketingOptIn(unittest.TestCase):
	def test_row_missing_sets_one(self):
		with patch(f"{DB}.sql", return_value=[]), patch(f"{DB}.set_single_value") as setter:
			patch_mod.execute()
		setter.assert_called_once_with("WhatsApp Settings", "require_marketing_opt_in", 1)

	def test_explicit_zero_left_alone(self):
		with patch(f"{DB}.sql", return_value=[("0",)]), patch(f"{DB}.set_single_value") as setter:
			patch_mod.execute()
		setter.assert_not_called()

	def test_existing_one_left_alone(self):
		with patch(f"{DB}.sql", return_value=[("1",)]), patch(f"{DB}.set_single_value") as setter:
			patch_mod.execute()
		setter.assert_not_called()
