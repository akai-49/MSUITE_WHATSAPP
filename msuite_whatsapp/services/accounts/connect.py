"""What WhatsApp plugs into core's Connect: credential pushes and the account lists."""

import frappe
import requests

from msuite_core.constants import GRAPH_API_URL, GRAPH_API_VERSION, LOGGER_NAME, AccountStatus
# One shared dispatcher for the optional avatar handler (hook, else msuite_social when installed).
from msuite_core.services.connections.profile import _enqueue_account_avatar  # noqa: F401

logger = frappe.logger(LOGGER_NAME)

WHATSAPP_ACCOUNT_DOCTYPE = "WhatsApp Account"


def _handle_whatsapp_credentials(credentials):
	"""
	Create or update WhatsApp Account (one per WABA) with phones as child rows.

	One WhatsApp Account record per WABA. Token is WABA-scoped (shared
	across all phones). Phone numbers are child table rows.
	"""
	waba_id = credentials.get("waba_id", "")

	if not waba_id:
		logger.warning("No waba_id in WhatsApp credentials, skipping")
		return

	# Handle revocation from provider
	if credentials.get("revoked"):
		existing = frappe.db.get_value("WhatsApp Account", {"waba_id": waba_id}, "name")
		if existing:
			frappe.db.set_value("WhatsApp Account", existing, "status", "Inactive")
			logger.info(f"WhatsApp Account {existing} marked Inactive (revoked by provider)")
			frappe.db.commit()
		return

	waba_name = credentials.get("waba_name", "")
	token = credentials.get("system_user_token", "")
	business_id = credentials.get("business_id", "")
	business_name = credentials.get("business_name", "")
	app_id = credentials.get("app_id", "")
	phones = credentials.get("phones", [])
	avatar_url = (
		credentials.get("avatar_url")
		or credentials.get("profile_picture_url")
		or ""
	)

	# If avatar wasn't pushed by provider, fetch it synchronously now so Connections page displays it on 1st load
	if not avatar_url and phones and token:
		default_phone = next((p for p in phones if p.get("is_default_outgoing")), None) or phones[0]
		phone_id = default_phone.get("phone_number_id")
		if phone_id:
			try:
				resp = requests.get(
					f"{GRAPH_API_URL}/{GRAPH_API_VERSION}/{phone_id}/whatsapp_business_profile",
					params={"fields": "profile_picture_url"},
					headers={"Authorization": f"Bearer {token}"},
					timeout=10,
				)
				if resp.status_code == 200:
					data = resp.json().get("data", [])
					avatar_url = (data[0] if data else {}).get("profile_picture_url", "")
			except Exception as e:
				logger.warning(f"Could not fetch WhatsApp avatar synchronously: {e}")

	account_name = waba_name or f"WABA {waba_id}"

	# Upsert by waba_id (one record per WABA)
	existing = frappe.db.get_value("WhatsApp Account", {"waba_id": waba_id}, "name")

	if existing:
		doc = frappe.get_doc("WhatsApp Account", existing)
		doc.status = "Active"
		doc.needs_reauth = 0
		doc.last_token_error = ""
		doc.token = token
		doc.waba_name = waba_name
		doc.business_name = business_name
		doc.business_id = business_id
		if avatar_url:
			doc.avatar_url = avatar_url
		if app_id:
			doc.app_id = app_id
		doc.waba_currency = credentials.get("waba_currency", "")
		doc.waba_timezone = credentials.get("waba_timezone", "")
		if credentials.get("is_coexistence"):
			doc.is_coexistence = 1
			if not doc.coexistence_history_sync:
				doc.coexistence_history_sync = "Requested"
		_sync_phones(doc, phones)
		doc.save(ignore_permissions=True)
		logger.info(f"WhatsApp Account updated: {account_name} ({waba_id}), {len(phones)} phones")
		if avatar_url:
			_enqueue_account_avatar(WHATSAPP_ACCOUNT_DOCTYPE, doc.name, avatar_url)
	else:
		doc = frappe.new_doc("WhatsApp Account")
		doc.account_name = account_name
		doc.status = AccountStatus.ACTIVE
		doc.token = token
		doc.waba_id = waba_id
		doc.waba_name = waba_name
		doc.business_name = business_name
		doc.business_id = business_id
		if avatar_url:
			doc.avatar_url = avatar_url
		if app_id:
			doc.app_id = app_id
		doc.waba_currency = credentials.get("waba_currency", "")
		doc.waba_timezone = credentials.get("waba_timezone", "")
		if credentials.get("is_coexistence"):
			doc.is_coexistence = 1
			doc.coexistence_history_sync = "Requested"
		for i, phone in enumerate(phones):
			doc.append(
				"phones",
				{
					"phone_number_id": phone.get("phone_number_id", ""),
					"display_phone_number": phone.get("display_phone_number", ""),
					"verified_name": phone.get("verified_name", ""),
					"quality_rating": phone.get("quality_rating", ""),
					"messaging_limit_tier": phone.get("messaging_limit_tier", ""),
					"platform_type": phone.get("platform_type", ""),
					"is_on_biz_app": 1 if phone.get("is_on_biz_app") else 0,
					"is_default_outgoing": 1 if i == 0 else 0,
					"is_default_incoming": 1 if i == 0 else 0,
					"status": "Active",
				},
			)
		doc.insert(ignore_permissions=True)
		logger.info(f"WhatsApp Account created: {account_name} ({waba_id}), {len(phones)} phones")
		if avatar_url:
			_enqueue_account_avatar(WHATSAPP_ACCOUNT_DOCTYPE, doc.name, avatar_url)

		# Trigger Templates, Flows, and Analytics sync for newly connected/updated WhatsApp account
		_trigger_whatsapp_connect_sync(doc.name)

	frappe.db.commit()

	# Enqueue background refresh to keep daily sync and CDN re-signing active
	try:
		frappe.enqueue(
			"msuite_core.services.connections.profile._refresh_whatsapp_account",
			name=doc.name,
			queue="short",
			enqueue_after_commit=True,
		)
		frappe.enqueue(
			"msuite_whatsapp.services.accounts.phone_onboarding_service.sync_account_usernames",
			account=doc.name,
			queue="short",
			enqueue_after_commit=True,
		)
	except Exception:
		pass


