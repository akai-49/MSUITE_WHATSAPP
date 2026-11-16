# Copyright (c) 2022, Shridhar Patil and Contributors
# See license.txt

import json
from unittest.mock import patch, MagicMock

import frappe

from msuite_whatsapp.constants import GRAPH_API_VERSION
from frappe.tests import IntegrationTestCase

# Cuts the auto test-record dependency walk at three Links that all lead into
# erpnext's accounts chain, down to `Payment Gateway` (this bench's `payments`
# app isn't installed): `DocType` (Email Template -> Email Account -> Company ...),
# WhatsApp Account and WhatsApp Flow (-> CRM Organization ...).
# Nothing here needs those records; setUpClass builds its own account.
# Same pattern as ads/doctype/ad_set/test_ad_set.py.
EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = ["DocType", "WhatsApp Account", "WhatsApp Flow"]


class TestWhatsAppTemplates(IntegrationTestCase):
    """Tests for WhatsApp Templates doctype.

    Meta HTTP calls and payload building now live in
    `providers.meta.template_provider` / `services.template_service` /
    `services.template_sync_service` (see WHATSAPP_REFACTOR_PLAN.md §4-7) —
    patches target those modules instead of the doctype controller.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._ensure_test_account()

    @classmethod
    def _ensure_test_account(cls):
        if not frappe.db.exists("WhatsApp Account", "Test WA Tmpl Account"):
            account = frappe.get_doc({
                "doctype": "WhatsApp Account",
                "account_name": "Test WA Tmpl Account",
                "status": "Active",
                "business_id": "tmpl_test_business_id",
                "app_id": "tmpl_test_app_id",
                "phones": [{
                    "phone_number_id": "tmpl_test_phone_id",
                    "display_phone_number": "+1 tmpl",
                    "status": "Active",
                    "is_default_incoming": 1,
                    "is_default_outgoing": 1,
                }],
            })
            account.insert(ignore_permissions=True)
            frappe.db.commit()

    def setUp(self):
        # Set password within each test's transaction scope
        from frappe.utils.password import set_encrypted_password
        set_encrypted_password("WhatsApp Account", "Test WA Tmpl Account", "test_tmpl_token", "token")
        # Clear ALL defaults then set ours (db.set_value bypasses on_update hooks)
        frappe.db.sql("UPDATE `tabWhatsApp Phone Number` SET is_default_outgoing=0, is_default_incoming=0")
        frappe.db.sql(
            "UPDATE `tabWhatsApp Phone Number` SET is_default_outgoing=1, is_default_incoming=1 WHERE parent=%s",
            "Test WA Tmpl Account",
        )


    def tearDown(self):
        # Use SQL-level delete to avoid triggering on_trash (which calls get_settings)
        frappe.db.delete("WhatsApp Templates", {"template_name": ["like", "test_tmpl_%"]})
        frappe.db.delete("WhatsApp Templates", {"template_name": ["like", "test_msg_template%"]})
        frappe.db.commit()

    def _make_template_without_hooks(self, **kwargs):
        """Create a template directly in DB to avoid Meta API calls."""
        template_name = kwargs.get("template_name", "test_tmpl_basic")
        language_code = kwargs.get("language_code", "en")
        doc = frappe.get_doc({
            "doctype": "WhatsApp Templates",
            "template_name": template_name,
            "actual_name": template_name.lower().replace(" ", "_"),
            "template": kwargs.get("template", "Hello {{1}}"),
            "category": kwargs.get("category", "TRANSACTIONAL"),
            "language": kwargs.get("language", frappe.db.get_value("Language", {"language_code": "en"}) or "en"),
            "language_code": language_code,
            "whatsapp_account": kwargs.get("whatsapp_account", "Test WA Tmpl Account"),
            "status": kwargs.get("status", "APPROVED"),
            "id": kwargs.get("id", f"tmpl_id_{template_name}"),
            "header_type": kwargs.get("header_type", ""),
            "header": kwargs.get("header", ""),
            "footer": kwargs.get("footer", ""),
            "sample_values": kwargs.get("sample_values", ""),
        })
        doc.db_insert()
        frappe.db.commit()
        return frappe.get_doc("WhatsApp Templates", doc.name)

    def test_template_autoname(self):
        """Test template autoname format: template_name-language_code."""
        doc = self._make_template_without_hooks(template_name="test_tmpl_autoname")
        self.assertEqual(doc.name, "test_tmpl_autoname-en")

    @patch("msuite_whatsapp.integrations.meta.template_provider.make_post_request")
    def test_language_code_set_on_validate(self, mock_post):
        """Test language_code is derived from language field on validate."""
        mock_post.return_value = {}
        doc = self._make_template_without_hooks(template_name="test_tmpl_langcode")
        doc.language_code = ""
        doc.language = frappe.db.get_value("Language", {"language_code": "en"}) or "en"
        doc.validate()
        self.assertTrue(len(doc.language_code) > 0)

    def test_set_whatsapp_account_default(self):
        """Test whatsapp_account is set to default if missing."""
        doc = self._make_template_without_hooks(
            template_name="test_tmpl_default_acct",
            whatsapp_account=""
        )
        doc.whatsapp_account = ""
        doc.set_whatsapp_account()
        self.assertTrue(len(doc.whatsapp_account) > 0)

    def test_get_absolute_path_public_files(self):
        """Test the provider's absolute-path resolver for public files."""
        from msuite_whatsapp.integrations.meta.template_provider import _get_absolute_path
        path = _get_absolute_path("/files/test_image.png")
        self.assertIn("/public/files/test_image.png", path)

    def test_get_absolute_path_private_files(self):
        """Test the provider's absolute-path resolver for private files."""
        from msuite_whatsapp.integrations.meta.template_provider import _get_absolute_path
        path = _get_absolute_path("/private/files/test_doc.pdf")
        self.assertIn("/private/files/test_doc.pdf", path)

    def test_build_header_text(self):
        """Test the provider's header builder for TEXT header type."""
        from msuite_whatsapp.integrations.meta.template_provider import _build_header
        doc = self._make_template_without_hooks(
            template_name="test_tmpl_hdr_text",
            header_type="TEXT",
            header="Order Update"
        )
        header = _build_header(doc)
        self.assertEqual(header["type"], "HEADER")
        self.assertEqual(header["format"], "TEXT")
        self.assertEqual(header["text"], "Order Update")

    def test_build_header_text_with_sample(self):
        """Test the provider's header builder for TEXT header with sample values."""
        from msuite_whatsapp.integrations.meta.template_provider import _build_header
        doc = self._make_template_without_hooks(
            template_name="test_tmpl_hdr_sample",
            header_type="TEXT",
            header="Hello {{1}}",
            sample_values="John"
        )
        doc.sample = "John"
        header = _build_header(doc)
        self.assertEqual(header["format"], "TEXT")
        self.assertIn("example", header)
        self.assertEqual(header["example"]["header_text"], ["John"])

    def test_build_components_catalog_template(self):
        """CATALOGUE templates get BODY (+FOOTER) + one CATALOG button, nothing else."""
        from msuite_whatsapp.integrations.meta.template_provider import build_components
        doc = self._make_template_without_hooks(
            template_name="test_tmpl_catalog",
            template="Browse our latest collection",
            category="MARKETING",
            footer="Powered by us",
            header_type="TEXT",  # should be ignored for catalog templates
            header="ignored",
        )
        doc.template_type = "CATALOGUE"  # helper only sets a fixed field subset
        components = build_components(doc)
        types = [c["type"] for c in components]
        self.assertEqual(types, ["BODY", "FOOTER", "BUTTONS"])
        self.assertNotIn("HEADER", types)
        btns = components[-1]["buttons"]
        self.assertEqual(btns, [{"type": "CATALOG", "text": "View catalog"}])

    def test_get_credentials(self):
        """Test the provider loads WhatsApp Account credentials."""
        from msuite_whatsapp.integrations.meta.template_provider import get_credentials
        doc = self._make_template_without_hooks(template_name="test_tmpl_settings")
        creds = get_credentials(doc.whatsapp_account)
        self.assertEqual(creds["url"], "https://graph.facebook.com")
        self.assertEqual(creds["version"], GRAPH_API_VERSION)
        self.assertEqual(creds["business_id"], "tmpl_test_business_id")

    @patch("msuite_whatsapp.integrations.meta.template_provider.make_post_request")
    def test_after_insert_creates_template_on_meta(self, mock_post):
        """Test after_insert sends template to Meta API."""
        mock_post.return_value = {
            "id": "new_template_id_123",
            "status": "PENDING",
        }

        doc = frappe.get_doc({
            "doctype": "WhatsApp Templates",
            "template_name": "test_tmpl_insert",
            "template": "Test body {{1}}",
            "sample_values": "World",
            "category": "TRANSACTIONAL",
            "language": frappe.db.get_value("Language", {"language_code": "en"}) or "en",
            "language_code": "en",
            "whatsapp_account": "Test WA Tmpl Account",
        })
        doc.insert(ignore_permissions=True)

        self.assertTrue(mock_post.called)
        call_args = mock_post.call_args
        sent_data = json.loads(call_args.kwargs.get("data", call_args[1].get("data", "")))
        self.assertEqual(sent_data["name"], "test_tmpl_insert")
        self.assertEqual(sent_data["language"], "en")
        self.assertEqual(sent_data["category"], "TRANSACTIONAL")
        self.assertTrue(any(c["type"] == "BODY" for c in sent_data["components"]))

    @patch("msuite_whatsapp.integrations.meta.template_provider.make_post_request")
    def test_after_insert_with_footer(self, mock_post):
        """Test template creation includes footer in components."""
        mock_post.return_value = {"id": "tmpl_footer_id", "status": "PENDING"}

        doc = frappe.get_doc({
            "doctype": "WhatsApp Templates",
            "template_name": "test_tmpl_footer",
            "template": "Body text",
            "footer": "Reply STOP to opt out",
            "category": "MARKETING",
            "language": frappe.db.get_value("Language", {"language_code": "en"}) or "en",
            "language_code": "en",
            "whatsapp_account": "Test WA Tmpl Account",
        })
        doc.insert(ignore_permissions=True)

        call_args = mock_post.call_args
        sent_data = json.loads(call_args.kwargs.get("data", call_args[1].get("data", "")))
        footer_components = [c for c in sent_data["components"] if c["type"] == "FOOTER"]
        self.assertEqual(len(footer_components), 1)
        self.assertEqual(footer_components[0]["text"], "Reply STOP to opt out")

    @patch("msuite_whatsapp.integrations.meta.template_provider.make_post_request")
    def test_after_insert_with_buttons(self, mock_post):
        """Test template creation includes buttons."""
        mock_post.return_value = {"id": "tmpl_btn_id", "status": "PENDING"}

        doc = frappe.get_doc({
            "doctype": "WhatsApp Templates",
            "template_name": "test_tmpl_buttons",
            "template": "Click below",
            "category": "TRANSACTIONAL",
            "language": frappe.db.get_value("Language", {"language_code": "en"}) or "en",
            "language_code": "en",
            "whatsapp_account": "Test WA Tmpl Account",
        })
        doc.append("buttons", {
            "button_type": "Visit Website",
            "button_label": "Visit",
            "website_url": "https://example.com",
            "url_type": "Static",
        })
        doc.append("buttons", {
            "button_type": "Call Phone",
            "button_label": "Call",
            "phone_number": "+15550001111",
        })
        doc.insert(ignore_permissions=True)

        call_args = mock_post.call_args
        sent_data = json.loads(call_args.kwargs.get("data", call_args[1].get("data", "")))
        button_components = [c for c in sent_data["components"] if c["type"] == "BUTTONS"]
        self.assertEqual(len(button_components), 1)
        buttons = button_components[0]["buttons"]
        self.assertEqual(len(buttons), 2)
        self.assertEqual(buttons[0]["type"], "URL")
        self.assertEqual(buttons[1]["type"], "PHONE_NUMBER")

    @patch("msuite_whatsapp.integrations.meta.template_provider.make_post_request")
    @patch("msuite_whatsapp.integrations.meta.template_provider.make_request")
    def test_on_trash_deletes_from_meta(self, mock_request, mock_post):
        """Test on_trash calls Meta API to delete template."""
        mock_post.return_value = {"id": "tmpl_trash_id", "status": "PENDING"}

        doc = frappe.get_doc({
            "doctype": "WhatsApp Templates",
            "template_name": "test_tmpl_trash",
            "template": "Delete me",
            "category": "TRANSACTIONAL",
            "language": frappe.db.get_value("Language", {"language_code": "en"}) or "en",
            "language_code": "en",
            "whatsapp_account": "Test WA Tmpl Account",
        })
        doc.insert(ignore_permissions=True)

        mock_request.return_value = {}
        doc.delete()

        # Verify DELETE was called on Meta API
        self.assertTrue(mock_request.called)
        delete_call = mock_request.call_args
        self.assertEqual(delete_call[0][0], "DELETE")
        self.assertIn("message_templates", delete_call[0][1])

    def test_on_trash_graceful_missing_account(self):
        """Test on_trash handles missing or deleted whatsapp_account gracefully."""
        doc = self._make_template_without_hooks(
            template_name="test_tmpl_trash_no_acct",
            whatsapp_account="Non Existent Account",
        )
        
        # This shouldn't throw AttributeError or DoesNotExistError
        try:
            doc.delete()
        except Exception as e:
            self.fail(f"doc.delete() raised an exception: {e}")

    def test_on_trash_graceful_null_account(self):
        """Test on_trash handles null whatsapp_account gracefully."""
        doc = self._make_template_without_hooks(
            template_name="test_tmpl_trash_null_acct",
            whatsapp_account="",
        )
        # Force whatsapp_account to None in the DB & loaded document
        frappe.db.set_value("WhatsApp Templates", doc.name, "whatsapp_account", None)
        doc.reload()
        
        # This shouldn't throw AttributeError
        try:
            doc.delete()
        except Exception as e:
            self.fail(f"doc.delete() raised an exception: {e}")

    @patch("frappe.model.document.Document.get_password", return_value="mock_token")
    @patch("msuite_whatsapp.services.templates.template_sync_service.make_request")
    def test_fetch_templates_from_meta(self, mock_get, mock_get_password):
        """Test the fetch (sync_all_accounts) whitelisted function."""
        mock_get.return_value = {
            "data": [
                {
                    "name": "test_tmpl_fetched",
                    "status": "APPROVED",
                    "language": "en",
                    "category": "UTILITY",
                    "id": "fetched_tmpl_id",
                    "components": [
                        {"type": "BODY", "text": "Hello {{1}}, your order is ready"},
                        {"type": "FOOTER", "text": "Thank you"},
                    ]
                }
            ]
        }

        from msuite_whatsapp.services.templates.template_sync_service import sync_all_accounts as fetch
        result = fetch()
        self.assertEqual(result, "Successfully fetched templates from meta")

    def test_upsert_doc_without_hooks(self):
        """Test upsert_without_hooks inserts and updates correctly."""
        from msuite_whatsapp.queries.template_repository import upsert_without_hooks

        doc = self._make_template_without_hooks(template_name="test_tmpl_upsert")

        # Update template text
        doc.template = "Updated body text"
        upsert_without_hooks(doc, "WhatsApp Button", "buttons")

        doc.reload()
        self.assertEqual(doc.template, "Updated body text")
