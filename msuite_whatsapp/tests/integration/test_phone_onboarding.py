"""Phone onboarding service/API. Graph is mocked; no live calls."""

from unittest.mock import MagicMock, patch

import frappe
import requests
from frappe.tests import IntegrationTestCase

from msuite_whatsapp.api.v1.app import phone_onboarding as api
from msuite_whatsapp.services.accounts import phone_onboarding_service as svc

ACCOUNT, PHONE = "Test Onboarding Account", "9990001112223"


def _resp(status=200, body=None, headers=None):
	r = MagicMock()
	r.ok = status < 400
	r.status_code = status
	r.json.return_value = body if body is not None else {}
	r.headers = headers or {}
	return r


def _err(status, code, sub=None, details="", message=""):
	return _resp(status, {"error": {"code": code, "error_subcode": sub, "message": message, "error_data": {"details": details}}})


class OnboardingBase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("WhatsApp Account", ACCOUNT):
			frappe.get_doc({
				"doctype": "WhatsApp Account", "account_name": ACCOUNT, "status": "Active",
				"business_id": "onb_test_business", "app_id": "onb_app",
				"phones": [{"phone_number_id": PHONE, "display_phone_number": "+1 onb", "status": "Active"}],
			}).insert(ignore_permissions=True)
			frappe.db.commit()

	def setUp(self):
		p = patch.object(svc.accounts, "get_credentials", return_value=("https://graph.facebook.com", "v26.0", "tok"))
		p.start()
		self.addCleanup(p.stop)

	def _call_with(self, resp, fn, *args, **kw):
		with patch.object(svc.requests, "request", return_value=resp) as m:
			out = fn(*args, **kw)
		return out, m



