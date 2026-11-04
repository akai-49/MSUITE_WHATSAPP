"""
WhatsApp Flow — controller.

Lifecycle hooks and validation only. The 960-line Flow-JSON compiler and
every Meta HTTP call that used to live here have moved to
`providers/meta/flow_compiler.py`, `providers/meta/flow_provider.py`, and
`services/flow_service.py` — this was the single largest fat-controller
finding in the architecture audit. See WHATSAPP_REFACTOR_PLAN.md §3/§4.
"""

import json

import frappe
from frappe.model.document import Document

from msuite_core.services.permissions.checks import check_create, check_read
from msuite_whatsapp.services.flows import flow_service
from msuite_whatsapp.services.validators import flow_validator


class WhatsAppFlow(Document):
	def before_save(self):
		"""Generate flow JSON before saving."""
		self.flow_json = json.dumps(flow_service.generate_flow_json(self), indent=2)

	def validate(self):
		flow_service.validate_categories(self)
		flow_validator.validate_screens(self.screens, self.fields)

	@frappe.whitelist()
	def create_on_whatsapp(self):
		"""Create the flow on WhatsApp Business API."""
		self.check_permission("write")
		flow_service.create_on_whatsapp(self)

	@frappe.whitelist()
	def upload_flow_json(self):
		"""Upload flow JSON to WhatsApp."""
		self.check_permission("write")
		flow_service.upload_flow_json(self)

	@frappe.whitelist()
	def publish_flow(self):
		"""Publish the flow to make it available for use."""
		self.check_permission("write")
		flow_service.publish_flow(self)

	@frappe.whitelist()
	def deprecate_flow(self):
		"""Deprecate the flow."""
		self.check_permission("write")
		flow_service.deprecate_flow(self)

	@frappe.whitelist()
	def delete_from_whatsapp(self):
		"""Delete the flow from WhatsApp."""
		self.check_permission("write")
		flow_service.delete_from_whatsapp(self)

	@frappe.whitelist()
	def get_flow_preview(self):
		"""Get the preview URL for the flow."""
		# perm: read is enforced by run_doc_method
		return flow_service.get_flow_preview(self)

	@frappe.whitelist()
	def send_test(self, phone_number, message=None):
		"""Send a test flow message via the inbox pipeline."""
		self.check_permission("write")
		flow_service.send_test(self, phone_number, message)

	@frappe.whitelist()
	def get_flow_status(self):
		"""Get flow status and validation errors from WhatsApp."""
		# perm: read is enforced by run_doc_method
		return flow_service.get_flow_status(self)

	@frappe.whitelist()
	def sync_from_whatsapp(self):
		"""Sync flow details from WhatsApp."""
		self.check_permission("write")
		flow_service.sync_from_whatsapp(self)


@frappe.whitelist()
def get_whatsapp_flows(whatsapp_account):
	"""Get list of all flows from WhatsApp Business Account.

	Args:
	    whatsapp_account: Name of WhatsApp Account document

	Returns:
	    List of flows from WhatsApp
	"""
	check_read("WhatsApp Account", whatsapp_account)
	check_read("WhatsApp Flow")
	return flow_service.get_whatsapp_flows(whatsapp_account)


@frappe.whitelist()
def import_flow_from_whatsapp(whatsapp_account, flow_id, flow_name=None):
	"""Import a flow from WhatsApp into Frappe.

	Args:
	    whatsapp_account: Name of WhatsApp Account document
	    flow_id: WhatsApp Flow ID to import
	    flow_name: Optional name for the flow (uses WhatsApp name if not provided)

	Returns:
	    Name of created WhatsApp Flow document
	"""
	check_read("WhatsApp Account", whatsapp_account)
	check_create("WhatsApp Flow")
	return flow_service.import_flow_from_whatsapp(whatsapp_account, flow_id, flow_name)


@frappe.whitelist()
def sync_all_flows(whatsapp_account):
	"""Sync all flows from WhatsApp Business Account.

	Imports new flows and updates existing ones.

	Args:
	    whatsapp_account: Name of WhatsApp Account document

	Returns:
	    Dict with counts: imported, updated, skipped
	"""
	check_read("WhatsApp Account", whatsapp_account)
	check_create("WhatsApp Flow")
	return flow_service.sync_all_flows(whatsapp_account)
