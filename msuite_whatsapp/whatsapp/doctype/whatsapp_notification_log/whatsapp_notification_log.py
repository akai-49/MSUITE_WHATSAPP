# Copyright (c) 2022, Shridhar Patil and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class WhatsAppNotificationLog(Document):
	"""Deprecated send/webhook log doctype (WHATSAPP_REFACTOR_PLAN.md §10).

	Outcomes are now logged structurally via `frappe.logger` instead of as
	rows here (see `services.notification_service.notify` and
	`api/v1/whatsapp/webhook.post`). Historical rows are kept for
	reference; no new rows may be created.
	"""

	def before_insert(self):
		frappe.throw(
			_(
				"WhatsApp Notification Log is deprecated. Outcomes are now "
				"recorded via the application logger instead."
			)
		)
