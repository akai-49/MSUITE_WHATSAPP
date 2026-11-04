import frappe
from frappe.model.document import Document


class WhatsAppCall(Document):
	def before_save(self):
		if self.duration_seconds and self.duration_seconds > 0:
			minutes = self.duration_seconds // 60
			seconds = self.duration_seconds % 60
			self.duration_display = f"{minutes:02d}:{seconds:02d}"
