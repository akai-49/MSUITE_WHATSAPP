"""Phone-number onboarding endpoints: status, request OTP, verify OTP, register.

Thin wrappers over `phone_onboarding_service`; each returns the service's
`{ok, data | error}` envelope. The three state-changing calls are POST-only.
"""

import frappe

from msuite_core.services.permissions.checks import check_read, check_write
from msuite_whatsapp.queries.account_repository import ACCOUNT_DOCTYPE
from msuite_whatsapp.services.accounts import phone_onboarding_service as onboarding


@frappe.whitelist()
def get_phone_status(account: str, phone_number_id: str) -> dict:
	check_read(ACCOUNT_DOCTYPE, account)
	return onboarding.get_status(account, phone_number_id)


@frappe.whitelist()
def get_phone_username(account: str, phone_number_id: str) -> dict:
	check_read(ACCOUNT_DOCTYPE, account)
	return onboarding.get_username(account, phone_number_id)


@frappe.whitelist(methods=["POST"])
def request_phone_code(account: str, phone_number_id: str, code_method: str = "SMS", language: str = "en_US") -> dict:
	check_write(ACCOUNT_DOCTYPE, account)
	return onboarding.request_code(account, phone_number_id, code_method, language)


@frappe.whitelist(methods=["POST"])
def verify_phone_code(account: str, phone_number_id: str, code: str) -> dict:
	check_write(ACCOUNT_DOCTYPE, account)
	return onboarding.verify_code(account, phone_number_id, code)


@frappe.whitelist(methods=["POST"])
def register_phone(account: str, phone_number_id: str, pin: str) -> dict:
	check_write(ACCOUNT_DOCTYPE, account)
	return onboarding.register(account, phone_number_id, pin)
