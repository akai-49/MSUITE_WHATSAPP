"""
Tests for WhatsApp Analytics Account Resolution (Numeric & Fuzzy matching)
and Meta API failure fallback to local DB.
"""

import unittest
from unittest.mock import MagicMock, patch
import frappe

from msuite_whatsapp.api.v1.app.analytics_query import (
	_fetch_accounts_list,
	_resolve_account_name,
	get_messaging_summary,
	get_whatsapp_account_insights,
)


class TestAnalyticsAccountResolution(unittest.TestCase):
	def setUp(self):
		frappe.local.db = MagicMock()
		frappe.local.db.exists.return_value = False
		frappe.local.request = MagicMock()
		frappe.local.form_dict = {}
		self._orig_get_system_settings = getattr(frappe, "get_system_settings", None)
		self._orig_log_error = getattr(frappe, "log_error", None)
		frappe.get_system_settings = MagicMock(return_value="Asia/Kolkata")
		frappe.log_error = MagicMock()

	def tearDown(self):
		if hasattr(frappe.local, "db"):
			del frappe.local.db
		if self._orig_get_system_settings is not None:
			frappe.get_system_settings = self._orig_get_system_settings
		if self._orig_log_error is not None:
			frappe.log_error = self._orig_log_error

	@patch("msuite_whatsapp.api.v1.app.analytics_query.get_display_phone_number", return_value="123")
	@patch("frappe.get_list")
	def test_fetch_accounts_list(self, mock_get_list, _display):
		"""_fetch_accounts_list returns accounts with the default phone's number filled in."""
		mock_get_list.return_value = [{"name": "Acc_One", "account_name": "Acc One"}]
		accounts = _fetch_accounts_list()
		self.assertEqual(len(accounts), 1)
		self.assertEqual(accounts[0]["phone_number"], "123")
		self.assertEqual(accounts[0]["display_phone_number"], "123")

	def test_numeric_index_resolution(self):
		"""Numeric string or integer is resolved as 1-based index."""
		mock_accounts = [
			{"name": "Acc_One", "account_name": "Acc One", "phone_number": "", "display_phone_number": ""},
			{"name": "Acc_Two", "account_name": "Acc Two", "phone_number": "+1234567890", "display_phone_number": "+1234567890"},
			{"name": "Acc_Three", "account_name": "Demo Business", "phone_number": "+91 98765 43210", "display_phone_number": "+91 98765 43210"},
		]

		# 1-based index as string
		name, _ = _resolve_account_name("1", mock_accounts)
		self.assertEqual(name, "Acc_One")

		name, _ = _resolve_account_name("2", mock_accounts)
		self.assertEqual(name, "Acc_Two")

		name, _ = _resolve_account_name("3", mock_accounts)
		self.assertEqual(name, "Acc_Three")

		# 1-based index as integer
		name, _ = _resolve_account_name(2, mock_accounts)
		self.assertEqual(name, "Acc_Two")

	def test_fuzzy_and_substring_resolution(self):
		"""Case-insensitive and substring match on account_name and phone_number."""
		mock_accounts = [
			{"name": "Acc_One", "account_name": "Test Alpha", "phone_number": "", "display_phone_number": ""},
			{"name": "Acc_Demo", "account_name": "Demo Business", "phone_number": "+91 98765 43210", "display_phone_number": "+91 98765 43210"},
		]

		# Case-insensitive direct name
		name, _ = _resolve_account_name("acc_one", mock_accounts)
		self.assertEqual(name, "Acc_One")

		# Substring of account_name
		name, _ = _resolve_account_name("demo", mock_accounts)
		self.assertEqual(name, "Acc_Demo")

		# Phone digits match
		name, _ = _resolve_account_name("9876543210", mock_accounts)
		self.assertEqual(name, "Acc_Demo")

	def test_nonexistent_and_fallback_resolution(self):
		"""Nonexistent account falls back to first account."""
		mock_accounts = [
			{"name": "Default_Acc", "account_name": "Default Acc", "phone_number": "", "display_phone_number": ""},
			{"name": "Secondary_Acc", "account_name": "Secondary Acc", "phone_number": "", "display_phone_number": ""},
		]

		# None or 'all' -> Default_Acc
		name, _ = _resolve_account_name(None, mock_accounts)
		self.assertEqual(name, "Default_Acc")

		name, _ = _resolve_account_name("all", mock_accounts)
		self.assertEqual(name, "Default_Acc")

		# Non-existent name -> fallback to Default_Acc
		name, _ = _resolve_account_name("unknown_nonexistent", mock_accounts)
		self.assertEqual(name, "Default_Acc")

		# Numeric out-of-range -> fallback to Default_Acc
		name, _ = _resolve_account_name("999", mock_accounts)
		self.assertEqual(name, "Default_Acc")

	@patch("msuite_whatsapp.api.v1.app.analytics_query._fetch_accounts_list")
	def test_get_messaging_summary_numeric_account(self, mock_fetch):
		"""get_messaging_summary accepts numeric account string and returns valid structure."""
		mock_fetch.return_value = [
			{"name": "Acc_One", "account_name": "Acc One", "phone_number": "", "display_phone_number": ""}
		]
		frappe.local.db.count.return_value = 10
		res = get_messaging_summary(account_name="1", days=30)
		self.assertIsInstance(res, dict)
		self.assertIn("sent", res)
		self.assertIn("delivered", res)
		self.assertIn("delivery_rate", res)
		self.assertIn("read_rate", res)

	@patch("frappe.get_doc")
	@patch("msuite_whatsapp.api.v1.app.analytics_query._fetch_accounts_list")
	def test_get_whatsapp_account_insights_fallback(self, mock_fetch, mock_get_doc):
		"""get_whatsapp_account_insights safely handles Meta API failure and returns valid dict."""
		mock_fetch.return_value = [
			{"name": "Acc_One", "account_name": "Acc One", "phone_number": "", "display_phone_number": ""}
		]
		frappe.local.db.count.return_value = 10
		frappe.local.db.sql.return_value = []
		mock_doc = MagicMock()
		mock_doc.name = "Acc_One"
		mock_doc.account_name = "Acc One"
		mock_doc.waba_id = "12345"
		mock_doc.status = "Active"
		mock_doc.get.return_value = "INR"
		mock_get_doc.return_value = mock_doc

		with patch("msuite_whatsapp.services.analytics.sync._call_meta_api", side_effect=Exception("Meta API timeout")):
			res = get_whatsapp_account_insights(account_name="1", days=7)
			self.assertIsInstance(res, dict)
			self.assertIn("totals", res)
			self.assertIn("all_messages", res["totals"])
			self.assertIn("delivery_rate", res["totals"]["all_messages"])
			self.assertIn("daily_trend", res)
			self.assertIsInstance(res["daily_trend"], list)
			self.assertIn("account", res)
			self.assertIn("accounts_list", res)

