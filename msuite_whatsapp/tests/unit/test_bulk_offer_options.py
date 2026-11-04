"""Task 4: Bulk WhatsApp Message offer options: validation + send plumbing (mocked, no HTTP)."""

import json
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import frappe

from msuite_whatsapp.constants import WHATSAPP_COUPON_CODE_MAX
from msuite_whatsapp.whatsapp.doctype.bulk_whatsapp_message.bulk_whatsapp_message import BulkWhatsAppMessage
from msuite_whatsapp.services.bulk import bulk_send_service as svc
from msuite_whatsapp.services.validators import bulk_message_validator as val

NOW = datetime(2030, 1, 1, 12, 0, 0)
FUTURE = datetime(2030, 6, 1, 12, 0, 0)
LTO = json.dumps({"limited_time_offer": {"text": "Sale", "has_expiration": True}})
COPY = {"button_type": "Copy Offer Code"}
URL = {"button_type": "Visit Website"}


def _template(**kw):
	base = dict(button_configuration="", buttons=[], offer_code="")
	base.update(kw)
	return frappe._dict(base)


def _doc(**kw):
	base = dict(
		template="t", offer_expires_at=None, coupon_code=None, tap_target_url=None, tap_target_title=None,
		scheduled_time=None, docstatus=0, get_doc_before_save=lambda: None,
	)
	base.update(kw)
	return frappe._dict(base)


def _check(doc, template):
	with patch.object(val.frappe, "get_cached_doc", return_value=template), patch.object(
		val, "now_datetime", return_value=NOW
	):
		val.validate_offer_options(doc)


