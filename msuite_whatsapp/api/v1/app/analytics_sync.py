"""Analytics refreshes the screens ask for."""

import frappe

from msuite_whatsapp.services.analytics import sync


@frappe.whitelist()
def refresh_campaign(campaign_name: str) -> dict:
	# perm: the service checks read on the Marketing Campaign
	return sync.refresh_campaign(campaign_name=campaign_name)


@frappe.whitelist()
def refresh_account_analytics(account_name: str) -> dict:
	# perm: the service checks read on the WhatsApp Account
	return sync.refresh_account_analytics(account_name=account_name)
