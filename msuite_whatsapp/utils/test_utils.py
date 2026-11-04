# Copyright (c) 2025, Shridhar Patil and Contributors
# See license.txt

from unittest.mock import patch, MagicMock

import frappe
from frappe.tests import IntegrationTestCase

from msuite_whatsapp.utils import format_number, get_whatsapp_account


class TestFormatNumber(IntegrationTestCase):
    """Tests for format_number utility."""

    def test_strips_leading_plus(self):
        self.assertEqual(format_number("+919900112233"), "919900112233")

    def test_no_plus_unchanged(self):
        self.assertEqual(format_number("919900112233"), "919900112233")

    def test_plus_only_at_start(self):
        self.assertEqual(format_number("+1234567890"), "1234567890")


class TestGetWhatsAppAccount(IntegrationTestCase):
    """Tests for get_whatsapp_account utility."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._ensure_test_accounts()

    @classmethod
    def _ensure_test_accounts(cls):
        if not frappe.db.exists("WhatsApp Account", "Test Utils Account"):
            account = frappe.get_doc({
                "doctype": "WhatsApp Account",
                "account_name": "Test Utils Account",
                "status": "Active",
                "business_id": "utils_test_business_id",
                "app_id": "utils_test_app_id",
                "phones": [{
                    "phone_number_id": "utils_test_phone_id",
                    "display_phone_number": "+1 utils",
                    "status": "Active",
                    "is_default_incoming": 1,
                    "is_default_outgoing": 1,
                }],
            })
            account.insert(ignore_permissions=True)
            frappe.db.commit()

    def setUp(self):
        # Clear ALL phone defaults then set ours — a real dev-site account with a
        # default phone row would otherwise always win over this test's fixture.
        frappe.db.sql("UPDATE `tabWhatsApp Phone Number` SET is_default_outgoing=0, is_default_incoming=0")
        frappe.db.sql(
            "UPDATE `tabWhatsApp Phone Number` SET is_default_outgoing=1, is_default_incoming=1 "
            "WHERE parent='Test Utils Account'"
        )

    def test_get_account_by_phone_id(self):
        """Test getting account by phone_id."""
        account = get_whatsapp_account(phone_id="utils_test_phone_id")
        self.assertIsNotNone(account)
        self.assertEqual(account.name, "Test Utils Account")

    def test_get_account_by_phone_id_not_found(self):
        """Test getting account by non-existent phone_id falls back to default."""
        account = get_whatsapp_account(phone_id="nonexistent_phone_id")
        # Should fall back to the default incoming account
        self.assertEqual(account.name, "Test Utils Account")

    def test_get_default_incoming_account(self):
        """Test getting default incoming account."""
        account = get_whatsapp_account(account_type='incoming')
        self.assertEqual(account.name, "Test Utils Account")

    def test_get_default_outgoing_account(self):
        """Test getting default outgoing account."""
        account = get_whatsapp_account(account_type='outgoing')
        self.assertEqual(account.name, "Test Utils Account")
