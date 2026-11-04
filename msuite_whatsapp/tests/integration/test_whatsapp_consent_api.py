import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from msuite_whatsapp.api.v1.app.consent import bulk_set_whatsapp_consent


class TestWhatsappConsentApi(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.contacts_to_cleanup = []

	def tearDown(self):
		frappe.db.rollback()
		for c in self.contacts_to_cleanup:
			if frappe.db.exists("Contact", c):
				frappe.delete_doc("Contact", c, force=True, ignore_permissions=True)

	def _make_contact(self, phone):
		c = frappe.get_doc({
			"doctype": "Contact",
			"first_name": "Test",
			"last_name": "User",
			"mobile_no": phone,
			"phone_e164": phone,
			"unsubscribed_whatsapp": 0,
		}).insert(ignore_permissions=True)
		self.contacts_to_cleanup.append(c.name)
		return c

	def test_bulk_consent_counts_and_actions(self):
		"""Bulk API counts valid/updated, invalid, and unknown (not_found) numbers and performs opt-out / opt-in."""
		phone_existing = "+919876543210"
		self._make_contact(phone_existing)

		phone_unknown = "+919876543299"
		phone_invalid = "not-a-valid-phone"
		phone_duplicate = "+919876543210"

		# Test opt_out with list containing: existing, unknown, invalid, duplicate, and blank
		input_numbers = [phone_existing, phone_unknown, phone_invalid, phone_duplicate, "", "   "]
		res = bulk_set_whatsapp_consent(input_numbers, "opt_out")

		self.assertEqual(res["updated"], 1)
		self.assertEqual(res["not_found"], 1)
		self.assertEqual(res["invalid"], 1)

		# Verify Contact was marked unsubscribed
		c_doc = frappe.get_all("Contact", filters={"phone_e164": phone_existing}, fields=["unsubscribed_whatsapp"])[0]
		self.assertEqual(c_doc.unsubscribed_whatsapp, 1)

		# Test opt_in restores consent
		res_in = bulk_set_whatsapp_consent(phone_existing, "opt_in")
		self.assertEqual(res_in["updated"], 1)
		c_doc_in = frappe.get_all("Contact", filters={"phone_e164": phone_existing}, fields=["unsubscribed_whatsapp"])[0]
		self.assertEqual(c_doc_in.unsubscribed_whatsapp, 0)

	def test_bulk_consent_pasted_text_input(self):
		"""Accepts pasted text with newlines or commas."""
		phone = "+919876543211"
		self._make_contact(phone)

		pasted = f"{phone}\n+919876543200,invalid_num"
		res = bulk_set_whatsapp_consent(pasted, "opt_out")
		self.assertEqual(res["updated"], 1)
		self.assertEqual(res["not_found"], 1)
		self.assertEqual(res["invalid"], 1)

	def test_bulk_consent_rejects_bad_action(self):
		"""Rejects unknown actions with a ValidationError."""
		with self.assertRaises(frappe.ValidationError):
			bulk_set_whatsapp_consent(["+919876543210"], "delete_all")

	def test_bulk_consent_capped_at_5000(self):
		"""Rejects more than 5,000 numbers in a single call."""
		too_many = [f"+9198765{i:05d}" for i in range(5001)]
		with self.assertRaises(frappe.ValidationError):
			bulk_set_whatsapp_consent(too_many, "opt_out")

	def test_bulk_consent_permission_check(self):
		"""Raises PermissionError when user lacks write permission."""
		with patch("frappe.has_permission", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				bulk_set_whatsapp_consent(["+919876543210"], "opt_out")

	def test_bulk_consent_empty_json_list_is_not_invalid(self):
		res = bulk_set_whatsapp_consent("[]", "opt_in")
		self.assertEqual(res, {"updated": 0, "not_found": 0, "invalid": 0})
