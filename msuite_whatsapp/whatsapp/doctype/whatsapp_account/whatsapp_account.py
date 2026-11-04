"""
WhatsApp Account controller.

One record per WABA (WhatsApp Business Account). Token is WABA-scoped.
Phone numbers are child rows — each can be default incoming/outgoing.

Lifecycle hooks and validation only — default-account promotion/demotion
orchestration lives in `services/account_service.py`; phone/credential
resolution lives in `repositories/account_repository.py`. See
WHATSAPP_REFACTOR_PLAN.md §4.
"""

import frappe
from frappe.model.document import Document

from msuite_whatsapp.queries import account_repository as accounts
from msuite_whatsapp.services.accounts import account_service

STATUS_ACTIVE = "Active"


class WhatsAppAccount(Document):
	def after_insert(self):
		self.sync_aws_secret()

	def on_update(self):
		if self.has_value_changed("status"):
			account_service.handle_status_change(self.name, self.status)
		self.sync_aws_secret()

	def sync_aws_secret(self):
		"""Sync credentials to AWS Secrets Manager via provider if AWS pipeline is ready."""
		try:
			from msuite_campaigns.aws_pipeline import client as aws_client
			from msuite_campaigns.aws_pipeline import dispatch as aws_dispatch

			if not aws_dispatch.is_ready("whatsapp"):
				return
			token = self.get_password("token", raise_exception=False)
			if token:
				aws_client.sync_channel_secret("whatsapp", {"access_token": token})
		except Exception as e:
			frappe.logger().warning(f"AWS secret sync for WhatsApp Account {self.name} skipped: {e}")

	def get_default_phone(self, phone_type: str = "outgoing"):
		"""Get the default phone for sending/receiving.

		Args:
		    phone_type: "outgoing" or "incoming"

		Returns:
		    WhatsApp Phone Number child row, or first active phone, or None
		"""
		return accounts.get_default_phone(self, phone_type)

