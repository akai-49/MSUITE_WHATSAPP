"""
Tests for WhatsApp Flow Response capture and CRM Lead Forms integration.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import frappe
from frappe.tests import IntegrationTestCase

from msuite_whatsapp.services.flows import flow_response_service
from msuite_whatsapp.services.validators.recipient_validator import clean_mobile

# The service stores numbers in the normalised form `clean_mobile` returns (E.164 with a plus),
# so lookups and cleanup must cover both the raw webhook form and the stored form.
EXISTING_LEAD_PHONE = "919888877777"
NEW_LEAD_PHONE = "919777766666"
NEW_LEAD_STORED_PHONE = clean_mobile(NEW_LEAD_PHONE)[0]
CLEANUP_PHONES = [EXISTING_LEAD_PHONE, NEW_LEAD_PHONE, NEW_LEAD_STORED_PHONE]


class TestFlowResponse(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		# Clean up any existing test records
		for d in frappe.get_all("CRM Lead", filters={"mobile_no": ["in", CLEANUP_PHONES]}):
			frappe.delete_doc("CRM Lead", d.name, force=1, ignore_permissions=True)
		for d in frappe.get_all("WhatsApp Flow Response", filters={"contact_phone": ["in", CLEANUP_PHONES]}):
			frappe.delete_doc("WhatsApp Flow Response", d.name, force=1, ignore_permissions=True)
		frappe.db.commit()

	def test_capture_flow_response_for_existing_lead(self):
		"""Existing CRM Lead should receive a meta_form_submissions row and link to WhatsApp Flow Response."""
		lead = frappe.get_doc(
			{
				"doctype": "CRM Lead",
				"lead_name": "Existing Lead Test",
				"first_name": "Existing",
				"mobile_no": "919888877777",
				"status": "New",
			}
		)
		lead.insert(ignore_permissions=True)
		frappe.db.commit()

		msg_mock = MagicMock()
		msg_mock.name = "MSG-FLOW-TEST-001"
		msg_mock.sender_phone = "919888877777"
		msg_mock.sender_name = "Existing Lead Test"
		msg_mock.conversation = ""
		msg_mock.reference_doctype = "CRM Lead"
		msg_mock.reference_name = lead.name
		msg_mock.whatsapp_account = ""  # no account needed; avoids depending on a site-specific record
		msg_mock.interactive_payload = {
			"type": "nfm_reply",
			"nfm_reply": {
				"response_json": json.dumps(
					{
						"full_name": "Existing Lead Test",
						"course": "Fullstack Python",
						"experience": "2 Years",
						"flow_token": "flow_token_123",
					}
				),
			},
		}

		flow_response_service.capture_from_message(msg_mock, {})

		# 1. Verify WhatsApp Flow Response doc created
		flow_resp_name = frappe.db.get_value("WhatsApp Flow Response", {"contact_phone": "919888877777"}, "name")
		self.assertIsNotNone(flow_resp_name)
		flow_resp = frappe.get_doc("WhatsApp Flow Response", flow_resp_name)
		self.assertEqual(flow_resp.status, "Completed")
		self.assertEqual(flow_resp.lead, lead.name)

		# 2. Verify CRM Lead received meta_form_submissions row
		lead.reload()
		self.assertGreaterEqual(len(lead.meta_form_submissions or []), 1)
		sub = lead.meta_form_submissions[0]
		self.assertEqual(sub.platform_lead_id, flow_resp.name)
		self.assertEqual(sub.form_type, "WhatsApp Flow")
		self.assertIn("course: Fullstack Python", sub.meta_form_answers)
		self.assertIn("experience: 2 Years", sub.meta_form_answers)

	def test_capture_flow_response_auto_creates_new_lead(self):
		"""When no CRM Lead exists for the phone, one should be auto-created with submitted flow fields."""
		msg_mock = MagicMock()
		msg_mock.name = "MSG-FLOW-TEST-002"
		msg_mock.sender_phone = "919777766666"
		msg_mock.sender_name = "New Flow Contact"
		msg_mock.conversation = ""
		msg_mock.reference_doctype = None
		msg_mock.reference_name = None
		msg_mock.whatsapp_account = ""  # no account needed; avoids depending on a site-specific record
		msg_mock.interactive_payload = {
			"type": "nfm_reply",
			"nfm_reply": {
				"response_json": json.dumps(
					{
						"full_name": "Rohan Sharma",
						"email": "rohan@example.com",
						"organization": "Sharma Tech",
						"interested_service": "WhatsApp CRM",
						"flow_token": "flow_token_456",
					}
				),
			},
		}

		flow_response_service.capture_from_message(msg_mock, {})

		# 1. Verify CRM Lead was auto-created
		lead_name = frappe.db.get_value("CRM Lead", {"mobile_no": NEW_LEAD_STORED_PHONE}, "name")
		self.assertIsNotNone(lead_name)
		new_lead = frappe.get_doc("CRM Lead", lead_name)
		self.assertEqual(new_lead.lead_name, "Rohan Sharma")
		self.assertEqual(new_lead.first_name, "Rohan")
		self.assertEqual(new_lead.last_name, "Sharma")
		self.assertEqual(new_lead.email, "rohan@example.com")
		self.assertEqual(new_lead.organization, "Sharma Tech")
		self.assertEqual(new_lead.source, "WhatsApp Flow")

		# 2. Verify Flow submission row attached
		self.assertEqual(len(new_lead.meta_form_submissions or []), 1)
		sub = new_lead.meta_form_submissions[0]
		self.assertEqual(sub.form_type, "WhatsApp Flow")
		self.assertIn("interested_service: WhatsApp CRM", sub.meta_form_answers)

		# 3. Verify WhatsApp Flow Response links to new lead
		flow_resp_name = frappe.db.get_value("WhatsApp Flow Response", {"contact_phone": "919777766666"}, "name")
		flow_resp = frappe.get_doc("WhatsApp Flow Response", flow_resp_name)
		self.assertEqual(flow_resp.lead, new_lead.name)

		# 4. Triggering again should not create duplicate submission rows
		flow_response_service.capture_from_message(msg_mock, {})
		new_lead.reload()
		self.assertEqual(len(new_lead.meta_form_submissions or []), 1)
