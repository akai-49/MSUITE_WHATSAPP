"""Tests for header-based auth and 401/403/token-code handling in WhatsApp analytics sync (D6).

All HTTP is mocked; no live Meta calls.
"""

import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import requests

from msuite_whatsapp.constants import (
	ANALYTICS_BACKFILL_DAYS,
	TEMPLATE_ANALYTICS_BATCH_SIZE,
	TEMPLATE_ANALYTICS_DEFAULT_DAYS,
	TEMPLATE_ANALYTICS_MAX_LOOKBACK_DAYS,
)
from msuite_whatsapp.services.analytics import sync

MODULE = "msuite_whatsapp.services.analytics.sync"
TOKEN = "EAAB-secret-token-123"
URL = "https://graph.example/v26.0/waba1"
ACCOUNT = "ACC-1"
FIXED_TODAY = "2026-10-20"


def _resp(body, status=200):
	"""Build a fake requests.Response returning `body` as JSON."""
	resp = MagicMock()
	resp.status_code = status
	resp.json.return_value = body
	return resp


def _err_body(code, message="boom"):
	return {"error": {"message": message, "code": code}}


class TestCallMetaApiAuth(unittest.TestCase):
	def _call(self, resp=None, side_effect=None, account=ACCOUNT, fn=sync._call_meta_api):
		with patch(f"{MODULE}.requests.get", return_value=resp, side_effect=side_effect) as get, patch(
			f"{MODULE}.set_reauth_flag"
		) as flag:
			out = fn(URL, {"fields": "x", "access_token": TOKEN}, account)
		return out, get, flag

	def test_token_in_header_never_in_params(self):
		out, get, _ = self._call(_resp({"ok": 1}))
		self.assertEqual(out, {"ok": 1})
		kwargs = get.call_args.kwargs
		self.assertNotIn("access_token", kwargs["params"])
		self.assertEqual(kwargs["headers"]["Authorization"], f"Bearer {TOKEN}")
		self.assertEqual(kwargs["params"]["fields"], "x")

	def test_caller_params_not_mutated(self):
		params = {"fields": "x", "access_token": TOKEN}
		with patch(f"{MODULE}.requests.get", return_value=_resp({})), patch(f"{MODULE}.set_reauth_flag"):
			sync._call_meta_api(URL, params, ACCOUNT)
		self.assertEqual(params["access_token"], TOKEN)

	def test_uses_named_timeout(self):
		from msuite_whatsapp.constants import META_ANALYTICS_HTTP_TIMEOUT

		_, get, _ = self._call(_resp({}))
		self.assertEqual(get.call_args.kwargs["timeout"], META_ANALYTICS_HTTP_TIMEOUT)

	def test_http_401_flags_reauth_once(self):
		out, _, flag = self._call(_resp(_err_body(1, "bad"), 401))
		self.assertIsNone(out)
		flag.assert_called_once()
		self.assertEqual(flag.call_args.args[0], ACCOUNT)
		self.assertIs(flag.call_args.kwargs["needs_reauth"], True)

	def test_http_401_non_json_body_still_flags(self):
		resp = _resp(None, 401)
		resp.json.side_effect = ValueError("no json")
		out, _, flag = self._call(resp)
		self.assertIsNone(out)
		flag.assert_called_once()

	def test_token_code_with_http_200_flags_reauth(self):
		for code in (190, 102):
			out, _, flag = self._call(_resp(_err_body(code), 200))
			self.assertIsNone(out)
			flag.assert_called_once()

	def _call_logged(self, resp):
		with patch(f"{MODULE}.requests.get", return_value=resp), patch(f"{MODULE}.set_reauth_flag") as flag, patch(
			f"{MODULE}.logger"
		) as log:
			out = sync._call_meta_api(URL, {"access_token": TOKEN}, ACCOUNT)
		self.last_log = log
		return out, None, flag

	def test_403_single_warning(self):
		out, _, flag = self._call_logged(_resp(_err_body(1), 403))
		self.assertIsNone(out)
		flag.assert_not_called()
		self.assertEqual(self.last_log.warning.call_count, 1)

	def test_permission_codes_no_reauth(self):
		for code in (10, 200, 250, 299):
			out, _, flag = self._call(_resp(_err_body(code), 200))
			self.assertIsNone(out)
			flag.assert_not_called()

	def test_code_300_is_not_permission_and_not_reauth(self):
		_, _, flag = self._call(_resp(_err_body(300), 400))
		flag.assert_not_called()

	def test_no_account_name_never_flags(self):
		_, _, flag = self._call(_resp(_err_body(190), 401), account=None)
		flag.assert_not_called()

	def test_network_errors_return_none(self):
		for exc in (requests.Timeout("t"), requests.ConnectionError("c")):
			out, _, flag = self._call(side_effect=exc)
			self.assertIsNone(out)
			flag.assert_not_called()

	def test_non_json_200_returns_none(self):
		resp = _resp(None, 200)
		resp.json.side_effect = ValueError("no json")
		out, _, _ = self._call(resp)
		self.assertIsNone(out)

	def test_token_never_logged(self):
		cases = [
			dict(resp=_resp(_err_body(190, f"Invalid token {TOKEN}"), 401)),
			dict(resp=_resp(_err_body(10, f"nope {TOKEN}"), 403)),
			dict(side_effect=requests.ConnectionError(f"failed ?access_token={TOKEN}")),
		]
		for kw in cases:
			with patch(f"{MODULE}.logger") as log:
				with patch(f"{MODULE}.requests.get", return_value=kw.get("resp"), side_effect=kw.get("side_effect")), patch(
					f"{MODULE}.set_reauth_flag"
				) as flag:
					sync._call_meta_api(URL, {"access_token": TOKEN}, ACCOUNT)
			logged = " ".join(str(c) for m in (log.warning, log.error, log.info) for c in m.call_args_list)
			self.assertNotIn(TOKEN, logged)
			for call in flag.call_args_list:
				self.assertNotIn(TOKEN, call.kwargs.get("error", ""))

	def test_with_error_variant_exposes_status_and_code(self):
		for status, code in ((401, 190), (403, 10), (400, 100), (429, 4)):
			(data, err), _, _ = self._call(_resp(_err_body(code), status), fn=sync._call_meta_api_with_error)
			self.assertIsNone(data)
			self.assertEqual(err["status_code"], status)
			self.assertEqual(err["code"], code)

	def test_with_error_variant_success(self):
		(data, err), _, _ = self._call(_resp({"data": []}), fn=sync._call_meta_api_with_error)
		self.assertEqual(data, {"data": []})
		self.assertIsNone(err)

	def test_with_error_variant_exception(self):
		(data, err), _, _ = self._call(side_effect=requests.Timeout("t"), fn=sync._call_meta_api_with_error)
		self.assertIsNone(data)
		self.assertTrue(err["exception"])


