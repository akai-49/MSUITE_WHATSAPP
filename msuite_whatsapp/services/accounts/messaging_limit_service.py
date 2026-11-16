"""Business-portfolio messaging tier, read from Meta.

Meta sets one messaging limit per business portfolio, shared by every number in
it, and raises it on its own schedule - so the tier stored on each phone row
(pushed once at connect time) goes stale. This refreshes it hourly and serves
`rate_limit_service` the current value.

Field chain, per Meta's docs: `whatsapp_business_manager_messaging_limit`
first, then the deprecated `messaging_limit_tier` (which, from Graph v24.0,
also returns the portfolio's limit), then whatever we last stored.
"""

from __future__ import annotations

import frappe
import requests

from msuite_whatsapp.constants import GRAPH_API_BASE, LOGGER_NAME
from msuite_whatsapp.queries import account_repository as accounts

TIER_FIELD = "whatsapp_business_manager_messaging_limit"
LEGACY_TIER_FIELD = "messaging_limit_tier"
CACHE_TTL_SEC = 60 * 60
REQUEST_TIMEOUT_SEC = 15

logger = frappe.logger(LOGGER_NAME)


def _cache_key(business_id: str) -> str:
	return f"wa_portfolio_tier:{business_id}"


def fetch_portfolio_tier(phone_number_id: str, token: str) -> str | None:
	"""The portfolio's current tier as Meta reports it for this number, or None
	on any failure (callers keep the last known tier)."""
	try:
		resp = requests.get(
			f"{GRAPH_API_BASE}/{phone_number_id}",
			params={"fields": f"{TIER_FIELD},{LEGACY_TIER_FIELD}"},
			headers={"Authorization": f"Bearer {token}"},
			timeout=REQUEST_TIMEOUT_SEC,
		)
		if not resp.ok:
			return None
		body = resp.json() or {}
	except (requests.RequestException, ValueError):
		return None
	return body.get(TIER_FIELD) or body.get(LEGACY_TIER_FIELD) or None


def _portfolio_accounts(business_id: str) -> list[str]:
	return frappe.get_all(
		accounts.ACCOUNT_DOCTYPE,
		filters={"business_id": business_id, "status": accounts.STATUS_ACTIVE},
		pluck="name",
	)


def _stored_tier(business_id: str) -> str | None:
	"""Last tier we stored on any phone of the portfolio."""
	for account in _portfolio_accounts(business_id):
		tier = frappe.db.get_value(
			accounts.PHONE_CHILD_DOCTYPE, {"parent": account, "messaging_limit_tier": ["!=", ""]}, "messaging_limit_tier"
		)
		if tier:
			return tier
	return None


def get_portfolio_tier(business_id: str) -> str | None:
	"""Current tier for a portfolio: fresh cached value, else the stored one."""
	if not business_id:
		return None
	cached = frappe.cache().get_value(_cache_key(business_id))
	return cached or _stored_tier(business_id)


def refresh_portfolio(business_id: str) -> None:
	"""Ask Meta for the portfolio's tier and store it on every phone in it."""
	for account in _portfolio_accounts(business_id):
		phone = frappe.db.get_value(
			accounts.PHONE_CHILD_DOCTYPE, {"parent": account}, "phone_number_id", order_by="idx asc"
		)
		if not phone:
			continue
		try:
			_, _, token = accounts.get_credentials(account)
		except Exception:
			continue  # no token on this account; another account of the portfolio may have one
		tier = fetch_portfolio_tier(phone, token)
		if not tier:
			continue
		for name in _portfolio_accounts(business_id):
			frappe.db.sql(
				f"UPDATE `tab{accounts.PHONE_CHILD_DOCTYPE}` SET messaging_limit_tier = %s WHERE parent = %s",
				(tier, name),
			)
		frappe.cache().set_value(_cache_key(business_id), tier, expires_in_sec=CACHE_TTL_SEC)
		return
	logger.warning("No messaging tier refreshed for portfolio %s - keeping the last known one", business_id)


def refresh_all() -> None:
	"""Scheduler: refresh every portfolio that has an active WhatsApp account."""
	for business_id in sorted(
		set(frappe.get_all(accounts.ACCOUNT_DOCTYPE, filters={"status": accounts.STATUS_ACTIVE}, pluck="business_id"))
	):
		if not business_id:
			continue
		try:
			refresh_portfolio(business_id)
		except Exception:
			logger.exception("Messaging tier refresh failed for portfolio %s", business_id)
		if not frappe.flags.in_test:  # the test runner rolls back per test
			frappe.db.commit()
