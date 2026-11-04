# Copyright (c) 2025, Shridhar Patil and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase


class TestWhatsAppAccount(IntegrationTestCase):
    """Tests for WhatsApp Account doctype.

    Account identity is WABA-level; per-phone defaults/status live on
    the `phones` child table (WhatsApp Phone Number).
    """

    def setUp(self):
        for name in frappe.get_all(
            "WhatsApp Account", filters={"account_name": ["like", "Test WA Account%"]}, pluck="name"
        ):
            frappe.delete_doc("WhatsApp Account", name, force=True, ignore_permissions=True)
        frappe.db.commit()

    def tearDown(self):
        for name in frappe.get_all(
            "WhatsApp Account", filters={"account_name": ["like", "Test WA Account%"]}, pluck="name"
        ):
            frappe.delete_doc("WhatsApp Account", name, force=True, ignore_permissions=True)
        frappe.db.commit()

    def _make_account(self, account_name="Test WA Account 1", phones=None, **kwargs):
        doc = frappe.get_doc(
            {
                "doctype": "WhatsApp Account",
                "account_name": account_name,
                "status": kwargs.get("status", "Active"),
                "phones": phones or [],
            }
        )
        doc.insert(ignore_permissions=True)
        return doc

    def _phone_row(self, phone_number_id, **kwargs):
        return {
            "phone_number_id": phone_number_id,
            "display_phone_number": kwargs.get("display_phone_number", "+1 555 0000"),
            "verified_name": kwargs.get("verified_name", "Test Biz"),
            "status": kwargs.get("status", "Active"),
            "is_default_outgoing": kwargs.get("is_default_outgoing", 0),
            "is_default_incoming": kwargs.get("is_default_incoming", 0),
        }

    def test_account_creation(self):
        doc = self._make_account()
        self.assertTrue(frappe.db.exists("WhatsApp Account", doc.name))
        self.assertEqual(doc.status, "Active")

    def test_account_autoname_from_account_name(self):
        doc = self._make_account(account_name="Test WA Account Autoname")
        self.assertEqual(doc.name, "Test WA Account Autoname")

    def test_account_name_must_be_unique(self):
        self._make_account(account_name="Test WA Account Dup")
        dup = frappe.get_doc(
            {
                "doctype": "WhatsApp Account",
                "account_name": "Test WA Account Dup",
                "status": "Active",
            }
        )
        with self.assertRaises(frappe.DuplicateEntryError):
            dup.insert(ignore_permissions=True)

    def test_get_default_phone_prefers_flagged_default(self):
        doc = self._make_account(
            account_name="Test WA Account GetDefault",
            phones=[
                self._phone_row("111", is_default_outgoing=0),
                self._phone_row("222", is_default_outgoing=1),
            ],
        )
        phone = doc.get_default_phone("outgoing")
        self.assertEqual(phone.phone_number_id, "222")

    def test_get_default_phone_falls_back_to_active(self):
        doc = self._make_account(
            account_name="Test WA Account GetDefaultActive",
            phones=[self._phone_row("111", status="Suspended"), self._phone_row("222", status="Active")],
        )
        phone = doc.get_default_phone("outgoing")
        self.assertEqual(phone.phone_number_id, "222")

    def test_get_default_phone_none_when_no_phones(self):
        doc = self._make_account(account_name="Test WA Account NoDefault", phones=[])
        self.assertIsNone(doc.get_default_phone("outgoing"))

    def test_status_change_to_active_promotes_default(self):
        """Activating an account claims empty/stale WhatsApp Settings default slots."""
        settings = frappe.get_single("WhatsApp Settings")
        settings.db_set("default_outgoing_account", None, update_modified=False)
        settings.db_set("default_incoming_account", None, update_modified=False)

        doc = self._make_account(account_name="Test WA Account Promote", status="Inactive")
        doc.status = "Active"
        doc.save(ignore_permissions=True)

        settings.reload()
        self.assertEqual(settings.default_outgoing_account, doc.name)
        self.assertEqual(settings.default_incoming_account, doc.name)

    def test_status_change_away_from_active_demotes_default(self):
        """Deactivating the current default clears/replaces it so the CRM
        WhatsApp tab doesn't point at a broken account."""
        settings = frappe.get_single("WhatsApp Settings")

        doc = self._make_account(account_name="Test WA Account Demote", status="Active")
        settings.db_set("default_outgoing_account", doc.name, update_modified=False)
        settings.db_set("default_incoming_account", doc.name, update_modified=False)

        doc.status = "Inactive"
        doc.save(ignore_permissions=True)

        settings.reload()
        self.assertNotEqual(settings.default_outgoing_account, doc.name)
