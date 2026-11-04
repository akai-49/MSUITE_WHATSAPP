"""Phase 5.1: limited-time-offer / coupon-code / tap-target template support (mocked, no HTTP)."""

import json
import unittest
from unittest.mock import patch

import frappe

from msuite_whatsapp.constants import WHATSAPP_COUPON_CODE_MAX, WHATSAPP_LTO_TEXT_MAX
from msuite_whatsapp.integrations.meta import message_provider, template_provider
from msuite_whatsapp.services.templates import template_sync_service
from msuite_whatsapp.services.validators import template_validator as v

LTO = {"limited_time_offer": {"text": "Summer sale", "has_expiration": True}}


def _tpl(**kw):
	base = dict(
		template="Hi {{1}}", category="MARKETING", header_type="IMAGE", footer="", buttons=[],
		is_carousel=0, carousel_cards=[], sample_values="Al", parameter_format="POSITIONAL",
		add_security_recommendation=0, is_call_permission=0, button_configuration=json.dumps(LTO),
		template_type="DEFAULT", offer_code="", actual_name="t", template_name="t", language_code="en",
		parameters=None, sample="/files/a.png", media_sample="/files/a.png",
	)
	base.update(kw)
	return frappe._dict(base)


class TestLtoValidation(unittest.TestCase):
	def test_none_and_blank_mean_no_lto(self):
		for raw in (None, "", "   ", "{}", {}):
			self.assertIsNone(v.validate_limited_time_offer(raw, "MARKETING", "IMAGE", ""))

	def test_valid_config_returned_normalised(self):
		out = v.validate_limited_time_offer(json.dumps(LTO), "MARKETING", "VIDEO", "")
		self.assertEqual(out, {"text": "Summer sale", "has_expiration": True})

	def test_text_boundary(self):
		ok = {"limited_time_offer": {"text": "x" * WHATSAPP_LTO_TEXT_MAX}}
		self.assertEqual(v.validate_limited_time_offer(ok, "MARKETING", "IMAGE", "")["has_expiration"], False)
		bad = {"limited_time_offer": {"text": "x" * (WHATSAPP_LTO_TEXT_MAX + 1)}}
		with self.assertRaises(frappe.ValidationError):
			v.validate_limited_time_offer(bad, "MARKETING", "IMAGE", "")

	def test_unicode_counts_characters(self):
		cfg = {"limited_time_offer": {"text": "\U0001F525" * WHATSAPP_LTO_TEXT_MAX}}
		self.assertTrue(v.validate_limited_time_offer(cfg, "MARKETING", "IMAGE", ""))

	def test_rejections(self):
		cases = [
			("not json{", "MARKETING", "IMAGE", ""),
			("[1]", "MARKETING", "IMAGE", ""),
			({"limited_time_offer": {"text": "  "}}, "MARKETING", "IMAGE", ""),
			({"limited_time_offer": {"text": 5}}, "MARKETING", "IMAGE", ""),
			({"limited_time_offer": {"text": "a", "has_expiration": "yes"}}, "MARKETING", "IMAGE", ""),
			(LTO, "UTILITY", "IMAGE", ""),
			(LTO, "MARKETING", "TEXT", ""),
			(LTO, "MARKETING", "", ""),
			(LTO, "MARKETING", "IMAGE", "footer text"),
		]
		for cfg, cat, hdr, footer in cases:
			with self.subTest(cfg=cfg, cat=cat, hdr=hdr, footer=footer):
				with self.assertRaises(frappe.ValidationError):
					v.validate_limited_time_offer(cfg, cat, hdr, footer)


class TestCouponCodeLimit(unittest.TestCase):
	def _btn(self):
		return [frappe._dict(button_type="Copy Offer Code", button_label="Copy", otp_type="COPY_CODE", example_url="")]

	def test_boundary(self):
		v.validate_buttons(self._btn(), "MARKETING", "A" * WHATSAPP_COUPON_CODE_MAX)
		with self.assertRaises(frappe.ValidationError):
			v.validate_buttons(self._btn(), "MARKETING", "A" * (WHATSAPP_COUPON_CODE_MAX + 1))


class TestLtoComponentBuild(unittest.TestCase):
	def test_lto_component_emitted_before_body_and_without_footer(self):
		comps = template_provider.build_components(_tpl())
		types = [c["type"] for c in comps]
		self.assertEqual(types.index("limited_time_offer"), types.index("BODY") - 1)
		self.assertLess(types.index("HEADER"), types.index("limited_time_offer"))
		lto = next(c for c in comps if c["type"] == "limited_time_offer")
		self.assertEqual(lto["limited_time_offer"], {"text": "Summer sale", "has_expiration": True})

	def test_no_config_no_component(self):
		comps = template_provider.build_components(_tpl(button_configuration=None))
		self.assertNotIn("limited_time_offer", [c["type"] for c in comps])

	def test_garbage_config_ignored_at_build(self):
		comps = template_provider.build_components(_tpl(button_configuration="{{oops"))
		self.assertNotIn("limited_time_offer", [c["type"] for c in comps])


