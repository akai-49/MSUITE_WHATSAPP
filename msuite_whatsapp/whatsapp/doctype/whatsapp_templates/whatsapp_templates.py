"""
WhatsApp Templates — controller.

Lifecycle hooks and validation only. Meta API calls, payload building,
and sync live in `services/template_service.py`,
`services/template_sync_service.py`, and `providers/meta/template_provider.py`
— see WHATSAPP_REFACTOR_PLAN.md §4.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from msuite_whatsapp.queries.account_repository import get_whatsapp_account
from msuite_whatsapp.services.templates import template_service
from msuite_whatsapp.services.validators import template_validator


class WhatsAppTemplates(Document):
	def before_naming(self):
		"""Set language_code before autoname so the name includes it."""
		if self.template_name:
			self.template_name = template_validator.clean_template_name(self.template_name)
		if not self.language_code and self.language:
			lang_code = frappe.db.get_value("Language", self.language) or "en"
			self.language_code = lang_code.replace("-", "_")

	def validate(self):
		self.template_name = template_validator.validate_template_name(self.template_name)
		self.set_whatsapp_account()

		if not self.language_code or self.has_value_changed("language"):
			lang_code = frappe.db.get_value("Language", self.language) or "en"
			self.language_code = lang_code.replace("-", "_")

		# Auto-enable call permission when Voice Call button exists or CALL_PERMISSION_REQUEST type selected
		if (
			self.buttons and any(btn.button_type == "Voice Call" for btn in self.buttons)
		) or self.template_type == "CALL_PERMISSION_REQUEST":
			self.is_call_permission = 1
		elif (
			self.template_type
			and self.template_type != "CALL_PERMISSION_REQUEST"
			and not (self.buttons and any(btn.button_type == "Voice Call" for btn in self.buttons))
		):
			self.is_call_permission = 0

		template_validator.validate_media_sample(self.header_type, self.media_sample)
		template_validator.validate_catalog_template(self.template_type, self.category)
		template_validator.validate_commerce_template(
			self.template_type, self.header_type, self.category, self.template
		)
		template_validator.validate_buttons(self.buttons, self.category, self.offer_code)
		template_validator.validate_limited_time_offer(
			self.button_configuration, self.category, self.header_type, self.footer
		)
		self._normalize_flow_buttons()
		template_validator.validate_carousel_cards(self.is_carousel, self.carousel_cards)
		template_validator.validate_unique_name_per_language(
			self.template_name,
			self.language,
			self.name,
		)

	def _normalize_flow_buttons(self):
		"""Ensure Flow buttons have valid Link values to WhatsApp Flow or resolve from flow_id."""
		for btn in (self.buttons or []):
			if btn.get("button_type") == "Flow":
				flow_val = btn.get("flow")
				if flow_val and not frappe.db.exists("WhatsApp Flow", flow_val):
					matched = frappe.db.get_value(
						"WhatsApp Flow", {"flow_id": flow_val}, "name"
					) or frappe.db.get_value(
						"WhatsApp Flow", {"flow_name": flow_val}, "name"
					)
					if matched:
						btn.flow = matched
					else:
						# Keep flow_id on template and clear link to prevent LinkValidationError
						if not self.get("flow_id"):
							self.flow_id = flow_val
						btn.flow = None

	def after_insert(self):
		if self.status != "Draft" or frappe.flags.in_test:
			self.push_to_meta()

	def set_whatsapp_account(self):
		"""Set whatsapp account to default if missing."""
		if not self.whatsapp_account:
			default = get_whatsapp_account()
			if not default:
				frappe.throw(_("Please set a default outgoing WhatsApp Account or select one."))
			self.whatsapp_account = default.name

	@frappe.whitelist()
	def push_to_meta(self):
		"""Create or update this template on Meta."""
		self.check_permission("write")
		template_service.push_to_meta(self)

	def before_delete(self):
		"""Unlink or disable any local docs referencing this template before deletion."""
		_cleanup_template_links(self.name)

	def on_trash(self):
		"""Delete template from Meta when deleted locally."""
		if getattr(self.flags, "delete_from_msuite_only", False):
			return
		template_service.delete_from_meta(self)


def _cleanup_template_links(template_name: str):
	"""Unlink or disable any local docs referencing this template before deletion."""
	if not template_name:
		return
	# Other apps unlink their own records. Automation disables the rules that used this template.
	for listener in frappe.get_hooks("whatsapp_template_removed_listeners"):
		frappe.get_attr(listener)(template_name)
	if frappe.db.has_table("Bulk WhatsApp Message"):
		frappe.db.set_value(
			"Bulk WhatsApp Message",
			{"template": template_name},
			{"template": None},
			update_modified=False,
		)
	if frappe.db.has_table("Inbox Response Rule"):
		rule_field = "template" if frappe.db.has_column("Inbox Response Rule", "template") else (
			"whatsapp_template" if frappe.db.has_column("Inbox Response Rule", "whatsapp_template") else None
		)
		if rule_field:
			frappe.db.set_value(
				"Inbox Response Rule",
				{rule_field: template_name},
				{rule_field: None},
				update_modified=False,
			)

