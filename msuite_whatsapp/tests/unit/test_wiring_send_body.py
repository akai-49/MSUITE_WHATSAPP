"""Task 1: _build_send_body forwards offer expiry / coupon / tap target to build_template_meta (mocked)."""

import unittest
from unittest.mock import patch

import frappe

from msuite_whatsapp.services.channels import inbox_channel as wa_channel
from msuite_whatsapp.integrations.meta import message_provider
from msuite_whatsapp.tests.unit.test_marketing_templates import _tpl

BUILDER = "msuite_whatsapp.utils.template_send.build_template_meta"
TARGET = "919999999999"
EXTRA_KEYS = ("limited_time_offer_expiry_ms", "coupon_code", "tap_target")


def _send(payload):
	"""Run _build_send_body with a mocked builder; return (body, builder_mock)."""
	with patch(BUILDER, return_value={"name": "t", "components": [], "_resolved_parameters": []}) as m:
		body = wa_channel._build_send_body(TARGET, {"type": "template", "template": "t", **payload})
	return body, m


class TestForwarding(unittest.TestCase):
	def test_each_key_forwarded(self):
		tap = {"url": "https://x.test", "title": "Go"}
		_, m = _send({"limited_time_offer_expiry_ms": 1698562800000, "coupon_code": "SAVE20", "tap_target": tap})
		kw = m.call_args.kwargs
		self.assertEqual(kw["limited_time_offer_expiry_ms"], 1698562800000)
		self.assertEqual(kw["coupon_code"], "SAVE20")
		self.assertEqual(kw["tap_target"], tap)

	def test_absent_keys_are_none(self):
		_, m = _send({})
		for k in EXTRA_KEYS:
			self.assertIsNone(m.call_args.kwargs[k])

	def test_falsy_values_forwarded_as_given(self):
		for key, val in (("limited_time_offer_expiry_ms", 0), ("coupon_code", ""), ("tap_target", None)):
			with self.subTest(key=key):
				_, m = _send({key: val})
				self.assertEqual(m.call_args.kwargs[key], val)

	def test_explicit_components_still_override(self):
		body, _ = _send({"components": [{"type": "x"}], "coupon_code": "A"})
		self.assertEqual(body["template"]["components"], [{"type": "x"}])


class TestBuilderRejectsBadValues(unittest.TestCase):
	"""Validation lives in the real builder; prove bad values reach it through the send body."""

	def _real(self, payload, tpl):
		with patch.object(message_provider.frappe, "get_cached_doc", return_value=tpl), patch.object(
			message_provider.media_provider, "get_media_header_param", return_value={"type": "image", "image": {"id": "1"}}
		):
			return wa_channel._build_send_body(TARGET, {"type": "template", "template": "t", **payload})

	def test_whitespace_coupon_rejected(self):
		tpl = _tpl(button_configuration="", buttons=[frappe._dict(button_type="Copy Offer Code")])
		with self.assertRaises(frappe.ValidationError) as cm:
			self._real({"coupon_code": "   "}, tpl)
		self.assertIn("coupon code of 1 to 15", str(cm.exception))

	def test_unicode_coupon_is_forwarded_into_component(self):
		tpl = _tpl(button_configuration="", buttons=[frappe._dict(button_type="Copy Offer Code")])
		body = self._real({"coupon_code": "SÄLE🎉"}, tpl)
		comp = next(c for c in body["template"]["components"] if c.get("sub_type") == "copy_code")
		self.assertEqual(comp["parameters"][0]["coupon_code"], "SÄLE🎉")

	def test_json_string_tap_target_is_accepted(self):
		tpl = _tpl(button_configuration="")
		body = self._real({"tap_target": '{"url": "https://x.test", "title": "Shop"}'}, tpl)
		comp = next(c for c in body["template"]["components"] if c["type"] == "tap_target_configuration")
		self.assertEqual(comp["parameters"][0]["tap_target_configuration"], [{"url": "https://x.test", "title": "Shop"}])

	def test_non_dict_tap_target_rejected(self):
		tpl = _tpl(button_configuration="")
		for bad in ("https://x.test", ["https://x.test"]):
			with self.subTest(bad=bad), self.assertRaises(frappe.ValidationError) as cm:
				self._real({"tap_target": bad}, tpl)
			self.assertIn("Tap target needs an http(s) URL and a title.", str(cm.exception))