def _trigger_whatsapp_connect_sync(account_name: str) -> None:
	"""Enqueue template, flow, and analytics synchronization upon WhatsApp account connection."""
	try:
		# 1. Sync WhatsApp Templates
		frappe.enqueue(
			"msuite_whatsapp.services.templates.template_sync_service.sync_all_accounts",
			queue="long",
			enqueue_after_commit=True,
		)
		# 2. Sync WhatsApp Flows
		frappe.enqueue(
			"msuite_whatsapp.whatsapp.doctype.whatsapp_flow.whatsapp_flow.sync_all_flows",
			whatsapp_account=account_name,
			queue="long",
			enqueue_after_commit=True,
		)
		# 3. Sync WhatsApp Analytics
		frappe.enqueue(
			"msuite_whatsapp.services.analytics.sync.sync_all",
			account_name=account_name,
			queue="long",
			enqueue_after_commit=True,
		)
		frappe.enqueue(
			"msuite_whatsapp.services.analytics.sync.sync_template_analytics",
			account_name=account_name,
			queue="long",
			enqueue_after_commit=True,
		)
		logger.info(f"Enqueued WhatsApp connect sync (templates, flows, analytics) for {account_name}")
	except Exception as e:
		logger.warning(f"Could not enqueue WhatsApp connect sync for {account_name}: {e}")


def _sync_phones(doc, phones):
	"""Sync phone child rows — upsert by phone_number_id."""
	existing_ids = {p.phone_number_id: p for p in (doc.phones or [])}
	for phone in phones:
		pid = phone.get("phone_number_id", "")
		if not pid:
			continue
		if pid in existing_ids:
			row = existing_ids[pid]
			row.display_phone_number = phone.get("display_phone_number", row.display_phone_number)
			row.verified_name = phone.get("verified_name", row.verified_name)
			row.quality_rating = phone.get("quality_rating", row.quality_rating)
			row.messaging_limit_tier = phone.get("messaging_limit_tier", row.messaging_limit_tier)
			if phone.get("platform_type"):
				row.platform_type = phone["platform_type"]
			if "is_on_biz_app" in phone:
				row.is_on_biz_app = 1 if phone.get("is_on_biz_app") else 0
		else:
			doc.append(
				"phones",
				{
					"phone_number_id": pid,
					"display_phone_number": phone.get("display_phone_number", ""),
					"verified_name": phone.get("verified_name", ""),
					"quality_rating": phone.get("quality_rating", ""),
					"messaging_limit_tier": phone.get("messaging_limit_tier", ""),
					"platform_type": phone.get("platform_type", ""),
					"is_on_biz_app": 1 if phone.get("is_on_biz_app") else 0,
					"status": "Active",
				},
			)


def _trigger_analytics_backfill(account_name: str):
	"""Enqueue analytics backfill for a newly connected account (last 30 days)."""
	from msuite_whatsapp.constants import ANALYTICS_BACKFILL_DAYS
	from msuite_core.services.plans.plan_enforcer import is_feature_enabled

	if not is_feature_enabled("analytics"):
		return

	try:
		frappe.enqueue(
			"msuite_whatsapp.services.analytics.sync.sync_all",
			queue="long",
			account_name=account_name,
			days=ANALYTICS_BACKFILL_DAYS,
		)
		logger.info(f"Analytics backfill enqueued for {account_name}")
	except Exception as e:
		logger.warning(f"Analytics backfill failed to enqueue for {account_name}: {e}")


def connected_accounts() -> list[dict]:
	"""WhatsApp accounts for the Connections page. Registered as `msuite_connected_accounts`."""
	if not frappe.has_permission("WhatsApp Account", "read"):
		return []
	return frappe.get_all(
		"WhatsApp Account",
		fields=[
			"name",
			"account_name",
			"status",
			"waba_id",
			"avatar_url",
			"needs_reauth",
			"last_token_error",
			"last_verified_at",
		],
		limit=100,
	)


def analytics_agent_accounts() -> list[dict]:
	"""WhatsApp accounts for the analytics agent. Registered as `msuite_analytics_agent_accounts`."""
	from msuite_whatsapp.queries.account_repository import get_display_phone_number

	fields = ["name"]
	if frappe.db.has_column("WhatsApp Account", "account_name"):
		fields.append("account_name")
	accounts = frappe.get_list("WhatsApp Account", fields=fields)
	for account in accounts:
		account["display_phone_number"] = get_display_phone_number(account["name"])
	return accounts
