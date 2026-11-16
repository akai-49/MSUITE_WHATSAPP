# Copyright (c) 2026, MSuite and contributors
# For license information, please see license.txt

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from msuite_whatsapp.api.v1.app import analytics as analytics_api
from msuite_whatsapp.api.v1.app import calls as calls_api
from msuite_whatsapp.services.permissions.roles import ADMIN, INBOX_AGENT, VIEWER, WA_MANAGER, WA_USER
from msuite_whatsapp.api.v1.app import analytics_query as query
from msuite_whatsapp.services.analytics import sync
from msuite_whatsapp.whatsapp.doctype.whatsapp_flow import whatsapp_flow
from msuite_whatsapp.api.v1.app import bulk_messaging


def _user(role: str | None) -> str:
	email = f"perm-{(role or 'none').lower().replace(' ', '-')}@example.com"
	if not frappe.db.exists("User", email):
		u = frappe.get_doc({
			"doctype": "User",
			"email": email,
			"first_name": "Perm",
			"send_welcome_email": 0,
		}).insert(ignore_permissions=True)
		if role:
			u.add_roles(role)
	else:
		u = frappe.get_doc("User", email)
		current_roles = [r.role for r in u.roles]
		if role:
			if role not in current_roles:
				u.add_roles(role)
		else:
			roles_to_remove = [r.role for r in u.roles if r.role not in ("Desk User", "All")]
			if roles_to_remove:
				u.remove_roles(*roles_to_remove)
	return email