class TestPhoneOnboarding(OnboardingBase):
	def test_status_returns_fields_and_hits_graph(self):
		body = {"verified_name": "Acme", "code_verification_status": "EXPIRED", "display_phone_number": "+1 555", "quality_rating": "GREEN"}
		out, m = self._call_with(_resp(200, body), svc.get_status, ACCOUNT, PHONE)
		self.assertTrue(out["ok"])
		self.assertEqual(out["data"]["code_verification_status"], "EXPIRED")
		self.assertEqual(m.call_args.args[:2], ("GET", f"https://graph.facebook.com/v26.0/{PHONE}"))
		self.assertEqual(m.call_args.kwargs["headers"]["Authorization"], "Bearer tok")

	def test_request_code_payload_and_voice_toggle(self):
		out, m = self._call_with(_resp(200, {"success": True}), svc.request_code, ACCOUNT, PHONE, "voice", "en_US")
		self.assertTrue(out["ok"])
		self.assertEqual(m.call_args.kwargs["json"], {"code_method": "VOICE", "language": "en_US"})

	def test_bad_method_and_malformed_inputs_never_reach_meta(self):
		with patch.object(svc.requests, "request") as m:
			with self.assertRaises(frappe.ValidationError):
				svc.request_code(ACCOUNT, PHONE, "EMAIL")
			with self.assertRaises(frappe.ValidationError):
				svc.verify_code(ACCOUNT, PHONE, "12345")
			with self.assertRaises(frappe.ValidationError):
				svc.register(ACCOUNT, PHONE, "12ab56")
		m.assert_not_called()

	def test_foreign_phone_number_id_rejected(self):
		with patch.object(svc.requests, "request") as m:
			with self.assertRaises(frappe.ValidationError):
				svc.get_status(ACCOUNT, "123456789")
		m.assert_not_called()

	def test_rate_limit_subcode_136025_and_retry_after(self):
		out, _ = self._call_with(_resp(400, {"error": {"code": 100, "error_subcode": 136025}}, {"Retry-After": "300"}), svc.request_code, ACCOUNT, PHONE)
		self.assertEqual(out["error"]["code"], "rate_limited")
		self.assertEqual(out["error"]["retry_after"], 300)

	def test_http_429_is_rate_limited(self):
		out, _ = self._call_with(_err(429, 4), svc.verify_code, ACCOUNT, PHONE, "123456")
		self.assertEqual(out["error"]["code"], "rate_limited")

	def test_expired_and_invalid_code(self):
		out, _ = self._call_with(_err(422, 100, details="Code expired"), svc.verify_code, ACCOUNT, PHONE, "123456")
		self.assertEqual(out["error"]["code"], "expired_code")
		out, _ = self._call_with(_err(400, 100, details="Invalid verification code"), svc.verify_code, ACCOUNT, PHONE, "123456")
		self.assertEqual(out["error"]["code"], "invalid_code")

	def test_register_pin_mismatch_and_pin_guess_throttle(self):
		out, m = self._call_with(_err(400, 133005), svc.register, ACCOUNT, PHONE, "123456")
		self.assertEqual(out["error"]["code"], "pin_mismatch")
		self.assertEqual(m.call_args.kwargs["json"], {"messaging_product": "whatsapp", "pin": "123456"})
		out, _ = self._call_with(_err(400, 133008, details="try again in 5 minutes"), svc.register, ACCOUNT, PHONE, "123456")
		self.assertEqual(out["error"]["code"], "rate_limited")

	def test_subcode_wins_and_register_pin_text_is_not_an_otp_error(self):
		out, _ = self._call_with(_err(400, 100, sub=133005), svc.register, ACCOUNT, PHONE, "123456")
		self.assertEqual(out["error"]["code"], "pin_mismatch")
		out, _ = self._call_with(_err(400, 100, details="PIN code is invalid"), svc.register, ACCOUNT, PHONE, "123456")
		self.assertEqual(out["error"]["code"], "meta_error")

	def test_non_dict_error_body_does_not_crash(self):
		out, _ = self._call_with(_resp(502, ["bad gateway"]), svc.get_status, ACCOUNT, PHONE)
		self.assertEqual(out["error"]["code"], "meta_error")

	def test_non_numeric_phone_id_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			svc.get_status(ACCOUNT, "../x")

	def test_register_needs_reverification(self):
		out, _ = self._call_with(_err(400, 133006), svc.register, ACCOUNT, PHONE, "123456")
		self.assertEqual(out["error"]["code"], "reverification_needed")

	def test_expired_token_flags_reauth(self):
		with patch.object(svc.accounts, "set_reauth_flag") as flag:
			out, _ = self._call_with(_err(401, 190), svc.get_status, ACCOUNT, PHONE)
		self.assertEqual(out["error"]["code"], "token_invalid")
		flag.assert_called_once()

	def test_network_error_is_structured(self):
		with patch.object(svc.requests, "request", side_effect=requests.ConnectionError()):
			out = svc.verify_code(ACCOUNT, PHONE, "123456")
		self.assertEqual(out["error"]["code"], "network_error")

	def test_endpoints_require_write_permission(self):
		with patch.object(api, "check_write", side_effect=frappe.PermissionError):
			for fn, args in ((api.request_phone_code, ()), (api.verify_phone_code, ("123456",)), (api.register_phone, ("123456",))):
				with self.assertRaises(frappe.PermissionError):
					fn(ACCOUNT, PHONE, *args)


