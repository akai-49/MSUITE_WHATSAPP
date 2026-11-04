from frappe.model.document import Document

from msuite_whatsapp.services.validators import recipient_validator


class WhatsAppRecipient(Document):
	"""Frappe doesn't call a child controller's validate() when rows are
	saved as part of the parent -- WhatsAppRecipientList.validate() is the
	path that actually runs for desk-grid edits, CSV import, etc. This
	hook only fires if a row is loaded and saved standalone (e.g. the
	grid's "expand row" full-page editor), so keep it for that case."""

	def validate(self):
		self.validate_mobile_number()

	def validate_mobile_number(self):
		self.mobile_number = recipient_validator.validate_single_mobile_number(self.mobile_number)
		if self.mobile_number.startswith("+"):
			country_name, _isd = recipient_validator.match_country_code(self.mobile_number[1:])
			self.country_code = country_name
