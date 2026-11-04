from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

if not getattr(frappe.local, "initialised", False):
	frappe.local.db = MagicMock()

from msuite_whatsapp.integrations.meta.message_provider import build_template_meta


class TestMessageProvider(TestCase):
	def test_build_template_meta_uses_cached_doc_not_get_doc(self):
		fake_template = MagicMock()
		fake_template.parameter_format = "POSITIONAL"
		fake_template.template = ""
		fake_template.sample_values = None
		fake_template.header_type = "NONE"
		fake_template.is_carousel = False
		fake_template.buttons = []

		with (
			patch("frappe.get_doc") as mock_get_doc,
			patch("frappe.get_cached_doc", return_value=fake_template) as mock_get_cached_doc,
		):
			build_template_meta(template_name="greeting_template")

		mock_get_doc.assert_not_called()
		mock_get_cached_doc.assert_called_once_with("WhatsApp Templates", "greeting_template")