class TestOfferValidation(unittest.TestCase):
	def assertRejects(self, doc, template, message):
		with self.assertRaises(frappe.ValidationError) as cm:
			_check(doc, template)
		self.assertIn(message, str(cm.exception))

	def test_no_offer_fields_no_template_needs_passes(self):
		_check(_doc(), _template())

	def test_no_template_skips(self):
		val.validate_offer_options(_doc(template=None, coupon_code="X"))

	def test_expiry_required_when_template_needs_it(self):
		self.assertRejects(_doc(), _template(button_configuration=LTO), "Offer end date and time is required for this template.")

	def test_expiry_given_but_template_has_no_countdown(self):
		self.assertRejects(
			_doc(offer_expires_at=FUTURE), _template(), "This template has no limited-time offer with a countdown."
		)

	def test_expiry_past_or_now_rejected(self):
		for when in (NOW, datetime(2029, 1, 1)):
			with self.subTest(when=when):
				self.assertRejects(
					_doc(offer_expires_at=when), _template(button_configuration=LTO),
					"Offer end date and time must be in the future.",
				)

	def test_expiry_one_second_ahead_ok(self):
		_check(_doc(offer_expires_at=datetime(2030, 1, 1, 12, 0, 1)), _template(button_configuration=LTO))

	def test_expiry_string_value_ok(self):
		_check(_doc(offer_expires_at="2030-06-01 12:00:00"), _template(button_configuration=LTO))

	def test_expiry_must_be_after_schedule(self):
		tpl = _template(button_configuration=LTO)
		self.assertRejects(
			_doc(offer_expires_at=FUTURE, scheduled_time=FUTURE), tpl,
			"Offer end date and time must be later than the scheduled time.",
		)
		self.assertRejects(
			_doc(offer_expires_at=FUTURE, scheduled_time=datetime(2030, 7, 1)), tpl,
			"Offer end date and time must be later than the scheduled time.",
		)
		_check(_doc(offer_expires_at=FUTURE, scheduled_time=datetime(2030, 5, 1)), tpl)

	def test_already_submitted_doc_skips_future_check(self):
		before = frappe._dict(docstatus=1)
		_check(
			_doc(offer_expires_at=datetime(2029, 1, 1), docstatus=1, get_doc_before_save=lambda: before),
			_template(button_configuration=LTO),
		)

	def test_coupon_length_boundaries(self):
		tpl = _template(buttons=[COPY])
		_check(_doc(coupon_code="x" * WHATSAPP_COUPON_CODE_MAX), tpl)
		self.assertRejects(
			_doc(coupon_code="x" * (WHATSAPP_COUPON_CODE_MAX + 1)), tpl,
			f"Coupon code cannot exceed {WHATSAPP_COUPON_CODE_MAX} characters.",
		)

	def test_coupon_counts_characters_not_bytes(self):
		tpl = _template(buttons=[COPY])
		_check(_doc(coupon_code="🎉" * WHATSAPP_COUPON_CODE_MAX), tpl)
		_check(_doc(coupon_code="é" * WHATSAPP_COUPON_CODE_MAX), tpl)
		self.assertRejects(_doc(coupon_code="🎉" * (WHATSAPP_COUPON_CODE_MAX + 1)), tpl, "cannot exceed")

	def test_coupon_whitespace_only_rejected(self):
		self.assertRejects(_doc(coupon_code="   "), _template(buttons=[COPY]), "Coupon code cannot be blank.")

	def test_coupon_is_stripped(self):
		doc = _doc(coupon_code="  SAVE20 ")
		_check(doc, _template(buttons=[COPY]))
		self.assertEqual(doc.coupon_code, "SAVE20")

	def test_coupon_without_copy_button_is_an_error(self):
		self.assertRejects(_doc(coupon_code="SAVE20"), _template(), "This template has no Copy Offer Code button.")

	def test_coupon_required_when_no_stored_code(self):
		self.assertRejects(_doc(), _template(buttons=[COPY]), "A coupon code is required for this template.")

	def test_stored_offer_code_makes_coupon_optional(self):
		_check(_doc(), _template(buttons=[COPY], offer_code="STORED"))

	def test_tap_target_needs_both(self):
		tpl = _template(buttons=[URL])
		self.assertRejects(_doc(tap_target_url="https://a.test"), tpl, "Tap link needs both a URL and a title.")
		self.assertRejects(_doc(tap_target_title="Go"), tpl, "Tap link needs both a URL and a title.")
		self.assertRejects(
			_doc(tap_target_url="https://a.test", tap_target_title="   "), tpl, "Tap link needs both a URL and a title."
		)

	def test_tap_target_scheme(self):
		tpl = _template(buttons=[URL])
		for bad in ("javascript:alert(1)", "data:text/html,x", "ftp://a.test", "//a.test", "a.test"):
			with self.subTest(bad=bad):
				self.assertRejects(
					_doc(tap_target_url=bad, tap_target_title="Go"), tpl,
					"Tap link URL must start with http:// or https://.",
				)
		_check(_doc(tap_target_url="HTTPS://a.test/x?y=1", tap_target_title="Go"), tpl)

	def test_tap_target_requires_url_button(self):
		self.assertRejects(
			_doc(tap_target_url="https://a.test", tap_target_title="Go"), _template(),
			"This template has no Visit Website button.",
		)

	def test_all_features_together(self):
		_check(
			_doc(offer_expires_at=FUTURE, coupon_code="SAVE20", tap_target_url="https://a.test", tap_target_title="Go"),
			_template(button_configuration=LTO, buttons=[COPY, URL]),
		)

	def test_controller_skips_checks_for_partial_draft(self):
		doc = MagicMock()
		doc.flags = frappe._dict(partial_draft=True)
		doc.recipients = []
		with patch.object(val, "validate_offer_options") as m:
			BulkWhatsAppMessage.validate(doc)
		m.assert_not_called()

	def test_controller_calls_validator_when_not_draft(self):
		doc = MagicMock()
		doc.flags = frappe._dict()
		with patch.object(val, "validate_recipients", return_value=1), patch.object(
			val, "validate_mpm_configuration"
		), patch.object(val, "validate_carousel_configuration"), patch.object(
			val, "validate_template_approved"
		), patch.object(val, "validate_offer_options") as m:
			BulkWhatsAppMessage.validate(doc)
		m.assert_called_once_with(doc)


def _ms(dt_utc):
	return int(dt_utc.replace(tzinfo=timezone.utc).timestamp() * 1000)


