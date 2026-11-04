# Copyright (c) 2026, MSuite and contributors
# For license information, please see license.txt

"""
`bulk_send_service.queue_messages`: the AWS dispatch-failure status guard.

A genuine `export_and_enqueue` failure must be durably recorded as a
distinct status, not left indistinguishable from a healthy in-flight or
successfully-completed blast — that distinction is what makes retry-gating
in `dispatch/hub.py` and `audience/api/v1/audience.py` safe.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from msuite_whatsapp.constants import BulkMessageStatus
from msuite_whatsapp.services.bulk import bulk_send_service as svc


class TestQueueMessagesAwsDispatchFailure(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.bulk_doc = frappe._dict(
			{
				"doctype": "Bulk WhatsApp Message",
				"name": "BWA-AWS-FAIL-TEST",
				"docstatus": 1,
				"status": BulkMessageStatus.IN_PROGRESS,
				"recipient_type": "Individual",
			}
		)
		self.status_writes = []

		def fake_db_set(field, value, update_modified=None, **kwargs):
			self.status_writes.append((field, value))
			self.bulk_doc[field] = value

		self.bulk_doc.db_set = fake_db_set

	def test_export_and_enqueue_failure_sets_aws_dispatch_failed_and_reraises(self):
		fake_recipient = {"name": "WAR-1", "mobile_number": "+919900000001", "status": ""}

		with patch.object(svc, "get_recipients", return_value=[fake_recipient]), patch.object(
			svc, "is_opted_out", return_value=False
		):
			from msuite_campaigns.aws_pipeline import dispatch as aws_dispatch

			with patch.object(aws_dispatch, "should_use_aws", return_value=True), patch.object(
				aws_dispatch, "export_and_enqueue", side_effect=RuntimeError("provider unreachable")
			):
				with self.assertRaises(RuntimeError):
					svc.queue_messages(self.bulk_doc)

		self.assertIn(("status", BulkMessageStatus.AWS_DISPATCH_FAILED), self.status_writes)


class TestEnsureLeadForBulkRecipient(IntegrationTestCase):
	def test_ensure_lead_passes_caller_verified_auth(self):
		"""Smoke test that _ensure_lead_for_bulk_recipient passes caller_verified_auth=True
		to create_lead_for_source and does not raise frappe.PermissionError."""
		fake_bulk_doc = frappe._dict(
			{
				"doctype": "Bulk WhatsApp Message",
				"name": "BWA-LEAD-TEST",
				"campaign": "Test Campaign",
				"whatsapp_account": None,
			}
		)
		mock_handle = frappe._dict(
			{
				"name": "CH-TEST-001",
				"platform_handle": "919900000001",
				"display_name": "",
				"crm_party": None,
				"crm_party_type": None,
			}
		)
		mock_handle.db_set = lambda k, v: mock_handle.update({k: v})

		with patch("msuite_inbox.inbox.services.outbound._upsert_handle", return_value=mock_handle), patch(
			"custom_crm.api.v1.lead.find_existing_party", return_value=None
		), patch("frappe.db.exists", return_value=True), patch(
			"custom_crm.utils.lead_factory.create_lead_for_source"
		) as mock_create:

			def fake_create_lead(*args, **kwargs):
				if not kwargs.get("caller_verified_auth"):
					raise frappe.PermissionError("caller_verified_auth required")
				return "CRM-LEAD-001"

			mock_create.side_effect = fake_create_lead

			lead_name = svc._ensure_lead_for_bulk_recipient(
				phone="+919900000001",
				recipient_name="Test Recipient",
				bulk_doc=fake_bulk_doc,
			)

			self.assertEqual(lead_name, "CRM-LEAD-001")
			mock_create.assert_called_once()
			self.assertTrue(mock_create.call_args.kwargs.get("caller_verified_auth"))

