"""
WhatsApp Analytics REST API endpoints.

Wraps the query service for external consumption.
All endpoints are plan-gated (analytics feature must be enabled).
"""

import frappe

from msuite_whatsapp.api.v1.app import analytics_query as query
from msuite_whatsapp.services.analytics import sync
from msuite_whatsapp.services.permissions.checks import check_read


@frappe.whitelist()
def get_dashboard_data(account_name: str, days: int = 30) -> dict:
	"""
	Get all dashboard data for a WhatsApp Account in one call.
	Reduces round-trips from the JS dashboard.
	"""
	check_read("WhatsApp Account", account_name)
	check_read("WhatsApp Analytics Snapshot")
	return {
		"summary": query.get_messaging_summary(account_name, days),
		"trend": query.get_messaging_trend(account_name, days),
		"response": query.get_response_metrics(account_name, days),
		"errors": query.get_error_breakdown(account_name, days),
		"templates": query.get_template_performance(account_name),
		"conversations": query.get_conversation_breakdown(account_name),
		"costs": query.get_cost_summary(account_name),
		"calls": query.get_call_summary(account_name),
	}


@frappe.whitelist()
def trigger_sync(account_name: str) -> dict:
	"""Manually trigger analytics sync for one account."""
	check_read("WhatsApp Account", account_name)
	check_read("WhatsApp Analytics Snapshot")
	sync.sync_all(account_name)
	sync.sync_template_analytics(account_name)
	return {"status": "success", "message": "Analytics synced."}