class TestAwareIsoExpiry(unittest.TestCase):
	"""ISO strings with a UTC offset (REST API callers) must convert, not crash or shift."""

	def test_validator_accepts_aware_future_iso_without_type_error(self):
		doc = _doc(offer_expires_at="2030-06-01T12:00:00Z")
		with patch.object(val, "get_system_timezone", return_value="Asia/Kolkata"):
			_check(doc, _template(button_configuration=LTO))

	def test_validator_rejects_aware_past_iso_with_clean_error(self):
		doc = _doc(offer_expires_at="2029-06-01T12:00:00+00:00")
		with patch.object(val, "get_system_timezone", return_value="UTC"), self.assertRaises(
			frappe.ValidationError
		) as cm:
			_check(doc, _template(button_configuration=LTO))
		self.assertIn("must be in the future", str(cm.exception))

	def test_aware_value_is_converted_to_site_time_not_relabelled(self):
		with patch.object(val, "get_system_timezone", return_value="Asia/Kolkata"):
			self.assertEqual(val.to_site_naive_datetime("2030-06-01T12:00:00Z"), datetime(2030, 6, 1, 17, 30))
			self.assertEqual(val.to_site_naive_datetime(datetime(2030, 6, 1, 12, 0)), datetime(2030, 6, 1, 12, 0))

	def test_send_ms_for_aware_iso_is_the_true_instant(self):
		with patch.object(val, "get_system_timezone", return_value="Asia/Kolkata"), patch.object(
			svc, "get_system_timezone", return_value="Asia/Kolkata"
		), patch.object(svc, "now_datetime", return_value=datetime(2000, 1, 1)):
			ms = svc._offer_expiry_to_ms(frappe._dict(offer_expires_at="2030-06-01T12:00:00Z"))
		self.assertEqual(ms, _ms(datetime(2030, 6, 1, 12, 0)))


class TestExpiryToMs(unittest.TestCase):
	def _ms_for(self, value, tz):
		with patch.object(svc, "get_system_timezone", return_value=tz), patch.object(
			svc, "now_datetime", return_value=datetime(2000, 1, 1)
		):
			return svc._offer_expiry_to_ms(frappe._dict(offer_expires_at=value))

	def test_empty_is_none(self):
		for v in (None, "", 0):
			self.assertIsNone(self._ms_for(v, "UTC"))

	def test_kolkata_offset(self):
		self.assertEqual(self._ms_for(datetime(2030, 3, 15, 12, 0), "Asia/Kolkata"), _ms(datetime(2030, 3, 15, 6, 30)))

	def test_dst_zone_summer_and_winter(self):
		self.assertEqual(self._ms_for(datetime(2030, 7, 1, 12, 0), "America/New_York"), _ms(datetime(2030, 7, 1, 16, 0)))
		self.assertEqual(self._ms_for(datetime(2030, 12, 1, 12, 0), "America/New_York"), _ms(datetime(2030, 12, 1, 17, 0)))

	def test_leap_day_and_year_end(self):
		self.assertEqual(self._ms_for(datetime(2028, 2, 29, 23, 0), "UTC"), _ms(datetime(2028, 2, 29, 23, 0)))
		self.assertEqual(
			self._ms_for(datetime(2030, 12, 31, 23, 59, 59), "Asia/Kolkata"), _ms(datetime(2030, 12, 31, 18, 29, 59))
		)

	def test_string_input(self):
		self.assertEqual(self._ms_for("2030-03-15 12:00:00", "UTC"), _ms(datetime(2030, 3, 15, 12, 0)))

	def test_past_expiry_raises(self):
		with patch.object(svc, "get_system_timezone", return_value="UTC"), patch.object(
			svc, "now_datetime", return_value=datetime(2030, 1, 1)
		):
			with self.assertRaises(frappe.ValidationError) as cm:
				svc._offer_expiry_to_ms(frappe._dict(offer_expires_at=datetime(2029, 12, 31)))
		self.assertIn("Offer ended before this message could be sent.", str(cm.exception))


def _send_doc(**kw):
	base = dict(
		name="BULK-1", doctype="Bulk WhatsApp Message", template="t", template_variables=None, attach=None,
		whatsapp_account=None, is_carousel_template=0, thumbnail_product_retailer_id="", product_ids=[],
		offer_expires_at=None, coupon_code=None, tap_target_url=None, tap_target_title=None,
	)
	base.update(kw)
	return frappe._dict(base)


