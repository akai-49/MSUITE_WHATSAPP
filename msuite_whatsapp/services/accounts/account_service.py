"""
WhatsApp Account service — default-account promotion/demotion.

Extracted from the `WhatsApp Account` doctype controller so the
controller only contains lifecycle hooks (see WHATSAPP_REFACTOR_PLAN.md §4).
"""

from __future__ import annotations

import frappe

from msuite_whatsapp.queries import account_repository as accounts

SETTINGS_DOCTYPE = "WhatsApp Settings"
STATUS_ACTIVE = "Active"
DEFAULT_FIELDS = ("default_outgoing_account", "default_incoming_account")


def handle_status_change(account_name: str, new_status: str) -> None:
	"""Promote/demote this account as the system default when its status
	transitions to/away from Active.

	Tab visibility: CRM's WhatsApp tab is gated by
	WhatsApp Settings.default_outgoing_account pointing to an Active
	account. We keep that link healthy automatically: promote on
	activation, demote (with fallback) on deactivation. This avoids
	relying on manual setup after every fresh install or reconnection.
	"""
	if new_status == STATUS_ACTIVE:
		_promote_as_default_if_needed(account_name)
	else:
		_demote_if_default(account_name)


def _promote_as_default_if_needed(account_name: str) -> None:
	"""Claim the WhatsApp Settings default slots if they are empty or stale.

	Runs when an account transitions to Active. Only writes when the current
	default is missing or points to a non-Active account — an operator's
	explicit choice of a different active default is always respected.
	"""
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	dirty = False

	for field in DEFAULT_FIELDS:
		current = settings.get(field)
		if not current or not accounts.is_account_active(current):
			settings.set(field, account_name)
			dirty = True

	if dirty:
		settings.save(ignore_permissions=True)


def _demote_if_default(account_name: str) -> None:
	"""Replace this account in the default slots if it was selected.

	Runs when an account transitions away from Active. Falls back to any
	other Active account; if none exists, clears the field so the CRM tab
	hides cleanly rather than pointing at a broken account.
	"""
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	if not any(settings.get(field) == account_name for field in DEFAULT_FIELDS):
		return

	replacement = accounts.find_active_account(exclude=account_name)
	for field in DEFAULT_FIELDS:
		if settings.get(field) == account_name:
			settings.set(field, replacement)

	settings.save(ignore_permissions=True)
