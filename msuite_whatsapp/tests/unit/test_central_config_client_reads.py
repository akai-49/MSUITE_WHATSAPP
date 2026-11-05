"""Tests for MSuite WhatsApp client reads from central configuration."""

from __future__ import annotations

from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe
from msuite_core.central_config import clear_all, store_snapshot
from msuite_whatsapp.constants import (
	WHATSAPP_MM_SENDABLE_CATEGORY,
	WHATSAPP_MM_SITE_CONFIG_KEY,
)
from msuite_whatsapp.integrations.meta.client import _should_use_marketing_messages
from msuite_whatsapp.services.analytics.mm_sync import _is_enabled


class TestWhatsAppCentralConfigClientReads(TestCase):
	"""Test suite asserting msuite_whatsapp client reads resolve via central config."""

	def setUp(self) -> None:
		"""Clean up central config and backup frappe.conf."""
		clear_all()
		self._original_conf = dict(frappe.conf)

	def tearDown(self) -> None:
		"""Restore frappe.conf and clean up central config."""
		clear_all()
		frappe.conf = self._original_conf

	@patch("msuite_whatsapp.integrations.meta.client._template_category", return_value=WHATSAPP_MM_SENDABLE_CATEGORY)
	def test_should_use_marketing_messages_resolution_and_cint(self, mock_cat: MagicMock) -> None:
		"""Verify _should_use_marketing_messages obeys default -> site_config -> pushed hierarchy and cint rule."""
		dummy_doc = frappe._dict(name="acc_1")
		body = {"type": "template", "template": {"name": "promo"}}

		# (a) default off
		with patch.dict(frappe.conf, {WHATSAPP_MM_SITE_CONFIG_KEY: None}):
			self.assertFalse(_should_use_marketing_messages(dummy_doc, body))

		# (b) site_config honoured
		with patch.dict(frappe.conf, {WHATSAPP_MM_SITE_CONFIG_KEY: 1}):
			self.assertTrue(_should_use_marketing_messages(dummy_doc, body))

		# (c) pushed wins
		store_snapshot({WHATSAPP_MM_SITE_CONFIG_KEY: True})
		with patch.dict(frappe.conf, {WHATSAPP_MM_SITE_CONFIG_KEY: 0}):
			self.assertTrue(_should_use_marketing_messages(dummy_doc, body))

		# (d) cint coercion rule
		clear_all()
		for truthy_val in (1, "1", True):
			with patch.dict(frappe.conf, {WHATSAPP_MM_SITE_CONFIG_KEY: truthy_val}):
				self.assertTrue(
					_should_use_marketing_messages(dummy_doc, body),
					f"Expected cint True for {truthy_val!r}",
				)
		for falsy_val in (0, "0", False, None, "invalid"):
			with patch.dict(frappe.conf, {WHATSAPP_MM_SITE_CONFIG_KEY: falsy_val}):
				self.assertFalse(
					_should_use_marketing_messages(dummy_doc, body),
					f"Expected cint False for {falsy_val!r}",
				)

	@patch("msuite_whatsapp.services.analytics.mm_sync.is_feature_enabled", return_value=True)
	@patch("frappe.db.get_default", return_value=None)
	def test_mm_sync_is_enabled_resolution_and_cint(self, mock_default: MagicMock, mock_feat: MagicMock) -> None:
		"""Verify _is_enabled obeys default -> site_config -> pushed hierarchy and cint rule."""
		# (a) default off
		with patch.dict(frappe.conf, {WHATSAPP_MM_SITE_CONFIG_KEY: None}):
			self.assertFalse(_is_enabled("acc_1", "waba_1"))

		# (b) site_config honoured
		with patch.dict(frappe.conf, {WHATSAPP_MM_SITE_CONFIG_KEY: 1}):
			self.assertTrue(_is_enabled("acc_1", "waba_1"))

		# (c) pushed wins
		store_snapshot({WHATSAPP_MM_SITE_CONFIG_KEY: True})
		with patch.dict(frappe.conf, {WHATSAPP_MM_SITE_CONFIG_KEY: 0}):
			self.assertTrue(_is_enabled("acc_1", "waba_1"))