def _run_send(doc, tz="UTC", now=datetime(2000, 1, 1)):
	"""Run create_single_message with every collaborator mocked; return send_to_phone mock."""
	recipient = {"mobile_number": "919999999999", "name": "r1"}
	send = MagicMock(return_value={"ok": True})
	db = MagicMock()
	db.get_value.return_value = None
	with patch.object(svc.frappe, "db", db), patch.object(svc, "is_recipient_attempted", return_value=False), patch.object(
		svc, "_claim_send", return_value=True
	), patch.object(svc, "_release_send_claim"), patch.object(svc, "_is_rate_limited", return_value=False), patch.object(
		svc, "_parse_recipient_data", return_value={}
	), patch.object(svc, "get_mpm_action_json", return_value=None), patch.object(
		svc, "_ensure_lead_for_bulk_recipient"
	), patch.object(svc, "row_parent", return_value=("BULK-1", "Bulk WhatsApp Message")), patch.object(
		svc, "_mark_own_row"
	), patch.object(svc, "_has_pending_rows", return_value=True), patch.object(
		svc, "_check_and_update_completion"
	), patch.object(svc, "get_system_timezone", return_value=tz), patch.object(
		svc, "now_datetime", return_value=now
	), patch("msuite_inbox.inbox.services.outbound.send_to_phone", send):
		svc.create_single_message(doc, recipient)
	return send


class TestSendPlumbing(unittest.TestCase):
	def test_payload_has_all_offer_keys(self):
		doc = _send_doc(
			offer_expires_at=datetime(2030, 3, 15, 12, 0), coupon_code="SAVE20",
			tap_target_url="https://a.test", tap_target_title="Go",
		)
		payload = _run_send(doc, tz="Asia/Kolkata").call_args.kwargs["payload"]
		self.assertEqual(payload["limited_time_offer_expiry_ms"], _ms(datetime(2030, 3, 15, 6, 30)))
		self.assertEqual(payload["coupon_code"], "SAVE20")
		self.assertEqual(payload["tap_target"], {"url": "https://a.test", "title": "Go"})

	def test_payload_keys_absent_when_fields_empty(self):
		payload = _run_send(_send_doc()).call_args.kwargs["payload"]
		for k in ("limited_time_offer_expiry_ms", "coupon_code", "tap_target"):
			self.assertNotIn(k, payload)

	def test_expiry_passed_by_send_time_fails_recipient_without_calling_meta(self):
		doc = _send_doc(offer_expires_at=datetime(2029, 12, 31))
		recipient = {"mobile_number": "919999999999", "name": "r1"}
		send = MagicMock()
		db = MagicMock()
		db.get_value.return_value = None
		db.sql.return_value = []
		with patch.object(svc.frappe, "db", db), patch.object(svc, "is_recipient_attempted", return_value=False), patch.object(
			svc, "_claim_send", return_value=True
		), patch.object(svc, "_release_send_claim") as release, patch.object(svc, "_is_rate_limited", return_value=False), patch.object(
			svc, "_parse_recipient_data", return_value={}
		), patch.object(svc, "get_mpm_action_json", return_value=None), patch.object(
			svc, "_ensure_lead_for_bulk_recipient"
		), patch.object(svc, "row_parent", return_value=("BULK-1", "Bulk WhatsApp Message")), patch.object(
			svc, "_check_and_update_completion"
		), patch.object(svc, "get_system_timezone", return_value="UTC"), patch.object(
			svc, "now_datetime", return_value=datetime(2030, 1, 1)
		), patch("msuite_inbox.inbox.services.outbound.send_to_phone", send):
			svc.create_single_message(doc, recipient)
		send.assert_not_called()
		release.assert_called_once()
		update = [c for c in db.sql.call_args_list if "UPDATE `tabWhatsApp Recipient`" in str(c.args[0])]
		self.assertTrue(update)
		args = update[0].args[1]
		self.assertEqual(args[0], "Failed")
		self.assertIn("Offer ended before this message could be sent.", args[2])
		self.assertEqual(args[3], 0)  # not retryable
