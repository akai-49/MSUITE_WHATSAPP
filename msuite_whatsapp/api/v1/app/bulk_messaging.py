"""
Deprecated location — kept as a backward-compatible re-export layer.

The Vue SPA calls several of these functions by this exact dotted path
(`msuite_whatsapp.api.v1.app.bulk_messaging.*`) — see
`frontend/src/stores/whatsapp.js`. The real implementations moved to
`validators/recipient_validator.py`, `services/recipient_import_service.py`,
and `schedulers/bulk_message_scheduler.py` (see WHATSAPP_REFACTOR_PLAN.md §5/§7).
"""

import frappe

from msuite_whatsapp.services.permissions.checks import check_create
from msuite_whatsapp.tasks.bulk_message_scheduler import schedule_bulk_messages
from msuite_whatsapp.services.bulk.recipient_import_service import (
	download_sample_csv_template,
	export_recipients_csv,
	get_recipient_data_keys,
	import_recipients_from_file,
	parse_recipient_file,
)
from msuite_whatsapp.services.bulk.recipient_import_service import import_from_doctype as _import_from_doctype
from msuite_whatsapp.services.validators.recipient_validator import clean_mobile, match_country_code


@frappe.whitelist()
def get_progress(name):
	"""Get delivery progress for a bulk message."""
	doc = frappe.get_doc("Bulk WhatsApp Message", name, check_permission="read")
	return doc.get_progress()


@frappe.whitelist()
def retry_failed(name):
	"""Retry failed messages in a bulk campaign."""
	doc = frappe.get_doc("Bulk WhatsApp Message", name, check_permission="write")
	return {"requeued": doc.retry_failed()}


@frappe.whitelist()
def pause(name):
	"""Pause a bulk broadcast."""
	doc = frappe.get_doc("Bulk WhatsApp Message", name, check_permission="write")
	doc.pause_sending()
	return True


@frappe.whitelist()
def resume(name):
	"""Resume a paused bulk broadcast."""
	doc = frappe.get_doc("Bulk WhatsApp Message", name, check_permission="write")
	doc.resume_sending()
	return True


@frappe.whitelist()
def cancel(name):
	"""Cancel a bulk broadcast."""
	doc = frappe.get_doc("Bulk WhatsApp Message", name, check_permission="write")
	doc.cancel_sending()
	return True


@frappe.whitelist()
def import_recipients(
	list_name, doctype, mobile_field, name_field=None, filters=None, limit=None, data_fields=None
):
	"""Import recipients from a Frappe DocType into a Recipient List."""
	check_create("WhatsApp Recipient List")
	frappe.has_permission(doctype, "read", throw=True)
	return _import_from_doctype(
		list_name,
		doctype,
		mobile_field,
		name_field,
		filters,
		limit,
		data_fields,
	)


# `parse_recipient_file`, `import_recipients_from_file`, `export_recipients_csv`,
# and `get_recipient_data_keys` are already whitelisted in
# `services/recipient_import_service.py` is not the case — re-decorate here
# since the SPA calls them at *this* dotted path, not the service's.
parse_recipient_file = frappe.whitelist()(parse_recipient_file)  # perm: checks WhatsApp Recipient List read
import_recipients_from_file = frappe.whitelist()(import_recipients_from_file)  # perm: checks WhatsApp Recipient List write
export_recipients_csv = frappe.whitelist()(export_recipients_csv)  # perm: checks WhatsApp Recipient List read
get_recipient_data_keys = frappe.whitelist()(get_recipient_data_keys)  # perm: checks WhatsApp Recipient List read
download_sample_csv_template = frappe.whitelist()(download_sample_csv_template)  # perm: static template download
