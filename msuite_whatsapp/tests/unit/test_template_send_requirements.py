"""Task 2: get_template_send_requirements (pure helper + whitelisted wrapper), mocked permissions."""

import json
import unittest
from unittest.mock import patch

import frappe

from msuite_whatsapp.api.v1.app import crud
from msuite_whatsapp.constants import WHATSAPP_COUPON_CODE_MAX, WHATSAPP_LTO_TEXT_MAX
from msuite_whatsapp.api.v1.app import templates as api
from msuite_whatsapp.services.validators.template_validator import get_send_requirements

COPY = {"button_type": "Copy Offer Code"}
URL = {"button_type": "Visit Website"}


def _lto(has_expiration=True, text="Summer"):
	return json.dumps({"limited_time_offer": {"text": text, "has_expiration": has_expiration}})


def _req(**kw):
	return get_send_requirements(frappe._dict(buttons=kw.pop("buttons", []), **kw))


class TestRequirements(unittest.TestCase):
	def test_plain_template_needs_nothing(self):
		r = _req(button_configuration="", offer_code="")
		self.assertFalse(r["needs_expiry"])
		self.assertFalse(r["needs_coupon"])
		self.assertFalse(r["supports_tap_target"])
		self.assertIsNone(r["coupon_prefill"])
		self.assertIsNone(r["lto_text"])

	def test_lto_expiration_flag(self):
		self.assertTrue(_req(button_configuration=_lto(True))["needs_expiry"])
		r = _req(button_configuration=_lto(False))
		self.assertFalse(r["needs_expiry"])
		self.assertEqual(r["lto_text"], "Summer")

	def test_malformed_config_never_raises(self):
		for raw in ("{bad", "", "[]", "[1,2]", "null", None, "   ", json.dumps({"limited_time_offer": "x"})):
			with self.subTest(raw=raw):
				r = _req(button_configuration=raw)
				self.assertFalse(r["needs_expiry"])
				self.assertIsNone(r["lto_text"])

	def test_copy_code_with_and_without_stored_code(self):
		self.assertTrue(_req(buttons=[COPY], offer_code="")["needs_coupon"])
		self.assertIsNone(_req(buttons=[COPY], offer_code="  ")["coupon_prefill"])
		r = _req(buttons=[COPY], offer_code=" SAVE20 ")
		self.assertTrue(r["needs_coupon"])
		self.assertEqual(r["coupon_prefill"], "SAVE20")

	def test_stored_code_without_button_is_not_needed(self):
		self.assertFalse(_req(buttons=[URL], offer_code="SAVE20")["needs_coupon"])

	def test_all_features_together(self):
		r = _req(button_configuration=_lto(), buttons=[COPY, URL], offer_code="A")
		self.assertTrue(r["needs_expiry"] and r["needs_coupon"] and r["supports_tap_target"])

	def test_limits_come_from_constants(self):
		r = _req()
		self.assertEqual(r["coupon_max"], WHATSAPP_COUPON_CODE_MAX)
		self.assertEqual(r["lto_text_max"], WHATSAPP_LTO_TEXT_MAX)

	def test_unicode_lto_text(self):
		self.assertEqual(_req(button_configuration=_lto(text="Soldes d'été 🎉"))["lto_text"], "Soldes d'été 🎉")

	def test_blank_lto_text_is_none(self):
		self.assertIsNone(_req(button_configuration=_lto(text="  "))["lto_text"])


class TestEndpoint(unittest.TestCase):
	def test_denied_without_read_permission(self):
		with patch.object(api.frappe, "has_permission", return_value=False), patch.object(api.frappe, "get_doc") as gd:
			with self.assertRaises(frappe.PermissionError):
				api.get_template_send_requirements("t")
		gd.assert_not_called()

	def test_missing_template(self):
		with patch.object(api.frappe, "has_permission", return_value=True):
			with self.assertRaises(frappe.DoesNotExistError):
				api.get_template_send_requirements("no-such-template-ünï")

	def test_allowed_returns_shape_and_checks_doc_permission(self):
		doc = frappe._dict(button_configuration=_lto(), buttons=[COPY], offer_code="")
		with patch.object(api.frappe, "has_permission", return_value=True) as hp, patch.object(
			api.frappe, "get_doc", return_value=doc
		):
			r = api.get_template_send_requirements("t")
		hp.assert_called_once_with("WhatsApp Templates", "read", doc="t")
		self.assertEqual(
			set(r),
			{"needs_expiry", "needs_coupon", "coupon_prefill", "coupon_max", "lto_text", "lto_text_max", "supports_tap_target"},
		)

	def test_guest_denied(self):
		with patch.object(api.frappe, "has_permission", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				api.get_template_send_requirements("t")

	def test_crud_shim_reexports(self):
		self.assertIs(crud.get_template_send_requirements, api.get_template_send_requirements)


class TestTemplateLimits(unittest.TestCase):
	def test_returns_constant(self):
		with patch.object(api.frappe, "has_permission", return_value=True):
			self.assertEqual(api.get_whatsapp_template_limits(), {"lto_text_max": WHATSAPP_LTO_TEXT_MAX})

	def test_denied_without_read(self):
		with patch.object(api.frappe, "has_permission", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				api.get_whatsapp_template_limits()

	def test_crud_shim_reexports(self):
		self.assertIs(crud.get_whatsapp_template_limits, api.get_whatsapp_template_limits)
