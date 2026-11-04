"""
Unit & integration tests for Bulk Deletion APIs across WhatsApp modules.

Covers:
- `bulk_delete_bulk_messages`
- `bulk_delete_flows`
- `bulk_delete_flow_responses`
"""

from __future__ import annotations

import json
from unittest.mock import patch
import frappe
from frappe.tests import IntegrationTestCase

from msuite_whatsapp.api.v1.app.bulk_messages import bulk_delete_bulk_messages
from msuite_whatsapp.api.v1.app.flows import bulk_delete_flows
from msuite_whatsapp.api.v1.app.flow_responses import bulk_delete_flow_responses


class TestWhatsAppBulkDeletion(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		doc_name = "test_bulk_del_tpl-en"
		if not frappe.db.exists("WhatsApp Templates", doc_name):
			doc = frappe.get_doc({
				"doctype": "WhatsApp Templates",
				"template_name": "test_bulk_del_tpl",
				"category": "MARKETING",
				"language": "en",
				"language_code": "en",
				"template": "Hello {{1}}",
			})
			doc.flags.ignore_permissions = True
			doc.flags.ignore_links = True
			with patch("msuite_whatsapp.services.templates.template_service.push_to_meta"):
				doc.insert()
			frappe.db.commit()

		if not frappe.db.exists("WhatsApp Recipient List", "test_bulk_del_recipients"):
			rec_doc = frappe.get_doc({
				"doctype": "WhatsApp Recipient List",
				"list_name": "test_bulk_del_recipients",
			})
			rec_doc.flags.ignore_permissions = True
			rec_doc.insert()
			frappe.db.commit()

		if not frappe.db.exists("WhatsApp Account", "test_bulk_del_account"):
			acc_doc = frappe.get_doc({
				"doctype": "WhatsApp Account",
				"account_name": "test_bulk_del_account",
				"phone_number_id": "1234567890",
				"business_account_id": "9876543210",
				"access_token": "test_token",
			})
			acc_doc.flags.ignore_permissions = True
			acc_doc.insert()
			frappe.db.commit()

	def test_bulk_delete_bulk_messages(self):
		doc1 = frappe.get_doc({
			"doctype": "Bulk WhatsApp Message",
			"title": "Test Bulk Delete 1",
			"template": "test_bulk_del_tpl-en",
			"recipient_type": "Recipient List",
			"recipient_list": "test_bulk_del_recipients",
			"status": "Draft",
		})
		doc1.flags.ignore_validate = True
		doc1.insert(ignore_permissions=True, ignore_links=True)

		doc2 = frappe.get_doc({
			"doctype": "Bulk WhatsApp Message",
			"title": "Test Bulk Delete 2",
			"template": "test_bulk_del_tpl-en",
			"recipient_type": "Recipient List",
			"recipient_list": "test_bulk_del_recipients",
			"status": "Draft",
		})
		doc2.flags.ignore_validate = True
		doc2.insert(ignore_permissions=True, ignore_links=True)
		frappe.db.commit()

		self.assertTrue(frappe.db.exists("Bulk WhatsApp Message", doc1.name))
		self.assertTrue(frappe.db.exists("Bulk WhatsApp Message", doc2.name))

		# Execute bulk delete
		res = bulk_delete_bulk_messages(json.dumps([doc1.name, doc2.name]))
		self.assertIn(doc1.name, res["deleted"])
		self.assertIn(doc2.name, res["deleted"])
		self.assertEqual(len(res["failed"]), 0)

		# Verify deleted
		self.assertFalse(frappe.db.exists("Bulk WhatsApp Message", doc1.name))
		self.assertFalse(frappe.db.exists("Bulk WhatsApp Message", doc2.name))

	def test_bulk_delete_flows(self):
		flow1 = frappe.get_doc({
			"doctype": "WhatsApp Flow",
			"flow_name": "Test Flow Delete 1",
			"whatsapp_account": "test_bulk_del_account",
			"status": "Draft",
		})
		flow1.append("screens", {"screen_id": "WELCOME", "screen_title": "Welcome", "terminal": 1})
		flow1.append("fields", {
			"screen": "WELCOME",
			"field_type": "TextHeading",
			"field_name": "heading_1",
			"label": "Welcome",
			"enabled": 1,
		})
		flow1.flags.ignore_links = True
		flow1.insert(ignore_permissions=True)

		flow2 = frappe.get_doc({
			"doctype": "WhatsApp Flow",
			"flow_name": "Test Flow Delete 2",
			"whatsapp_account": "test_bulk_del_account",
			"status": "Draft",
		})
		flow2.append("screens", {"screen_id": "WELCOME", "screen_title": "Welcome", "terminal": 1})
		flow2.append("fields", {
			"screen": "WELCOME",
			"field_type": "TextHeading",
			"field_name": "heading_1",
			"label": "Welcome",
			"enabled": 1,
		})
		flow2.flags.ignore_links = True
		flow2.insert(ignore_permissions=True)
		frappe.db.commit()

		self.assertTrue(frappe.db.exists("WhatsApp Flow", flow1.name))
		self.assertTrue(frappe.db.exists("WhatsApp Flow", flow2.name))

		# Execute bulk delete
		res = bulk_delete_flows(json.dumps([flow1.name, flow2.name]))
		self.assertIn(flow1.name, res["deleted"])
		self.assertIn(flow2.name, res["deleted"])
		self.assertEqual(len(res["failed"]), 0)

		# Verify deleted
		self.assertFalse(frappe.db.exists("WhatsApp Flow", flow1.name))
		self.assertFalse(frappe.db.exists("WhatsApp Flow", flow2.name))

	def test_bulk_delete_flow_responses(self):
		doc1 = frappe.get_doc({
			"doctype": "WhatsApp Flow Response",
			"status": "Sent",
			"contact_phone": "+919876543210",
		}).insert(ignore_permissions=True, ignore_links=True)

		doc2 = frappe.get_doc({
			"doctype": "WhatsApp Flow Response",
			"status": "Sent",
			"contact_phone": "+919876543211",
		}).insert(ignore_permissions=True, ignore_links=True)
		frappe.db.commit()

		self.assertTrue(frappe.db.exists("WhatsApp Flow Response", doc1.name))
		self.assertTrue(frappe.db.exists("WhatsApp Flow Response", doc2.name))

		# Execute bulk delete
		res = bulk_delete_flow_responses(json.dumps([doc1.name, doc2.name]))
		self.assertIn(doc1.name, res["deleted"])
		self.assertIn(doc2.name, res["deleted"])
		self.assertEqual(len(res["failed"]), 0)

		# Verify deleted
		self.assertFalse(frappe.db.exists("WhatsApp Flow Response", doc1.name))
		self.assertFalse(frappe.db.exists("WhatsApp Flow Response", doc2.name))

	def test_bulk_delete_partial_failure_reports_missing_name(self):
		"""A name that doesn't exist must land in `failed`, not silently
		vanish or blow up the whole batch."""
		doc1 = frappe.get_doc({
			"doctype": "Bulk WhatsApp Message",
			"title": "Test Bulk Delete Partial",
			"template": "test_bulk_del_tpl-en",
			"recipient_type": "Recipient List",
			"recipient_list": "test_bulk_del_recipients",
			"status": "Draft",
		})
		doc1.flags.ignore_validate = True
		doc1.insert(ignore_permissions=True, ignore_links=True)
		frappe.db.commit()

		res = bulk_delete_bulk_messages(json.dumps([doc1.name, "NOT-A-REAL-NAME"]))
		self.assertIn(doc1.name, res["deleted"])
		self.assertEqual(len(res["failed"]), 1)
		self.assertEqual(res["failed"][0]["name"], "NOT-A-REAL-NAME")
		self.assertFalse(frappe.db.exists("Bulk WhatsApp Message", doc1.name))

	def test_bulk_delete_empty_list_is_a_noop(self):
		res = bulk_delete_bulk_messages(json.dumps([]))
		self.assertEqual(res, {"deleted": [], "failed": []})