class TestLtoSync(unittest.TestCase):
	def test_sync_component_stored_in_button_configuration(self):
		doc = frappe._dict(button_configuration=None)
		template_sync_service._apply_component(
			doc, {"type": "LIMITED_TIME_OFFER", "limited_time_offer": {"text": "Hot", "has_expiration": False}}
		)
		self.assertEqual(json.loads(doc.button_configuration), {"limited_time_offer": {"text": "Hot", "has_expiration": False}})

	def test_sync_preserves_other_keys(self):
		doc = frappe._dict(button_configuration=json.dumps({"other": 1}))
		template_sync_service._apply_component(doc, {"type": "LIMITED_TIME_OFFER", "limited_time_offer": {"text": "Hot"}})
		self.assertEqual(json.loads(doc.button_configuration)["other"], 1)


class TestSyncReviewFixes(unittest.TestCase):
	def test_dict_button_configuration_does_not_crash(self):
		doc = frappe._dict(button_configuration={"other": 1})
		template_sync_service._apply_component(doc, {"type": "LIMITED_TIME_OFFER", "limited_time_offer": {"text": "Hot"}})
		cfg = json.loads(doc.button_configuration)
		self.assertEqual(cfg["other"], 1)
		self.assertEqual(cfg["limited_time_offer"]["text"], "Hot")

	def test_copy_code_example_synced_to_offer_code(self):
		for example, expected in (("SAVE20", "SAVE20"), (["SAVE20"], "SAVE20"), (None, "")):
			with self.subTest(example=example):
				doc = frappe._dict(offer_code="", buttons=[], doctype="WhatsApp Templates", name=None)
				doc.set = lambda k, v, d=doc: d.__setitem__(k, v)
				doc.append = lambda k, v, d=doc: d[k].append(v)
				btn = {"type": "COPY_CODE", "text": "Copy"}
				if example is not None:
					btn["example"] = example
				template_sync_service._sync_buttons(doc, [btn])
				self.assertEqual(doc.offer_code, expected)


class TestSendComponents(unittest.TestCase):
	def _build(self, tpl, **kw):
		with patch.object(message_provider.frappe, "get_cached_doc", return_value=tpl), patch.object(
			message_provider.media_provider, "get_media_header_param", return_value={"type": "image", "image": {"id": "1"}}
		):
			return message_provider.build_template_meta("t", **kw)["components"]

	def test_lto_expiration_component(self):
		comps = self._build(_tpl(), limited_time_offer_expiry_ms=1698562800000)
		lto = next(c for c in comps if c["type"] == "limited_time_offer")
		self.assertEqual(lto["parameters"], [{"type": "limited_time_offer", "limited_time_offer": {"expiration_time_ms": 1698562800000}}])

	def test_lto_with_expiration_requires_expiry(self):
		with self.assertRaises(frappe.ValidationError):
			self._build(_tpl())

	def test_lto_without_expiration_needs_none(self):
		cfg = json.dumps({"limited_time_offer": {"text": "Hot", "has_expiration": False}})
		comps = self._build(_tpl(button_configuration=cfg))
		self.assertNotIn("limited_time_offer", [c["type"] for c in comps])

	def test_non_positive_expiry_rejected(self):
		for bad in (0, -5, "abc"):
			with self.subTest(bad=bad), self.assertRaises(frappe.ValidationError):
				self._build(_tpl(), limited_time_offer_expiry_ms=bad)

	def test_coupon_code_button_and_url_index(self):
		btns = [
			frappe._dict(button_type="Copy Offer Code", button_label="Copy", url_type=None, website_url=""),
			frappe._dict(button_type="Visit Website", button_label="Go", url_type="Dynamic", website_url="https://x.test/{{1}}"),
		]
		tpl = _tpl(button_configuration=None, buttons=btns)
		comps = self._build(tpl, coupon_code="SAVE20")
		copy = next(c for c in comps if c.get("sub_type") == "copy_code")
		self.assertEqual(copy["index"], "0")
		self.assertEqual(copy["parameters"], [{"type": "coupon_code", "coupon_code": "SAVE20"}])
		url = next(c for c in comps if c.get("sub_type") == "url")
		self.assertEqual(url["index"], "1")

	def test_coupon_code_falls_back_to_template_offer_code(self):
		btns = [frappe._dict(button_type="Copy Offer Code", button_label="Copy", url_type=None, website_url="")]
		comps = self._build(_tpl(button_configuration=None, buttons=btns, offer_code="DEFAULT1"))
		self.assertEqual(next(c for c in comps if c.get("sub_type") == "copy_code")["parameters"][0]["coupon_code"], "DEFAULT1")

	def test_coupon_code_too_long_or_missing(self):
		btns = [frappe._dict(button_type="Copy Offer Code", button_label="Copy", url_type=None, website_url="")]
		tpl = _tpl(button_configuration=None, buttons=btns)
		for code in ("X" * (WHATSAPP_COUPON_CODE_MAX + 1), None):
			with self.subTest(code=code), self.assertRaises(frappe.ValidationError):
				self._build(tpl, coupon_code=code)

	def test_tap_target_component(self):
		comps = self._build(_tpl(button_configuration=None), tap_target={"url": "https://x.test", "title": "Details"})
		tt = next(c for c in comps if c["type"] == "tap_target_configuration")
		self.assertEqual(tt["parameters"], [{"type": "tap_target_configuration", "tap_target_configuration": [{"url": "https://x.test", "title": "Details"}]}])

	def test_tap_target_validation(self):
		for bad in ({"url": "", "title": "t"}, {"url": "https://x.test", "title": " "}, {"url": "javascript:alert(1)", "title": "t"}, {"title": "t"}):
			with self.subTest(bad=bad), self.assertRaises(frappe.ValidationError):
				self._build(_tpl(button_configuration=None), tap_target=bad)
