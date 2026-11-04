import unittest
from unittest.mock import MagicMock, patch

import frappe

from msuite_whatsapp.integrations.meta import client

ACC = frappe._dict(name="acc", phones=[frappe._dict(phone_number_id="P1", is_default_outgoing=1), frappe._dict(phone_number_id="P2")])


@patch.object(client.accounts, "get_credentials", return_value=("https://graph.x", "v1", "tok"))
@patch.object(client.accounts, "get_account_doc", return_value=ACC)
class TestPostToMetaPhone(unittest.TestCase):
	@patch.object(client.requests, "post")
	def test_chosen_number_in_url(self, post, *_):
		post.return_value = MagicMock(ok=True, content=b"{}", json=lambda: {"messages": [{"id": "w"}]})
		client.post_to_meta("acc", {"to": "1"}, phone_number_id="P2")
		self.assertEqual(post.call_args.args[0], "https://graph.x/v1/P2/messages")

	@patch.object(client.requests, "post")
	def test_default_number_when_blank(self, post, *_):
		post.return_value = MagicMock(ok=True, content=b"{}", json=lambda: {"messages": [{"id": "w"}]})
		client.post_to_meta("acc", {"to": "1"})
		self.assertEqual(post.call_args.args[0], "https://graph.x/v1/P1/messages")

	@patch.object(client.requests, "post")
	def test_foreign_number_refused_without_http(self, post, *_):
		with self.assertRaisesRegex(client.MetaAPIError, "not on WhatsApp Account"):
			client.post_to_meta("acc", {"to": "1"}, phone_number_id="P9")
		post.assert_not_called()
