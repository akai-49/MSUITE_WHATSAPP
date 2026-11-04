"""
WhatsApp Recipient List — controller.

Lifecycle hooks and validation only. Mobile-number normalization lives
in `validators/recipient_validator.py`; cross-doctype import lives in
`services/recipient_import_service.py`. See WHATSAPP_REFACTOR_PLAN.md §5/§6.
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document

from msuite_whatsapp.services.validators import recipient_validator


class WhatsAppRecipientList(Document):
	def validate(self):
		self.validate_recipients()
		recipient_validator.validate_and_normalize_recipients(self.recipients)

	def validate_recipients(self):
		if not self.is_new():
			if not self.recipients:
				frappe.throw(_("At least one recipient is required"))

	def import_list_from_doctype(
		self, doctype, mobile_field, name_field=None, filters=None, limit=None, data_fields=None
	):
		"""Import recipients from another DocType into this list (in-memory —
		caller is responsible for calling `save()` afterwards).

		Appends to the existing recipients (it used to silently wipe the
		list first). Rows with invalid numbers, or numbers already present
		in the list / earlier in this import, are skipped instead of
		aborting the whole import in validate().
		"""
		from msuite_core.utils.import_guard import assert_importable
		from msuite_whatsapp.services.validators.recipient_validator import clean_mobile

		assert_importable(doctype)
		self.import_from_doctype = 1
		self.doctype_to_import = doctype
		self.mobile_field = mobile_field
		if filters:
			self.import_filters = filters if isinstance(filters, str) else json.dumps(filters)
		if data_fields:
			self.data_fields = json.dumps(data_fields)
		if limit:
			self.import_limit = limit

		fields = [mobile_field]
		if name_field:
			fields.append(name_field)
		if data_fields:
			meta = frappe.get_meta(doctype)
			for field in meta.fields:
				if field.fieldname not in fields and field.fieldname in data_fields:
					fields.append(field.fieldname)

		records = frappe.get_list(doctype, filters=filters, fields=fields, limit=limit)

		seen = set()
		for row in self.recipients or []:
			cleaned, error = clean_mobile(row.mobile_number)
			if cleaned and not error:
				seen.add(cleaned)

		imported = 0
		for record in records:
			mobile, error = clean_mobile(record.get(mobile_field))
			if error or mobile in seen:
				continue
			seen.add(mobile)

			recipient_data = {}
			if data_fields:
				for field in data_fields:
					if record.get(field):
						variable_name = field.lower().replace(" ", "_")
						recipient_data[variable_name] = record.get(field)

			recipient = {
				"mobile_number": mobile,
				"recipient_data": json.dumps(recipient_data),
			}
			if name_field and record.get(name_field):
				recipient["recipient_name"] = record.get(name_field)

			self.append("recipients", recipient)
			imported += 1

		return imported