class TestWhatsappApiPermissions(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")

		_user(WA_USER)
		_user(WA_MANAGER)
		_user(INBOX_AGENT)
		_user(VIEWER)
		_user(ADMIN)
		_user(None)

		cls.account_name = "Perm Test WhatsApp Account"
		if not frappe.db.exists("WhatsApp Account", cls.account_name):
			frappe.get_doc({
				"doctype": "WhatsApp Account",
				"account_name": cls.account_name,
				"waba_id": "1234567890",
				"status": "Active",
				"phone_number": "+1234567890",
				"display_phone_number": "+1234567890",
			}).insert(ignore_permissions=True)

		cls.template_name = "perm_test_template"
		existing_tmpl = frappe.db.get_value("WhatsApp Templates", {"template_name": cls.template_name}, "name")
		if not existing_tmpl:
			with patch("msuite_whatsapp.whatsapp.doctype.whatsapp_templates.whatsapp_templates.WhatsAppTemplates.push_to_meta"):
				tmpl = frappe.get_doc({
					"doctype": "WhatsApp Templates",
					"template_name": cls.template_name,
					"whatsapp_account": cls.account_name,
					"category": "UTILITY",
					"language": "en",
					"language_code": "en",
					"status": "APPROVED",
					"template": "Hello {{1}}",
					"sample_values": json.dumps({"1": "Alice"}),
				}).insert(ignore_permissions=True)
				cls.template_name = tmpl.name
		else:
			cls.template_name = existing_tmpl

		cls.bulk_doc = frappe.get_doc({
			"doctype": "Bulk WhatsApp Message",
			"title": "Perm Test Bulk WA",
			"whatsapp_account": cls.account_name,
			"template": cls.template_name,
			"status": "In Progress",
			"owner": _user(WA_USER),
			"recipients": [{"mobile_number": "+1234567890"}],
		}).insert(ignore_permissions=True)
		cls.bulk_name = cls.bulk_doc.name

		cls.flow_name = "Perm-Test-Flow"
		if frappe.db.exists("WhatsApp Flow", cls.flow_name):
			frappe.delete_doc("WhatsApp Flow", cls.flow_name, force=True)
		cls.flow_doc = frappe.get_doc({
			"doctype": "WhatsApp Flow",
			"flow_name": cls.flow_name,
			"whatsapp_account": cls.account_name,
			"category": '["OTHER"]',
			"status": "Draft",
			"flow_id": "flow-test-12345",
			"screens": [
				{
					"screen_id": "SCREEN_1",
					"screen_title": "Screen 1",
					"terminal": 1,
				}
			],
		}).insert(ignore_permissions=True)

		existing_call = frappe.db.get_value("WhatsApp Call", {"call_id": "call-perm-test-01"}, "name")
		if not existing_call:
			call_doc = frappe.get_doc({
				"doctype": "WhatsApp Call",
				"call_id": "call-perm-test-01",
				"direction": "Inbound",
				"status": "Ringing",
				"whatsapp_account": cls.account_name,
				"caller_number": "+1234567890",
			}).insert(ignore_permissions=True)
			cls.call_name = call_doc.name
		else:
			cls.call_name = existing_call

		if not frappe.db.exists("WhatsApp Analytics Snapshot", {"whatsapp_account": cls.account_name}):
			frappe.get_doc({
				"doctype": "WhatsApp Analytics Snapshot",
				"whatsapp_account": cls.account_name,
				"metric_type": "messaging",
				"period_start": "2026-10-01",
				"period_end": "2026-10-06",
				"granularity": "DAY",
				"raw_data": json.dumps({"data": []}),
			}).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def test_role_less_user_endpoints_raise_permission_error(self):
		frappe.set_user(_user(None))
		self.assertRaises(frappe.PermissionError, analytics_api.get_dashboard_data, self.account_name)
		self.assertRaises(frappe.PermissionError, query.get_messaging_summary, self.account_name)
		self.assertRaises(frappe.PermissionError, calls_api.get_call_history, "+1234567890")
		self.assertRaises(frappe.PermissionError, calls_api.answer_call, self.call_name)
		self.assertRaises(frappe.PermissionError, bulk_messaging.pause, self.bulk_name)
		self.assertRaises(frappe.PermissionError, whatsapp_flow.get_whatsapp_flows, self.account_name)

	def test_h1_scheduler_jobs_refused_or_admin_direct(self):
		frappe.set_user(_user(None))
		# Calling sync_all_accounts over HTTP whitelist registry is refused
		self.assertRaises(frappe.PermissionError, frappe.is_whitelisted, sync.sync_all_accounts)

		# Scheduler runs directly as Administrator (mocking Meta API)
		frappe.set_user("Administrator")
		with patch("msuite_whatsapp.services.analytics.sync.sync_all") as mock_sync_all:
			sync.sync_all_accounts()
			mock_sync_all.assert_called()

	def test_h2_call_roles_gate(self):
		# Inbox Agent passes the call-role gate
		frappe.set_user(_user(INBOX_AGENT))
		with patch("msuite_whatsapp.services.calls.call_service.answer_call") as mock_answer:
			mock_answer.return_value = {"status": "answered"}
			res = calls_api.answer_call(self.call_name)
			self.assertEqual(res, {"status": "answered"})
			mock_answer.assert_called_once_with(self.call_name, sdp="", sdp_type="answer")

		with patch("msuite_whatsapp.services.calls.call_service.get_call_history", return_value=[]):
			history = calls_api.get_call_history("+1234567890")
			self.assertEqual(history, [])

		# Viewer raises
		frappe.set_user(_user(VIEWER))
		self.assertRaises(frappe.PermissionError, calls_api.answer_call, self.call_name)

		# WhatsApp User raises
		frappe.set_user(_user(WA_USER))
		self.assertRaises(frappe.PermissionError, calls_api.answer_call, self.call_name)
		self.assertRaises(frappe.PermissionError, calls_api.get_call_history, "+1234567890")

		# WhatsApp Manager raises (O8: calling stays an Inbox capability)
		frappe.set_user(_user(WA_MANAGER))
		self.assertRaises(frappe.PermissionError, calls_api.answer_call, self.call_name)

	def test_h3_viewer_pause_cancel_retry_failed_raises_and_wa_user_passes(self):
		frappe.set_user(_user(VIEWER))
		self.assertRaises(frappe.PermissionError, bulk_messaging.pause, self.bulk_name)
		self.assertRaises(frappe.PermissionError, bulk_messaging.cancel, self.bulk_name)
		self.assertRaises(frappe.PermissionError, bulk_messaging.retry_failed, self.bulk_name)

		# Status is unchanged
		self.assertEqual(
			frappe.db.get_value("Bulk WhatsApp Message", self.bulk_name, "status"),
			"In Progress",
		)

		# WhatsApp User passes on their own broadcast (mock enqueue/service)
		frappe.set_user(_user(WA_USER))
		with patch("msuite_whatsapp.services.bulk.bulk_send_service.retry_failed", return_value={"requeued": 0}), \
			 patch("frappe.msgprint"):
			res = bulk_messaging.pause(self.bulk_name)
			self.assertTrue(res)

	def test_h4_whatsapp_manager_flow_actions_raise_and_admin_passes(self):
		frappe.set_user(_user(WA_MANAGER))
		flow_doc = frappe.get_doc("WhatsApp Flow", self.flow_name)
		self.assertRaises(frappe.PermissionError, flow_doc.publish_flow)
		self.assertRaises(frappe.PermissionError, flow_doc.send_test, "+1234567890")

		# Admin passes
		frappe.set_user(_user(ADMIN))
		with patch("msuite_whatsapp.services.flows.flow_service.publish_flow") as mock_publish, \
			 patch("msuite_whatsapp.services.flows.flow_service.send_test") as mock_send_test:
			flow_doc.publish_flow()
			mock_publish.assert_called_once_with(flow_doc)
			flow_doc.send_test("+1234567890")
			mock_send_test.assert_called_once_with(flow_doc, "+1234567890", None)

	def test_h5_whatsapp_user_reads_analytics_and_inbox_agent_raises(self):
		frappe.set_user(_user(WA_USER))
		with patch("msuite_whatsapp.api.v1.app.analytics_query.get_whatsapp_account_insights", return_value={}):
			data = query.get_messaging_summary(self.account_name)
			self.assertIsInstance(data, dict)

		# Inbox Agent without snapshot read raises
		frappe.set_user(_user(INBOX_AGENT))
		self.assertRaises(frappe.PermissionError, query.get_messaging_summary, self.account_name)
		self.assertRaises(frappe.PermissionError, analytics_api.get_dashboard_data, self.account_name)

	def test_h6_whatsapp_user_push_to_meta_raises_and_manager_passes(self):
		tmpl_doc = frappe.get_doc("WhatsApp Templates", self.template_name)

		frappe.set_user(_user(WA_USER))
		self.assertRaises(frappe.PermissionError, tmpl_doc.push_to_meta)

		frappe.set_user(_user(WA_MANAGER))
		with patch("msuite_whatsapp.services.templates.template_service.push_to_meta") as mock_push:
			tmpl_doc.push_to_meta()
			mock_push.assert_called_once_with(tmpl_doc)
