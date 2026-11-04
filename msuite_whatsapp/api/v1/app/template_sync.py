"""Template sync the screens ask for."""

import frappe

from msuite_whatsapp.services.templates import template_sync_service


@frappe.whitelist()
def sync_all_accounts() -> str:
	# perm: the service allows System Manager and MSuite Admin only
	return template_sync_service.sync_all_accounts()
