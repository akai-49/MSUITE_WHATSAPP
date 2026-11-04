# Copyright (c) 2022, Shridhar Patil and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase


class TestWhatsAppNotificationLog(IntegrationTestCase):
    """WhatsApp Notification Log is deprecated (WHATSAPP_REFACTOR_PLAN.md
    §10) — new rows are rejected; only historical-read behaviour remains
    under test."""

    def test_new_rows_are_rejected(self):
        doc = frappe.get_doc({
            "doctype": "WhatsApp Notification Log",
            "template": "Test Log Template",
            "meta_data": '{"status": "success"}',
        })
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)
