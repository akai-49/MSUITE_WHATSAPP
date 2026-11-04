from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

if not getattr(frappe.local, "initialised", False):
	frappe.local.db = MagicMock()

from msuite_whatsapp.services.bulk.bulk_send_service import build_body_param


class TestBulkSendService(TestCase):
	def test_build_body_param_uses_cached_doc_not_db_get_value(self):
		fake_doc = MagicMock()
		fake_doc.template = "greeting_template"
		fake_doc.template_variables = None

		fake_template = MagicMock()
		fake_template.parameter_format = "POSITIONAL"
		fake_template.template = "Hello {{1}}"

		with (
			patch("frappe.db.get_value") as mock_get_value,
			patch("frappe.get_cached_doc", return_value=fake_template) as mock_get_cached_doc,
		):
			build_body_param(fake_doc, {"mobile_number": "1234567890"})

		mock_get_value.assert_not_called()
		mock_get_cached_doc.assert_called_once_with("WhatsApp Templates", "greeting_template")
