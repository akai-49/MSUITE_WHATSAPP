# Copyright (c) 2024, shridhar patil and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class WhatsAppContact(Document):
	"""Deprecated contact-directory doctype (WHATSAPP_REFACTOR_PLAN.md §10).

	The Desk chat widget that created these rows has been removed —
	contacts are now Channel Handle records. Historical rows are kept for
	reference; no new rows may be created.
	"""

	def before_insert(self):
		frappe.throw(
			_("WhatsApp Contact is deprecated. New contacts are created as Channel Handle records instead.")
		)
