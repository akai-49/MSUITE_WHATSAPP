# Copyright (c) 2025, Shridhar Patil and Contributors
# See license.txt

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from msuite_whatsapp.api.v1.app.bulk_messaging import (
	get_progress,
	import_recipients,
	retry_failed,
	schedule_bulk_messages,
)


# `User` is not an allowed import source (utils/import_guard.py), so the import
# tests read from a Contact fixture instead.
CONTACT_FIRST_NAME = "BulkUtilImportContact"
CONTACT_MOBILE = "919900000001"


class TestBulkMessagingUtils(IntegrationTestCase):
    """Tests for bulk messaging utility functions."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._ensure_test_account()
        cls._ensure_test_template()

    @classmethod
    def _ensure_test_account(cls):
        if not frappe.db.exists("WhatsApp Account", "Test WA BulkUtil Account"):
            account = frappe.get_doc({
                "doctype": "WhatsApp Account",
                "account_name": "Test WA BulkUtil Account",
                "status": "Active",
                "business_id": "bulkutil_test_business_id",
                "app_id": "bulkutil_test_app_id",
                "phones": [{
                    "phone_number_id": "bulkutil_test_phone_id",
                    "display_phone_number": "+1 bulkutil",
                    "status": "Active",
                    "is_default_incoming": 1,
                    "is_default_outgoing": 1,
                }],
            })
            account.insert(ignore_permissions=True)
            frappe.db.commit()

    @classmethod
    def _ensure_test_template(cls):
        template_name = "test_bulkutil_template-en"
        if not frappe.db.exists("WhatsApp Templates", template_name):
            doc = frappe.get_doc({
                "doctype": "WhatsApp Templates",
                "template_name": "test_bulkutil_template",
                "actual_name": "test_bulkutil_template",
                "template": "Hello {{1}}",
                "sample_values": "User",
                "category": "MARKETING",
                "language": frappe.db.get_value("Language", {"language_code": "en"}) or "en",
                "language_code": "en",
                "whatsapp_account": "Test WA BulkUtil Account",
                "status": "APPROVED",
                "id": "test_bulkutil_template_id",
            })
            doc.db_insert()
            frappe.db.commit()

    def setUp(self):
        # Set password within each test's transaction scope
        from frappe.utils.password import set_encrypted_password
        set_encrypted_password("WhatsApp Account", "Test WA BulkUtil Account", "test_bulkutil_token", "token")
        # Clear ALL defaults then set ours (db.set_value bypasses on_update hooks)
        frappe.db.sql("UPDATE `tabWhatsApp Phone Number` SET is_default_outgoing=0, is_default_incoming=0")
        frappe.db.sql(
            "UPDATE `tabWhatsApp Phone Number` SET is_default_outgoing=1, is_default_incoming=1 WHERE parent=%s",
            "Test WA BulkUtil Account",
        )


    def tearDown(self):
        for name in frappe.get_all("Bulk WhatsApp Message", filters={"title": ["like", "Test BulkUtil%"]}, pluck="name"):
            frappe.db.set_value("Bulk WhatsApp Message", name, "docstatus", 2)
            frappe.delete_doc("Bulk WhatsApp Message", name, force=True)
        for name in frappe.get_all("Contact", filters={"first_name": CONTACT_FIRST_NAME}, pluck="name"):
            frappe.delete_doc("Contact", name, force=True)
        for name in frappe.get_all("WhatsApp Recipient List", filters={"list_name": ["like", "Test BulkUtil%"]}, pluck="name"):
            frappe.delete_doc("WhatsApp Recipient List", name, force=True)
        frappe.db.commit()

    def _make_bulk_message(self, title="Test BulkUtil Msg"):
        """Create a bulk message for testing."""
        doc = frappe.get_doc({
            "doctype": "Bulk WhatsApp Message",
            "title": title,
            "recipient_type": "Individual",
            "use_template": 1,
            "template": "test_bulkutil_template-en",
            "variable_type": "Common",
            "whatsapp_account": "Test WA BulkUtil Account",
        })
        doc.append("recipients", {"mobile_number": "919900112233", "recipient_name": "User 1"})
        doc.append("recipients", {"mobile_number": "919900112244", "recipient_name": "User 2"})
        doc.insert(ignore_permissions=True)
        return doc

    def test_get_progress(self):
        """Test get_progress whitelisted function."""
        doc = self._make_bulk_message(title="Test BulkUtil Progress")
        progress = get_progress(doc.name)
        self.assertIn("total", progress)
        self.assertEqual(progress["total"], 2)

    def test_retry_failed_util(self):
        """Test retry_failed whitelisted function.

        `WhatsApp Message` was migrated to `Channel Message`
        (patches/migrate_whatsapp_message_to_channel_message.py) — the
        doctype this test used to insert a fixture into no longer
        exists. bulk_messaging.retry_failed() just wraps
        `doc.retry_failed()`, which with zero failed messages msgprints
        and returns 0 without touching the network — no failed-message
        fixture or HTTP mock is needed to exercise the wrapper itself.
        """
        doc = self._make_bulk_message(title="Test BulkUtil Retry")

        result = retry_failed(doc.name)
        self.assertEqual(result, {"requeued": 0})

    def _make_import_contact(self):
        """Create a Contact whose mobile_no is populated (via phone_nos, as core requires)."""
        return frappe.get_doc({
            "doctype": "Contact",
            "first_name": CONTACT_FIRST_NAME,
            "phone_nos": [{"phone": CONTACT_MOBILE, "is_primary_mobile_no": 1}],
        }).insert(ignore_permissions=True)

    def test_import_recipients_rejects_non_allowlisted_doctype(self):
        """Security regression (audit C5): User must not be importable."""
        rec_list = frappe.get_doc({"doctype": "WhatsApp Recipient List", "list_name": "Test BulkUtil Import Deny"})
        rec_list.append("recipients", {"mobile_number": "919900000099"})
        rec_list.insert(ignore_permissions=True)

        with self.assertRaises(frappe.PermissionError):
            import_recipients(list_name=rec_list.name, doctype="User", mobile_field="mobile_no")

    def test_import_recipients(self):
        """Test import_recipients whitelisted function."""
        rec_list = frappe.get_doc({
            "doctype": "WhatsApp Recipient List",
            "list_name": "Test BulkUtil Import List",
        })
        rec_list.append("recipients", {"mobile_number": "919900000099"})
        rec_list.insert(ignore_permissions=True)

        self._make_import_contact()
        count = import_recipients(
            list_name=rec_list.name,
            doctype="Contact",
            mobile_field="mobile_no",
            name_field="full_name",
            filters=json.dumps({"first_name": CONTACT_FIRST_NAME}),
            limit=5,
        )
        self.assertGreater(count, 0)

    def test_import_recipients_with_string_filters(self):
        """Test import_recipients handles string filters."""
        rec_list = frappe.get_doc({
            "doctype": "WhatsApp Recipient List",
            "list_name": "Test BulkUtil Import Str",
        })
        rec_list.append("recipients", {"mobile_number": "919900000099"})
        rec_list.insert(ignore_permissions=True)

        # Pass filters as string (as it would come from a whitelisted call)
        self._make_import_contact()
        count = import_recipients(
            list_name=rec_list.name,
            doctype="Contact",
            mobile_field="mobile_no",
            filters=json.dumps({"first_name": CONTACT_FIRST_NAME}),
            limit=5,
        )
        self.assertGreater(count, 0)

    def test_schedule_bulk_messages(self):
        """Test schedule_bulk_messages background job."""
        # This just ensures the function runs without error
        # when there are no queued bulk messages
        schedule_bulk_messages()
