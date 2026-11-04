"""Phase 5.3: Marketing Messages API send path + Cloud API fallback (mocked, no HTTP)."""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from msuite_whatsapp.constants import WHATSAPP_MM_SITE_CONFIG_KEY
from msuite_whatsapp.integrations.meta import client

ACC = frappe._dict(name="acc", phones=[frappe._dict(phone_number_id="P1", is_default_outgoing=1)])
TEMPLATE_BODY = {"messaging_product": "whatsapp", "to": "1", "type": "template", "template": {"name": "promo"}}


def _resp(ok=True, data=None, status=200):
	return MagicMock(ok=ok, status_code=status, content=b"{}", json=lambda: data if data is not None else {"messages": [{"id": "w"}]})


def _err(code=131063, status=400):
	return _resp(False, {"error": {"message": "nope", "code": code}}, status)


@patch.object(client.accounts, "get_credentials", return_value=("https://graph.x", "v1", "tok"))
@patch.object(client.accounts, "get_account_doc", return_value=ACC)
class TestMarketingRouting(unittest.TestCase):
	def _enable(self, value=1):
		p = patch.object(client.frappe, "conf", frappe._dict({WHATSAPP_MM_SITE_CONFIG_KEY: value}))
		p.start()
		self.addCleanup(p.stop)

	def _category(self, cat="MARKETING"):
		p = patch.object(client, "_template_category", return_value=cat)
		p.start()
		self.addCleanup(p.stop)

	@patch.object(client.requests, "post")
	def test_disabled_by_default_uses_messages(self, post, *_):
		post.return_value = _resp()
		client.post_to_meta("acc", dict(TEMPLATE_BODY))
		self.assertTrue(post.call_args.args[0].endswith("/P1/messages"))

	@patch.object(client.requests, "post")
	def test_enabled_marketing_template_uses_mm_endpoint_with_policy(self, post, *_):
		self._enable(); self._category()
		post.return_value = _resp()
		client.post_to_meta("acc", dict(TEMPLATE_BODY))
		self.assertEqual(post.call_count, 1)
		self.assertTrue(post.call_args.args[0].endswith("/P1/marketing_messages"))
		import json
		sent = json.loads(post.call_args.kwargs["data"])
		self.assertEqual(sent["product_policy"], "CLOUD_API_FALLBACK")
		self.assertEqual(sent["to"], "1")

	@patch.object(client.requests, "post")
	def test_enabled_non_template_or_non_marketing_stays_on_cloud_api(self, post, *_):
		self._enable()
		post.return_value = _resp()
		self._category("UTILITY")
		client.post_to_meta("acc", dict(TEMPLATE_BODY))
		client.post_to_meta("acc", {"messaging_product": "whatsapp", "to": "1", "type": "text", "text": {"body": "x"}})
		for call in post.call_args_list:
			self.assertTrue(call.args[0].endswith("/P1/messages"))

	@patch.object(client.requests, "post")
	def test_unknown_template_category_stays_on_cloud_api(self, post, *_):
		self._enable(); self._category(None)
		post.return_value = _resp()
		client.post_to_meta("acc", dict(TEMPLATE_BODY))
		self.assertTrue(post.call_args.args[0].endswith("/P1/messages"))

	@patch.object(client.requests, "post")
	def test_mm_rejection_falls_back_to_cloud_api(self, post, *_):
		self._enable(); self._category()
		post.side_effect = [_err(), _resp()]
		out = client.post_to_meta("acc", dict(TEMPLATE_BODY))
		self.assertEqual(out["messages"][0]["id"], "w")
		self.assertTrue(post.call_args_list[1].args[0].endswith("/P1/messages"))
		self.assertNotIn("product_policy", __import__("json").loads(post.call_args_list[1].kwargs["data"]))

	@patch.object(client.requests, "post")
	def test_transient_mm_error_is_not_resent(self, post, *_):
		"""429/5xx may have been accepted; re-sending on /messages could duplicate."""
		self._enable(); self._category()
		post.return_value = _err(code=4, status=429)
		with self.assertRaises(client.MetaAPIError):
			client.post_to_meta("acc", dict(TEMPLATE_BODY))
		self.assertEqual(post.call_count, 1)

	@patch.object(client.requests, "post")
	def test_network_error_not_resent(self, post, *_):
		self._enable(); self._category()
		post.side_effect = client.requests.ConnectionError("down")
		with self.assertRaises(client.MetaAPIError):
			client.post_to_meta("acc", dict(TEMPLATE_BODY))
		self.assertEqual(post.call_count, 1)

	@patch.object(client.requests, "post")
	def test_falsy_flag_values_are_off(self, post, *_):
		post.return_value = _resp()
		for off in (0, "0", "", None, False):
			with self.subTest(off=off):
				self._enable(off)
				client.post_to_meta("acc", dict(TEMPLATE_BODY))
				self.assertTrue(post.call_args.args[0].endswith("/P1/messages"))

	@patch.object(client.requests, "post")
	def test_caller_body_not_mutated(self, post, *_):
		self._enable(); self._category()
		post.return_value = _resp()
		body = dict(TEMPLATE_BODY)
		client.post_to_meta("acc", body)
		self.assertNotIn("product_policy", body)