class TestPhoneUsername(OnboardingBase):
	"""Username sync + webhook."""

	def _row(self):
		return frappe.db.get_value(
			"WhatsApp Phone Number", {"parent": ACCOUNT, "phone_number_id": PHONE}, ["username", "username_status"], as_dict=True
		)

	def _reset(self, username="", status=""):
		frappe.db.set_value("WhatsApp Phone Number", {"parent": ACCOUNT, "phone_number_id": PHONE}, {"username": username, "username_status": status})

	def test_sync_stores_active_username(self):
		self._reset()
		out, m = self._call_with(_resp(200, {"username": "acme", "status": "ACTIVE"}), svc.get_username, ACCOUNT, PHONE)
		self.assertEqual(m.call_args.args[:2], ("GET", f"https://graph.facebook.com/v26.0/{PHONE}/username"))
		self.assertEqual(self._row(), {"username": "acme", "username_status": "ACTIVE"})

	def test_sync_pending_request_keeps_live_name_and_flags_pending(self):
		self._reset()
		self._call_with(_resp(200, {"username": "acme", "status": "ACTIVE", "requested_username": "acme_new"}), svc.get_username, ACCOUNT, PHONE)
		self.assertEqual(self._row(), {"username": "acme", "username_status": "PENDING"})

	def test_sync_empty_username_clears(self):
		self._reset("old", "ACTIVE")
		self._call_with(_resp(200, {"username": ""}), svc.get_username, ACCOUNT, PHONE)
		self.assertEqual(self._row(), {"username": "", "username_status": ""})

	def test_sync_graph_error_leaves_stored_value(self):
		self._reset("acme", "ACTIVE")
		out, _ = self._call_with(_err(500, 1), svc.get_username, ACCOUNT, PHONE)
		self.assertFalse(out["ok"])
		self.assertEqual(self._row(), {"username": "acme", "username_status": "ACTIVE"})

	def test_sync_foreign_phone_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			svc.get_username(ACCOUNT, "123456789")

	def test_sync_status_is_normalised_to_uppercase(self):
		self._reset()
		self._call_with(_resp(200, {"username": "acme", "status": "reserved"}), svc.get_username, ACCOUNT, PHONE)
		self.assertEqual(self._row(), {"username": "acme", "username_status": "RESERVED"})

	def test_account_job_swallows_errors_and_syncs_rows(self):
		self._reset()
		with patch.object(svc, "get_username", side_effect=RuntimeError("boom")):
			svc.sync_account_usernames(ACCOUNT)  # must not raise
		self._call_with(_resp(200, {"username": "acme", "status": "ACTIVE"}), svc.sync_account_usernames, ACCOUNT)
		self.assertEqual(self._row()["username"], "acme")

	def _webhook(self, decision, requested="acme", display="+1 onb"):
		frappe.db.set_value("WhatsApp Account", ACCOUNT, "waba_id", "onb_waba")
		return svc.apply_username_update(
			{"display_phone_number": display, "decision": decision, "requested_username": requested}, "onb_waba"
		)

	def test_webhook_approved_sets_active_username(self):
		self._reset()
		frappe.db.set_value("WhatsApp Phone Number", {"parent": ACCOUNT, "phone_number_id": PHONE}, "display_phone_number", "+1 555-0100")
		self.assertTrue(self._webhook("APPROVED", "acme", "15550100"))  # digits-only match
		self.assertEqual(self._row(), {"username": "acme", "username_status": "ACTIVE"})

	def test_webhook_rejected_keeps_existing_username_but_flags_when_none(self):
		frappe.db.set_value("WhatsApp Phone Number", {"parent": ACCOUNT, "phone_number_id": PHONE}, "display_phone_number", "+1 555-0100")
		self._reset("live", "PENDING")
		self._webhook("REJECTED", "nope", "15550100")
		self.assertEqual(self._row(), {"username": "live", "username_status": "ACTIVE"})
		self._reset()
		self._webhook("REJECTED", "nope", "15550100")
		self.assertEqual(self._row(), {"username": "", "username_status": "REJECTED"})

	def test_webhook_unknown_number_or_decision_is_ignored(self):
		self.assertFalse(self._webhook("APPROVED", "x", "99999999"))
		self.assertFalse(self._webhook("MAYBE", "x", "15550100"))

	def test_feed_payload_routes_username_update(self):
		from msuite_whatsapp.services.webhooks import inbound_webhook as wa_inbound

		payload = {"entry": [{"id": "w1", "changes": [{"field": "phone_number_username_update", "value": {"decision": "APPROVED"}}]}]}
		with patch.object(wa_inbound.phone_onboarding, "apply_username_update") as m:
			wa_inbound.feed_whatsapp_payload(payload)
		m.assert_called_once_with({"decision": "APPROVED"}, "w1")
