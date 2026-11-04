import frappe
from frappe.model.document import Document
from frappe.utils import add_to_date


class WhatsAppCallPermission(Document):
	def before_save(self):
		if self.last_request_sent_at:
			self.can_request_again_at = add_to_date(self.last_request_sent_at, hours=24)
