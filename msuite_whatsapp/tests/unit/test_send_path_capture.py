"""Task 3: `send_to_meta` reports which route carried a message (mocked HTTP, no network)."""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from msuite_whatsapp.constants import WHATSAPP_SEND_PATH_CLOUD_API, WHATSAPP_SEND_PATH_MARKETING_MESSAGES
from msuite_whatsapp.constants import WHATSAPP_MM_SITE_CONFIG_KEY
from msuite_whatsapp.integrations.meta import client

ACC = frappe._dict(name="acc", phones=[frappe._dict(phone_number_id="P1", is_default_outgoing=1)])
TEMPLATE_BODY = {"messaging_product": "whatsapp", "to": "1", "type": "template", "template": {"name": "promo"}}
TEXT_BODY = {"messaging_product": "whatsapp", "to": "1", "type": "text", "text": {"body": "x"}}
OK_JSON = {"messages": [{"id": "wamid.1"}]}


def _resp(ok=True, data=None, status=200):
	return MagicMock(ok=ok, status_code=status, content=b"{}", json=lambda: data if data is not None else OK_JSON)


def _err(code, status=400):
	return _resp(False, {"error": {"message": "nope", "code": code}}, status)


@patch.object(client.accounts, "get_credentials", return_value=("https://graph.x", "v1", "tok"))
@patch.object(client.accounts, "get_account_doc", return_value=ACC)
@patch.object(client.requests, "post")
class TestSendToMeta(unittest.TestCase):
	def _enable(self, category="MARKETING", flag=1):
		for target in (
			patch.object(client.frappe, "conf", frappe._dict({WHATSAPP_MM_SITE_CONFIG_KEY: flag})),
			patch.object(client, "_template_category", return_value=category),
		):
			target.start()
			self.addCleanup(target.stop)

	def test_mm_success_reports_marketing_messages(self, post, *_):
		self._enable()
		post.return_value = _resp()
		resp, path = client.send_to_meta("acc", dict(TEMPLATE_BODY))
		self.assertEqual(path, WHATSAPP_SEND_PATH_MARKETING_MESSAGES)
		self.assertEqual(resp, OK_JSON)

	def test_fallback_reports_cloud_api(self, post, *_):
		self._enable()
		post.side_effect = [_err(131063), _resp()]
		_, path = client.send_to_meta("acc", dict(TEMPLATE_BODY))
		self.assertEqual(path, WHATSAPP_SEND_PATH_CLOUD_API)
		self.assertEqual(post.call_count, 2)

	def test_non_fallback_error_raises_and_does_not_resend(self, post, *_):
		self._enable()
		post.return_value = _err(100)
		with self.assertRaises(client.MetaAPIError):
			client.send_to_meta("acc", dict(TEMPLATE_BODY))
		self.assertEqual(post.call_count, 1)

	def test_site_flag_off_reports_cloud_api(self, post, *_):
		self._enable(flag=0)
		post.return_value = _resp()
		_, path = client.send_to_meta("acc", dict(TEMPLATE_BODY))
		self.assertEqual(path, WHATSAPP_SEND_PATH_CLOUD_API)

	def test_non_template_body_reports_cloud_api(self, post, *_):
		self._enable()
		post.return_value = _resp()
		_, path = client.send_to_meta("acc", dict(TEXT_BODY))
		self.assertEqual(path, WHATSAPP_SEND_PATH_CLOUD_API)

	def test_non_marketing_category_reports_cloud_api(self, post, *_):
		self._enable(category="UTILITY")
		post.return_value = _resp()
		_, path = client.send_to_meta("acc", dict(TEMPLATE_BODY))
		self.assertEqual(path, WHATSAPP_SEND_PATH_CLOUD_API)

	def test_response_without_messages_is_returned_untouched(self, post, *_):
		post.return_value = _resp(data={"contacts": []})
		resp, path = client.send_to_meta("acc", dict(TEXT_BODY))
		self.assertEqual(resp, {"contacts": []})
		self.assertEqual(path, WHATSAPP_SEND_PATH_CLOUD_API)

	def test_post_to_meta_wrapper_returns_only_the_response(self, post, *_):
		self._enable()
		post.return_value = _resp()
		self.assertEqual(client.post_to_meta("acc", dict(TEMPLATE_BODY)), OK_JSON)

	def test_unknown_phone_number_raises_before_any_http(self, post, *_):
		with self.assertRaises(client.MetaAPIError):
			client.send_to_meta("acc", dict(TEXT_BODY), phone_number_id="P-unknown")
		post.assert_not_called()