@patch.object(client.accounts, "get_credentials", return_value=("https://graph.x", "v1", "tok"))
@patch.object(client.accounts, "get_account_doc", return_value=ACC)
class TestReviewFixes(unittest.TestCase):
	def setUp(self):
		for p in (
			patch.object(client.frappe, "conf", frappe._dict({WHATSAPP_MM_SITE_CONFIG_KEY: 1})),
			patch.object(client, "_template_category", return_value="MARKETING"),
		):
			p.start()
			self.addCleanup(p.stop)

	@patch.object(client.requests, "post")
	def test_non_onboarding_rejections_are_not_resent(self, post, *_):
		"""Auth / validation / window errors would fail identically on /messages."""
		for code, status in ((190, 401), (100, 400), (131047, 400), ("130429", 400)):
			with self.subTest(code=code):
				post.reset_mock()
				post.return_value = _err(code=code, status=status)
				with self.assertRaises(client.MetaAPIError):
					client.post_to_meta("acc", dict(TEMPLATE_BODY))
				self.assertEqual(post.call_count, 1)

	@patch.object(client.requests, "post")
	def test_non_json_gateway_error_raises_meta_error(self, post, *_):
		bad = MagicMock(ok=False, status_code=502, content=b"<html>502</html>")
		bad.json.side_effect = ValueError("not json")
		post.return_value = bad
		with self.assertRaises(client.MetaAPIError) as cm:
			client.post_to_meta("acc", dict(TEMPLATE_BODY))
		self.assertEqual(cm.exception.status_code, 502)
		self.assertEqual(post.call_count, 1)


class TestDownloadMediaHostGuard(unittest.TestCase):
	@patch.object(client.accounts, "get_credentials", return_value=("b", "v", "tok"))
	@patch.object(client.accounts, "get_account_doc", return_value=ACC)
	@patch.object(client.requests, "get")
	def test_untrusted_urls_never_get_the_token(self, get, *_):
		for url in (
			"https://attacker.com/leak",
			"http://169.254.169.254/latest/meta-data/",
			"http://lookaside.fbsbx.com/x",  # not https
			"https://fbsbx.com.evil.com/x",
			"https://evilfbsbx.com/x",
			"ftp://x.fbsbx.com/y",
		):
			with self.subTest(url=url):
				self.assertIsNone(client.download_media(url, "acc"))
		get.assert_not_called()

	@patch.object(client.accounts, "get_credentials", return_value=("b", "v", "tok"))
	@patch.object(client.accounts, "get_account_doc", return_value=ACC)
	@patch.object(client.requests, "get")
	def test_meta_cdn_url_is_downloaded(self, get, *_):
		get.return_value = MagicMock(ok=True, content=b"x")
		self.assertEqual(client.download_media("https://lookaside.fbsbx.com/whatsapp_business/a", "acc"), b"x")
