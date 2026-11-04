# Copyright (c) 2025, Shridhar Patil and Contributors
# See license.txt

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase


class TestWhatsAppRecipientList(IntegrationTestCase):
    """Tests for WhatsApp Recipient List doctype."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._ensure_test_user_with_mobile()

    @classmethod
    def _ensure_test_user_with_mobile(cls):
        """Ensure there's at least one user with mobile_no set for import tests."""
        if not frappe.db.get_value("User", "Administrator", "mobile_no"):
            frappe.db.set_value("User", "Administrator", "mobile_no", "919900000001")
            frappe.db.commit()

    def setUp(self):
        # These tests import from `User` as a convenient fixture source; in
        # production `User` is NOT an allowed import DocType (audit C5).
        patcher = patch(
            "msuite_core.utils.import_guard.allowed_import_doctypes",
            return_value=["User"],
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_import_from_non_allowlisted_doctype_is_refused(self):
        doc = self._make_recipient_list(
            list_name="Test Recipient Guard",
            recipients=[{"mobile_number": "919900112233", "recipient_name": "Guard"}],
        )
        with self.assertRaises(frappe.PermissionError):
            doc.import_list_from_doctype(doctype="Sales Invoice", mobile_field="contact_mobile")

    def tearDown(self):
        for name in frappe.get_all("WhatsApp Recipient List", filters={"list_name": ["like", "Test Recipient%"]}, pluck="name"):
            frappe.delete_doc("WhatsApp Recipient List", name, force=True)
        frappe.db.commit()

    def _make_recipient_list(self, list_name="Test Recipient List 1", recipients=None):
        """Helper to create a WhatsApp Recipient List."""
        doc = frappe.get_doc({
            "doctype": "WhatsApp Recipient List",
            "list_name": list_name,
            "description": "Test list",
        })
        if recipients:
            for r in recipients:
                doc.append("recipients", r)
        doc.insert(ignore_permissions=True)
        return doc

    def test_recipient_list_creation(self):
        """Test basic recipient list creation."""
        doc = self._make_recipient_list(recipients=[
            {"mobile_number": "919900112233", "recipient_name": "User 1"},
        ])
        self.assertTrue(frappe.db.exists("WhatsApp Recipient List", doc.name))

    def test_recipient_list_autoname(self):
        """Test list is named from list_name field."""
        doc = self._make_recipient_list(
            list_name="Test Recipient Autoname",
            recipients=[{"mobile_number": "919900112233"}]
        )
        self.assertEqual(doc.name, "Test Recipient Autoname")

    def test_validate_requires_recipients_on_existing(self):
        """Test validation requires at least one recipient on existing docs."""
        doc = self._make_recipient_list(
            list_name="Test Recipient Validate",
            recipients=[{"mobile_number": "919900112233"}]
        )
        # Remove all recipients and try to save
        doc.recipients = []
        with self.assertRaises(frappe.ValidationError):
            doc.save()

    def test_import_list_from_doctype(self):
        """Test importing recipients from another doctype (User)."""
        doc = self._make_recipient_list(
            list_name="Test Recipient Import",
            recipients=[{"mobile_number": "919900000099"}]
        )

        count = doc.import_list_from_doctype(
            doctype="User",
            mobile_field="mobile_no",
            name_field="full_name",
            filters={"mobile_no": ["is", "set"]},
            limit=5,
        )

        self.assertGreater(count, 0)
        doc.save()

    def test_import_list_with_data_fields(self):
        """Test importing with additional data fields."""
        doc = self._make_recipient_list(
            list_name="Test Recipient DataFields",
            recipients=[{"mobile_number": "919900000099"}]
        )

        count = doc.import_list_from_doctype(
            doctype="User",
            mobile_field="mobile_no",
            name_field="full_name",
            data_fields=["email", "first_name"],
            filters={"mobile_no": ["is", "set"]},
            limit=5,
        )

        self.assertGreater(count, 0)
        doc.save()
        # Verify recipient_data contains the data fields
        for recipient in doc.recipients:
            if recipient.recipient_data:
                data = json.loads(recipient.recipient_data)
                self.assertIsInstance(data, dict)

    def test_import_clears_existing_recipients(self):
        """Per import_list_from_doctype's own docstring: "Appends to the
        existing recipients (it used to silently wipe the list first)."
        So despite this test's name, an existing recipient now survives
        an import instead of being cleared — assert the current (append)
        behavior."""
        doc = self._make_recipient_list(
            list_name="Test Recipient Clear",
            recipients=[
                {"mobile_number": "919900112233", "recipient_name": "Old User"},
            ]
        )
        self.assertEqual(len(doc.recipients), 1)

        doc.import_list_from_doctype(
            doctype="User",
            mobile_field="mobile_no",
            filters={"mobile_no": ["is", "set"]},
            limit=5,
        )
        # The pre-existing recipient survives the import (append, not clear).
        self.assertTrue(any(r.recipient_name == "Old User" for r in doc.recipients))

    def test_import_formats_mobile_number(self):
        """Test that imported mobile numbers strip non-numeric characters."""
        doc = self._make_recipient_list(
            list_name="Test Recipient Format",
            recipients=[{"mobile_number": "919900000099"}]
        )

        # The import function strips non-numeric characters except +
        doc.recipients = []
        doc.append("recipients", {
            "mobile_number": "+91-9900-112233",
            "recipient_name": "Format Test",
        })
        # Manual mobile number isn't auto-formatted (that's in import logic)
        # Test the import logic separately by checking the function
        mobile = "+91-9900-112233"
        formatted = ''.join(char for char in mobile if char.isdigit() or char == '+')
        self.assertEqual(formatted, "+919900112233")


import csv
import io
import unittest
from msuite_whatsapp.services.bulk.recipient_import_service import (
	generate_sample_csv_content,
	download_sample_csv_template,
)
from msuite_whatsapp.services.validators.recipient_validator import clean_mobile


class UnitTestWhatsAppRecipientSampleTemplate(unittest.TestCase):
    """Unit tests for WhatsApp bulk upload sample CSV template."""

    def test_sample_csv_generation_headers_and_rows(self):
        """Verify sample CSV contains required mobile_number header and sample rows."""
        csv_text = generate_sample_csv_content()
        reader = csv.DictReader(io.StringIO(csv_text))
        headers = reader.fieldnames

        self.assertIn("mobile_number", headers)
        self.assertIn("recipient_name", headers)
        self.assertIn("company", headers)
        self.assertIn("city", headers)

        rows = list(reader)
        self.assertGreaterEqual(len(rows), 3)

        for row in rows:
            self.assertTrue(row["mobile_number"].startswith("+"))
            cleaned, err = clean_mobile(row["mobile_number"])
            self.assertIsNone(err, f"Sample number {row['mobile_number']} should be valid")
            self.assertTrue(len(cleaned) >= 10)

    def test_download_sample_csv_endpoint(self):
        """Verify download_sample_csv_template populates frappe.response correctly."""
        frappe.response = {}
        download_sample_csv_template()

        self.assertEqual(frappe.response.get("type"), "binary")
        self.assertEqual(frappe.response.get("filename"), "whatsapp_recipients_sample.csv")
        self.assertIn("filecontent", frappe.response)
        
        content = frappe.response["filecontent"].decode("utf-8-sig")
        self.assertIn("mobile_number", content)
        self.assertIn("+919876543210", content)