class TestSyncTemplateAnalytics(unittest.TestCase):
	def _run(self, responses, days=None, ids=None):
		"""Run sync_template_analytics with mocked responses; return (get, snapshot, flag)."""
		account = MagicMock()
		account.is_enabled_for_insights = 1
		account.get_password.return_value = TOKEN
		account.waba_id = "waba1"
		ids = ids if ids is not None else [str(i) for i in range(TEMPLATE_ANALYTICS_BATCH_SIZE * 2 + 1)]
		kwargs = {} if days is None else {"days": days}
		with patch(f"{MODULE}.today", return_value=FIXED_TODAY), patch(
			f"{MODULE}.frappe.get_doc", return_value=account
		), patch(
			f"{MODULE}.frappe.get_all", return_value=ids
		), patch(f"{MODULE}.requests.get", side_effect=responses) as get, patch(
			f"{MODULE}._save_snapshot"
		) as snap, patch(f"{MODULE}.set_reauth_flag") as flag:
			sync.sync_template_analytics("ACC-1", **kwargs)
		return get, snap, flag

	def test_token_header_only_and_data_saved(self):
		get, snap, _ = self._run([_resp({"data": [{"a": 1}]})] * 3)
		self.assertEqual(get.call_count, 3)
		for call in get.call_args_list:
			self.assertNotIn("access_token", call.kwargs["params"])
			self.assertEqual(call.kwargs["headers"]["Authorization"], f"Bearer {TOKEN}")
		snap.assert_called_once()

	def test_401_stops_batches_flags_and_writes_nothing(self):
		get, snap, flag = self._run([_resp(_err_body(190), 401), _resp({"data": [1]}), _resp({"data": [1]})])
		self.assertEqual(get.call_count, 1)
		snap.assert_not_called()
		flag.assert_called_once()

	def test_403_no_flag_no_snapshot(self):
		_, snap, flag = self._run([_resp(_err_body(10), 403)] * 3)
		snap.assert_not_called()
		flag.assert_not_called()

	def test_non_auth_error_continues_next_batches(self):
		get, snap, _ = self._run([_resp(_err_body(100), 400), _resp({"data": [1]}), _resp({"data": [2]})])
		self.assertEqual(get.call_count, 3)
		snap.assert_called_once()

	def test_days_clamped(self):
		for days in (0, -5, 10**6):
			get, _, _ = self._run([_resp({"data": []})], days=days, ids=["1"])
			params = get.call_args.kwargs["params"]
			span = (date.fromisoformat(params["end"]) - date.fromisoformat(params["start"])).days
			self.assertLessEqual(span, TEMPLATE_ANALYTICS_MAX_LOOKBACK_DAYS)
			self.assertGreaterEqual(span, 0)

	def test_default_days_is_named_constant(self):
		self.assertEqual(TEMPLATE_ANALYTICS_DEFAULT_DAYS, ANALYTICS_BACKFILL_DAYS)
		get, _, _ = self._run([_resp({"data": []})], ids=["1"])
		params = get.call_args.kwargs["params"]
		span = (date.fromisoformat(params["end"]) - date.fromisoformat(params["start"])).days
		self.assertEqual(span, TEMPLATE_ANALYTICS_DEFAULT_DAYS)

	def test_regression_old_behaviour_token_in_params_is_detected(self):
		"""If the token were sent in params (old behaviour) the header-only assertions must fail."""
		get, _, _ = self._run([_resp({"data": []})], ids=["1"])
		params = dict(get.call_args.kwargs["params"], access_token=TOKEN)
		with self.assertRaises(AssertionError):
			self.assertNotIn("access_token", params)
