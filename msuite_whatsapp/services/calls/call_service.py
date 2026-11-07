"""
Calling — routing, permissions, active-call management, state transitions,
and analytics for voice calls on any Inbox channel.

Per INBOX_ARCHITECTURE_AUDIT.md §1/§3/§10 and the approved refactor plan:
calling is part of the Business Communication Platform and belongs to
Inbox, not to the WhatsApp module — even though WhatsApp is the only
channel with Calling today. This module absorbs the call-routing logic
that used to live in `services/call_router.py` *and* the call-lifecycle/
permission business logic that used to live directly inside
`api/v1/whatsapp/calls.py`. That file is now a thin API layer that
delegates here (API → Service → Repository/Provider).

The one piece that deliberately stays in the WhatsApp module is the
literal Meta Graph API HTTP call (`providers.meta.call_provider.meta_call_action`)
and WhatsApp Account credential resolution
(`repositories.account_repository`) — those are channel-transport
concerns, not calling-domain concerns. This module calls into them the
same way `outbound.py` calls into a channel's `send()`.

Today every call/permission record is a `WhatsApp Call`/`WhatsApp Call
Permission` doctype (WhatsApp is the only channel with telephony), so
this module necessarily talks to those doctypes by name — that is a
statement about the current channel landscape, not a layering
violation: the *routing, state-machine, and permission* logic is
channel-and-CRM domain logic that lives correctly in Inbox.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional

import frappe
from frappe import _
from frappe.utils import get_datetime, now

from msuite_core.constants import GRAPH_API_BASE, LOGGER_NAME, REQUEST_TIMEOUT, CallDirection
from msuite_whatsapp.constants import (
	CALL_PERMISSION_AUTO_REVOKE_THRESHOLD,
	CALL_PERMISSION_COOLDOWN_HOURS,
	CALL_STATUS_MAP,
	CALL_TERMINAL_STATES,
	CallStatus,
	PermissionStatus,
)
from msuite_inbox.inbox import events as inbox_events
from msuite_inbox.inbox.constants import ChannelType
from msuite_whatsapp.services.channels.inbox_channel import is_bsuid

logger = frappe.logger(LOGGER_NAME)

CALL_DOCTYPE = "WhatsApp Call"
PERMISSION_DOCTYPE = "WhatsApp Call Permission"

# Statuses that mean "the agent is mid-call and shouldn't be handed another".
_BUSY_STATUSES = (CallStatus.RINGING, CallStatus.CONNECTED)

# Maximum plausible age for each "busy" status — see `is_agent_busy`.
_STALE_RINGING_SECONDS = 2 * 60
_STALE_CONNECTED_SECONDS = 2 * 60 * 60

# Permission window per Meta spec — once a contact grants, they stay
# opted-in for this long absent an explicit `expiration_timestamp`.
_PERMISSION_WINDOW_SECONDS = 7 * 24 * 3600


def _account_repo():
	from msuite_whatsapp.queries import account_repository

	return account_repository


def _meta_call_action(wa, action, call_id=None, sdp=None, sdp_type=None, to=None):
	from msuite_whatsapp.integrations.meta.call_provider import meta_call_action

	return meta_call_action(wa, action, call_id=call_id, sdp=sdp, sdp_type=sdp_type, to=to)


def _sync_crm_best_effort(call_name: str) -> None:
	"""Mirror this call's current state into CRM Call Log (see
	crm_sync.py). Most WhatsApp Call writes go through `frappe.db.set_value`
	rather than `doc.save()`, so a doctype `on_update` hook would silently
	miss them the same way `can_request_again_at` did — called explicitly
	at every status-transition site instead. Best-effort: a CRM sync
	failure must never take down call handling itself."""
	try:
		from msuite_inbox.inbox.services import crm_sync

		crm_sync.sync_call_to_crm(call_name)
	except Exception:
		logger.exception("CRM Call Log sync failed for %s", call_name)


def get_calling_settings(whatsapp_account=None) -> dict:
	"""Read-only Calling status for the header badge / settings screen —
	lets the UI warn *before* an agent hits (#138000) on an actual call."""
	from msuite_whatsapp.integrations.meta.call_provider import get_calling_settings as _get

	wa = resolve_wa_account(whatsapp_account)
	return _get(wa)


def enable_calling(whatsapp_account=None) -> dict:
	"""Attempt to turn on Calling for this phone number. See
	`call_provider.enable_calling` docstring — this only works once Meta
	has made Calling available for the WABA; otherwise Meta's own error
	is raised verbatim, telling the caller to finish enabling it in
	WhatsApp Manager."""
	from msuite_whatsapp.integrations.meta.call_provider import enable_calling as _enable

	wa = resolve_wa_account(whatsapp_account)
	return _enable(wa)


def _format_number(number: str | None) -> str | None:
	if not number:
		return number
	return number[1:] if number.startswith("+") else number


# ═══════════════════════════════════════════════════════════════════════
# Call routing — pick the agent who should receive an inbound call.
# ═══════════════════════════════════════════════════════════════════════


def resolve_target_user(phone: str, whatsapp_account: str) -> str | None:
	"""Pick the CRM user who should receive an inbound call from `phone`.

	Resolution order (first hit wins):
	  1. Frappe Contact (most durable identity)         → first `_assign` user
	  2. CRM Deal      (active opportunity)             → `deal_owner` / `_assign`
	  3. CRM Lead      (top of funnel)                  → `lead_owner` / `_assign`
	  4. WhatsApp Account.default_call_agent            (account-wide fallback)
	"""
	cleaned = _strip_phone(phone)
	if not cleaned:
		return _default_call_agent(whatsapp_account)

	contact_user = _resolve_contact_owner(cleaned)
	if contact_user:
		return contact_user

	deal_user = _resolve_deal_owner(cleaned)
	if deal_user:
		return deal_user

	lead_user = _resolve_lead_owner(cleaned)
	if lead_user:
		return lead_user

	return _default_call_agent(whatsapp_account)


def is_agent_busy(user: str, exclude_call_id: str | None = None) -> bool:
	"""True if `user` is already on a *live* call (age-guarded against
	orphaned Ringing/Connected rows — see module docstring history)."""
	if not user:
		return False

	now_dt = datetime.now()
	ringing_floor = now_dt - timedelta(seconds=_STALE_RINGING_SECONDS)
	connected_floor = now_dt - timedelta(seconds=_STALE_CONNECTED_SECONDS)

	base_filters = {"agent": user}
	if exclude_call_id:
		base_filters["call_id"] = ("!=", exclude_call_id)

	if frappe.db.exists(
		CALL_DOCTYPE,
		{
			**base_filters,
			"status": CallStatus.RINGING,
			"start_time": (">", ringing_floor),
		},
	):
		return True
	if frappe.db.exists(
		CALL_DOCTYPE,
		{
			**base_filters,
			"status": CallStatus.CONNECTED,
			"start_time": (">", connected_floor),
		},
	):
		return True
	return False


def sweep_stale_calls() -> dict:
	"""Scheduler hook — close out Call rows stranded in Ringing/Connected."""
	now_dt = datetime.now()
	cutoffs = (
		(CallStatus.RINGING, now_dt - timedelta(seconds=_STALE_RINGING_SECONDS)),
		(CallStatus.CONNECTED, now_dt - timedelta(seconds=_STALE_CONNECTED_SECONDS)),
	)
	closed = []
	for status, floor in cutoffs:
		names = frappe.get_all(
			CALL_DOCTYPE,
			filters={"status": status, "start_time": ("<", floor)},
			pluck="name",
		)
		for name in names:
			frappe.db.set_value(
				CALL_DOCTYPE,
				name,
				{
					"status": CallStatus.FAILED,
					"end_time": frappe.utils.now(),
				},
				update_modified=False,
			)
			closed.append(name)
	if closed:
		frappe.db.commit()
	return {"closed": closed, "count": len(closed)}


def _find_party_via_canonical(doctype: str, phone: str) -> str | None:
	"""Single-doctype lookup routed through the canonical existence
	check (crm_lead_core.api.v1.lead) so call routing matches people exactly the
	way identity resolution and the external check_exists API do."""
	from custom_crm.api.v1.lead import find_existing_party

	match = find_existing_party(phone=phone, priority=(doctype,))
	return match[1] if match else None


def _resolve_contact_owner(phone: str) -> str | None:
	name = _find_party_via_canonical("Contact", phone)
	if not name:
		return None
	assign_json = frappe.db.get_value("Contact", name, "_assign")
	return _first_assignee(assign_json)


def _resolve_deal_owner(phone: str) -> str | None:
	name = _find_party_via_canonical("CRM Deal", phone)
	if not name:
		return None
	deal = frappe.db.get_value("CRM Deal", name, ["deal_owner", "_assign"], as_dict=True)
	if not deal:
		return None
	return deal.get("deal_owner") or _first_assignee(deal.get("_assign"))


def _resolve_lead_owner(phone: str) -> str | None:
	name = _find_party_via_canonical("CRM Lead", phone)
	if not name:
		return None
	lead = frappe.db.get_value("CRM Lead", name, ["lead_owner", "_assign"], as_dict=True)
	if not lead:
		return None
	return lead.get("lead_owner") or _first_assignee(lead.get("_assign"))


def _default_call_agent(whatsapp_account: str | None) -> str | None:
	if not whatsapp_account:
		return None
	return frappe.db.get_value("WhatsApp Account", whatsapp_account, "default_call_agent") or None


def _strip_phone(phone: str) -> str:
	if not phone:
		return ""
	return phone.lstrip("+").strip()


def _first_assignee(assign_json: str | None) -> str | None:
	if not assign_json:
		return None
	try:
		users = json.loads(assign_json)
	except (TypeError, ValueError):
		return None
	if isinstance(users, list) and users:
		return users[0]
	return None


# ═══════════════════════════════════════════════════════════════════════
# Webhook ingestion — call state transitions
# ═══════════════════════════════════════════════════════════════════════


def process_call_event(call: dict) -> None:
	"""Process a single call event — create or update a WhatsApp Call record."""
	call_id = call.get("id", "")
	if not call_id:
		return

	event = call.get("event", "")
	call_status = call.get("status", "")
	phone_number_id = call.get("_phone_number_id", "")
	direction = (
		CallDirection.INBOUND
		if call.get("direction", "USER_INITIATED") == "USER_INITIATED"
		else CallDirection.OUTBOUND
	)

	existing = frappe.db.get_value(
		CALL_DOCTYPE,
		{"call_id": call_id},
		["name", "status", "agent"],
		as_dict=True,
	)

	if not existing and direction == CallDirection.OUTBOUND:
		callee = call.get("to", "")
		if callee and len(callee) >= 10:
			existing = frappe.db.get_value(
				CALL_DOCTYPE,
				{
					"callee_number": ["like", f"%{_format_number(callee)[-10:]}"],
					"direction": CallDirection.OUTBOUND,
					"status": ["not in", list(CALL_TERMINAL_STATES)],
				},
				["name", "status", "agent"],
				as_dict=True,
			)
			if existing:
				frappe.db.set_value(CALL_DOCTYPE, existing.name, "call_id", call_id)

	wa_account = _account_repo().get_whatsapp_account(phone_number_id)
	account_name = wa_account.name if wa_account else ""

	if existing:
		_update_existing_call(existing, call, event, call_status, direction, account_name)
	else:
		_create_new_call(call, call_id, call_status, direction, account_name, phone_number_id)


def _update_existing_call(existing, call, event, call_status, direction, account_name):
	if existing.status in CALL_TERMINAL_STATES:
		return

	mapped_status = CALL_STATUS_MAP.get(call_status.upper(), call_status) if call_status else None
	updates = {"raw_webhook": json.dumps(call)}

	# Forward-compatible: capture recording URL if Meta provides it
	recording = call.get("recording_url") or call.get("recording", {}).get("url")
	if recording:
		updates["recording_url"] = recording

	is_terminal = event == "terminate" or (mapped_status and mapped_status in CALL_TERMINAL_STATES)
	if is_terminal:
		updates["end_time"] = now()
		dur = _extract_duration(call)
		if dur is not None:
			updates["duration_seconds"] = dur
			updates["duration_display"] = _format_duration(dur)
		if mapped_status == CallStatus.COMPLETED and (dur or 0) == 0:
			mapped_status = CallStatus.MISSED

	if mapped_status:
		updates["status"] = mapped_status

	frappe.db.set_value(CALL_DOCTYPE, existing.name, updates)
	_sync_crm_best_effort(existing.name)

	if is_terminal:
		if mapped_status in (CallStatus.MISSED, CallStatus.FAILED):
			_handle_missed_call(call, direction, account_name)
		elif mapped_status == CallStatus.COMPLETED:
			_handle_completed_call(call, direction, account_name)

		try:
			_record_call_event_in_chat(
				call_name=existing.name,
				call_id=call.get("id", ""),
				direction=direction,
				status=mapped_status or existing.status,
				duration_seconds=updates.get("duration_seconds"),
				remote_number=_get_remote_number(call, direction),
				wa_account_name=account_name,
			)
		except Exception:
			logger.exception("Failed to record call event in chat (existing call)")

		inbox_events.emit(
			inbox_events.CALL_ENDED,
			{
				"call_name": existing.name,
				"call_id": call.get("id"),
				"status": mapped_status or existing.status,
				"direction": direction,
			},
		)

	frappe.publish_realtime(
		"whatsapp_call_update",
		{
			"call_name": existing.name,
			"call_id": call.get("id"),
			"event": event,
			"status": mapped_status or existing.status,
			"direction": direction,
		},
	)

	session = call.get("session", {})
	if event == "connect" and session.get("sdp"):
		frappe.publish_realtime(
			"whatsapp_call_sdp_answer",
			{
				"call_name": existing.name,
				"call_id": call.get("id"),
				"sdp": session["sdp"],
				"sdp_type": session.get("sdp_type", "answer"),
			},
		)


def _create_new_call(call, call_id, call_status, direction, account_name, phone_number_id):
	"""Create a new Call record from a webhook event.

	For inbound calls, route to the CRM-assigned user. If that user is
	already on a live call, reject at Meta and log a Missed record —
	never ring a busy agent. Unmatched callers fall back to broadcast.
	"""
	session = call.get("session", {})
	caller = call.get("from", "")
	callee = call.get("to", "")
	sdp = session.get("sdp", "")

	target_user = None
	if direction == CallDirection.INBOUND:
		target_user = resolve_target_user(caller, account_name)
		if target_user and is_agent_busy(target_user):
			_reject_call_as_busy(
				call=call,
				call_id=call_id,
				caller=caller,
				callee=callee,
				account_name=account_name,
				target_user=target_user,
				sdp=sdp,
				phone_number_id=phone_number_id,
			)
			return

	mapped_status = CALL_STATUS_MAP.get((call_status or "RINGING").upper(), CallStatus.RINGING)
	is_terminal_on_arrival = mapped_status in CALL_TERMINAL_STATES
	doc_payload = {
		"doctype": CALL_DOCTYPE,
		"call_id": call_id,
		"direction": direction,
		"status": mapped_status,
		"caller_number": caller,
		"callee_number": callee,
		"whatsapp_account": account_name,
		"agent": target_user or None,
		"start_time": now(),
		"sdp_offer": sdp,
		"raw_webhook": json.dumps(call),
	}
	# Forward-compatible: capture recording URL if Meta provides it
	recording = call.get("recording_url") or call.get("recording", {}).get("url")
	if recording:
		doc_payload["recording_url"] = recording
	if is_terminal_on_arrival:
		doc_payload["end_time"] = now()
		dur = _extract_duration(call)
		if dur is not None:
			doc_payload["duration_seconds"] = dur
			doc_payload["duration_display"] = _format_duration(dur)
		if doc_payload["status"] == CallStatus.COMPLETED and (dur or 0) == 0:
			doc_payload["status"] = CallStatus.MISSED
			mapped_status = CallStatus.MISSED
	doc = frappe.get_doc(doc_payload)
	doc.insert(ignore_permissions=True)
	_sync_crm_best_effort(doc.name)

	if direction == CallDirection.INBOUND and not is_terminal_on_arrival:
		inbox_events.emit(
			inbox_events.CALL_STARTED,
			{
				"call_name": doc.name,
				"call_id": call_id,
				"direction": direction,
				"agent": target_user,
			},
		)

	if is_terminal_on_arrival:
		try:
			_record_call_event_in_chat(
				call_name=doc.name,
				call_id=call_id,
				direction=direction,
				status=mapped_status,
				duration_seconds=doc_payload.get("duration_seconds"),
				remote_number=caller if direction == CallDirection.INBOUND else callee,
				wa_account_name=account_name,
			)
		except Exception:
			logger.exception("Failed to record call event in chat (new call, terminal)")
		inbox_events.emit(
			inbox_events.CALL_ENDED,
			{
				"call_name": doc.name,
				"call_id": call_id,
				"status": mapped_status,
				"direction": direction,
			},
		)

	if direction == CallDirection.INBOUND and not is_terminal_on_arrival:
		payload = {
			"call_name": doc.name,
			"call_id": call_id,
			"caller_number": caller,
			"phone_number_id": phone_number_id,
			"sdp_offer": sdp,
		}
		if target_user:
			frappe.publish_realtime("whatsapp_incoming_call", payload, user=target_user)
		else:
			frappe.publish_realtime("whatsapp_incoming_call", payload)


def _reject_call_as_busy(*, call, call_id, caller, callee, account_name, target_user, sdp, phone_number_id):
	if account_name:
		try:
			wa = frappe.get_doc("WhatsApp Account", account_name)
			_meta_call_action(wa, "reject", call_id=call_id)
		except Exception as e:
			logger.warning(f"Busy auto-reject for {target_user} on call {call_id} failed: {e}")

	try:
		doc = frappe.get_doc(
			{
				"doctype": CALL_DOCTYPE,
				"call_id": call_id,
				"direction": CallDirection.INBOUND,
				"status": CallStatus.MISSED,
				"caller_number": caller,
				"callee_number": callee,
				"whatsapp_account": account_name,
				"agent": target_user,
				"start_time": now(),
				"end_time": now(),
				"sdp_offer": sdp,
				"raw_webhook": json.dumps(call),
			}
		)
		doc.insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:
		return

	_sync_crm_best_effort(doc.name)

	frappe.publish_realtime(
		"whatsapp_call_missed_while_busy",
		{
			"call_name": doc.name,
			"call_id": call_id,
			"caller_number": caller,
			"phone_number_id": phone_number_id,
		},
		user=target_user,
	)

	try:
		_record_call_event_in_chat(
			call_name=doc.name,
			call_id=call_id,
			direction=CallDirection.INBOUND,
			status=CallStatus.MISSED,
			duration_seconds=0,
			remote_number=caller,
			wa_account_name=account_name,
			note="agent busy on another call",
		)
	except Exception:
		logger.exception("Failed to record busy-rejection call card")

	logger.info(
		f"Inbound call {call_id} from {caller} auto-rejected — agent {target_user} is on another call."
	)


def _extract_duration(call):
	if call.get("duration") is not None:
		return int(call["duration"])
	if call.get("start_time") and call.get("end_time"):
		return max(0, int(call["end_time"]) - int(call["start_time"]))
	return None


def _handle_missed_call(call, direction, account_name):
	remote = _get_remote_number(call, direction)
	perm = find_permission_by_number(remote, account_name)
	if not perm:
		return
	new_count = (perm.consecutive_missed_calls or 0) + 1
	updates = {"consecutive_missed_calls": new_count}
	if new_count >= CALL_PERMISSION_AUTO_REVOKE_THRESHOLD:
		updates["status"] = PermissionStatus.REVOKED
		logger.info(f"Auto-revoking call permission for {remote} after {new_count} missed calls")
	frappe.db.set_value(PERMISSION_DOCTYPE, perm.name, updates)


def _handle_completed_call(call, direction, account_name):
	remote = _get_remote_number(call, direction)
	perm = find_permission_by_number(remote, account_name)
	if perm and perm.consecutive_missed_calls:
		frappe.db.set_value(PERMISSION_DOCTYPE, perm.name, "consecutive_missed_calls", 0)


def process_permission_event(msg: dict) -> None:
	"""Process a call_permission_reply webhook — update permission record."""
	reply = msg.get("interactive", {}).get("call_permission_reply", {})
	status_str = reply.get("response", "") or reply.get("status", "")
	from_number = msg.get("from", "")
	phone_number_id = msg.get("_phone_number_id", "")
	context_msg_id = msg.get("context", {}).get("id", "")

	if not from_number or not phone_number_id:
		return

	wa_account = _account_repo().get_whatsapp_account(phone_number_id)
	if not wa_account:
		return

	perm_status = (
		PermissionStatus.GRANTED
		if status_str.lower() in ("accept", "granted", "allow")
		else PermissionStatus.DECLINED
	)

	existing = None
	if context_msg_id:
		existing = frappe.db.get_value(
			PERMISSION_DOCTYPE,
			{"last_request_message_id": context_msg_id},
			"name",
		)
	if not existing:
		existing = frappe.db.get_value(
			PERMISSION_DOCTYPE,
			{"user_wa_id": from_number, "whatsapp_account": wa_account.name},
			"name",
		)

	updates = {"status": perm_status}
	if perm_status == PermissionStatus.GRANTED:
		updates["granted_at"] = now()
		is_permanent = bool(reply.get("is_permanent"))
		updates["is_permanent"] = 1 if is_permanent else 0
		exp_ts = reply.get("expiration_timestamp")
		if not is_permanent and exp_ts:
			try:
				from msuite_inbox.inbox.services.normalizer import parse_unix_timestamp

				updates["expires_at"] = parse_unix_timestamp(exp_ts)
			except (TypeError, ValueError, OSError):
				pass
		else:
			updates["expires_at"] = None
	elif perm_status == PermissionStatus.DECLINED:
		updates["granted_at"] = None
		updates["expires_at"] = None
		updates["is_permanent"] = 0

	if existing:
		frappe.db.set_value(PERMISSION_DOCTYPE, existing, updates)
	else:
		frappe.get_doc(
			{
				"doctype": PERMISSION_DOCTYPE,
				"user_wa_id": from_number,
				"whatsapp_account": wa_account.name,
				**updates,
			}
		).insert(ignore_permissions=True)

	# Update Channel Message in the conversation thread to reflect the granted/declined state
	import json
	clean_from = from_number.lstrip("+").strip()
	msg_name = None
	if context_msg_id:
		msg_name = frappe.db.get_value("Channel Message", {"platform_message_id": context_msg_id}, "name")
	
	if not msg_name:
		if is_bsuid(clean_from):
			candidates = frappe.db.sql(
				"""
				SELECT m.name FROM `tabChannel Message` m
				JOIN `tabChannel Handle` h ON m.channel_handle = h.name
				WHERE (h.platform_handle = %s OR h.bsuid = %s) AND m.platform_payload LIKE '%%call_permission%%'
				ORDER BY m.creation DESC LIMIT 1
				""",
				(clean_from, clean_from),
				as_dict=True,
			)
		elif len(clean_from) >= 10:
			candidates = frappe.db.sql(
				"""
				SELECT m.name FROM `tabChannel Message` m
				JOIN `tabChannel Handle` h ON m.channel_handle = h.name
				WHERE h.platform_handle LIKE %s AND INSTR(h.platform_handle, '.') = 0 AND m.platform_payload LIKE '%%call_permission%%'
				ORDER BY m.creation DESC LIMIT 1
				""",
				(f"%{clean_from[-10:]}",),
				as_dict=True,
			)
		else:
			candidates = []
		if candidates:
			msg_name = candidates[0].name

	if msg_name:
		msg_doc = frappe.get_doc("Channel Message", msg_name)
		raw = {}
		if msg_doc.platform_payload:
			try:
				raw = json.loads(msg_doc.platform_payload) if isinstance(msg_doc.platform_payload, str) else dict(msg_doc.platform_payload)
			except Exception:
				raw = {}
		raw["permission_status"] = perm_status.lower()
		msg_doc.platform_payload = json.dumps(raw)
		if perm_status == PermissionStatus.GRANTED:
			msg_doc.text_content = "Call permission granted by customer. You can now place voice calls."
		else:
			msg_doc.text_content = "Call permission request declined by customer."
		msg_doc.status = "read"
		msg_doc.save(ignore_permissions=True)

		frappe.publish_realtime(
			"msuite_inbox:new_message",
			{
				"conversation": msg_doc.conversation,
				"name": msg_doc.name,
				"direction": msg_doc.direction,
			},
		)

	frappe.publish_realtime(
		"whatsapp_call_permission_update",
		{
			"user_wa_id": from_number,
			"status": perm_status,
			"whatsapp_account": wa_account.name,
		},
	)


def _get_remote_number(call, direction):
	return call.get("to", "") if direction == CallDirection.OUTBOUND else call.get("from", "")


def _format_duration(seconds):
	return f"{seconds // 60:02d}:{seconds % 60:02d}"


def find_permission_by_number(phone_number, wa_account_name):
	"""Find a WhatsApp Call Permission by matching the last 10 digits or exact BSUID."""
	if not phone_number or not wa_account_name:
		return None
	clean = str(phone_number).strip().lstrip("+")
	if is_bsuid(clean):
		permissions = frappe.get_all(
			PERMISSION_DOCTYPE,
			filters={"whatsapp_account": wa_account_name, "user_wa_id": clean},
			fields=[
				"name",
				"user_wa_id",
				"status",
				"consecutive_missed_calls",
				"last_request_sent_at",
				"can_request_again_at",
				"granted_at",
				"expires_at",
				"is_permanent",
			],
		)
		return permissions[0] if permissions else None

	clean = _format_number(phone_number)
	if len(clean) < 10:
		return None
	last10 = clean[-10:]
	permissions = frappe.get_all(
		PERMISSION_DOCTYPE,
		filters={"whatsapp_account": wa_account_name},
		fields=[
			"name",
			"user_wa_id",
			"status",
			"consecutive_missed_calls",
			"last_request_sent_at",
			"can_request_again_at",
			"granted_at",
			"expires_at",
			"is_permanent",
		],
	)
	for p in permissions:
		if is_bsuid(p.user_wa_id or ""):
			continue
		if _format_number(p.user_wa_id or "")[-10:] == last10:
			return p
	return None


# ═══════════════════════════════════════════════════════════════════════
# Active call management — agent-initiated state transitions
# ═══════════════════════════════════════════════════════════════════════


def get_call_record(call_name, fields=None):
	fields = fields or ["call_id", "status", "whatsapp_account"]
	result = frappe.db.get_value(CALL_DOCTYPE, call_name, fields, as_dict=True)
	if not result or not result.get("call_id"):
		frappe.throw(_("Call record not found"))
	return result


def answer_call(call_name, sdp="", sdp_type="answer"):
	call = get_call_record(call_name, ["call_id", "status", "whatsapp_account", "caller_number"])
	if call.status != CallStatus.RINGING:
		frappe.throw(_("Call is not ringing"))

	frappe.db.set_value(
		CALL_DOCTYPE,
		call_name,
		{
			"agent": frappe.session.user,
			"status": CallStatus.CONNECTED,
			"sdp_answer": sdp,
		},
	)
	_sync_crm_best_effort(call_name)

	wa = frappe.get_doc("WhatsApp Account", call.whatsapp_account)
	result = _meta_call_action(
		wa, "pre_accept", call_id=call.call_id, sdp=sdp, sdp_type=sdp_type, to=call.caller_number
	)
	frappe.db.commit()
	return result


def accept_call(call_name):
	call = get_call_record(call_name, ["call_id", "whatsapp_account", "sdp_answer", "caller_number"])
	wa = frappe.get_doc("WhatsApp Account", call.whatsapp_account)
	try:
		return _meta_call_action(
			wa, "accept", call_id=call.call_id, sdp=call.sdp_answer, sdp_type="answer", to=call.caller_number
		)
	except Exception as e:
		logger.warning(f"accept_call failed (non-fatal): {e}")
		return {"status": "ok", "note": "accept failed but call is connected via WebRTC"}


def reject_call(call_name):
	call = get_call_record(call_name, ["call_id", "status", "whatsapp_account"])
	if call.status in CALL_TERMINAL_STATES:
		return {"status": "already_ended"}

	frappe.db.set_value(
		CALL_DOCTYPE,
		call_name,
		{
			"status": CallStatus.REJECTED,
			"end_time": now(),
			"agent": frappe.session.user,
		},
	)
	_sync_crm_best_effort(call_name)

	wa = frappe.get_doc("WhatsApp Account", call.whatsapp_account)
	try:
		result = _meta_call_action(wa, "reject", call_id=call.call_id)
	except Exception:
		result = {}

	frappe.db.commit()
	inbox_events.emit(inbox_events.CALL_ENDED, {"call_name": call_name, "status": CallStatus.REJECTED})
	return result


def terminate_call(call_name):
	call = get_call_record(
		call_name,
		["name", "call_id", "status", "whatsapp_account", "start_time", "direction", "callee_number", "caller_number"],
	)
	if call.status in CALL_TERMINAL_STATES:
		return {"status": "already_ended"}

	end = now()
	was_connected = call.status == CallStatus.CONNECTED
	dur = 0
	if call.start_time and was_connected:
		dur = max(0, int((get_datetime(end) - get_datetime(call.start_time)).total_seconds()))

	# If call was never connected or hung up while Ringing (dur == 0), mark as MISSED
	if not was_connected or dur == 0:
		mapped_status = CallStatus.MISSED
	else:
		mapped_status = CallStatus.COMPLETED

	updates = {
		"status": mapped_status,
		"end_time": end,
		"duration_seconds": dur,
		"duration_display": _format_duration(dur),
	}

	frappe.db.set_value(CALL_DOCTYPE, call_name, updates)
	_sync_crm_best_effort(call_name)

	wa = frappe.get_doc("WhatsApp Account", call.whatsapp_account)
	try:
		result = _meta_call_action(wa, "terminate", call_id=call.call_id)
	except Exception:
		result = {}

	# Record call card into conversation thread
	remote_num = call.callee_number if call.direction == CallDirection.OUTBOUND else call.caller_number
	try:
		_record_call_event_in_chat(
			call_name=call_name,
			call_id=call.call_id or f"outbound-{call_name}",
			direction=call.direction,
			status=mapped_status,
			duration_seconds=dur,
			remote_number=remote_num,
			wa_account_name=call.whatsapp_account,
		)
	except Exception:
		logger.exception("Failed to record call event in chat on terminate_call")

	frappe.db.commit()
	inbox_events.emit(
		inbox_events.CALL_ENDED,
		{
			"call_name": call_name,
			"call_id": call.call_id,
			"status": mapped_status,
			"direction": call.direction,
		},
	)
	return result


def resolve_wa_account(whatsapp_account="", to_number=None, required=True):
	"""The WhatsApp Account to use. With required=False, None instead of an error
	when the site has no outgoing account (read-only callers, e.g. the badge)."""
	if whatsapp_account:
		return frappe.get_doc("WhatsApp Account", whatsapp_account)
	if to_number:
		from msuite_inbox.inbox.constants import ChannelType

		clean_num = to_number.lstrip("+").strip()
		if is_bsuid(clean_num):
			handle_name = frappe.db.get_value(
				"Channel Handle", {"channel_type": ChannelType.WHATSAPP, "bsuid": clean_num}, "name"
			) or frappe.db.get_value(
				"Channel Handle", {"channel_type": ChannelType.WHATSAPP, "platform_handle": clean_num}, "name"
			)
		else:
			handle_name = frappe.db.get_value(
				"Channel Handle", {"channel_type": ChannelType.WHATSAPP, "platform_handle": clean_num}, "name"
			)
		if handle_name:
			# Try to resolve from the most recent INBOUND message first (where the 24h window is open)
			wa_name = frappe.db.get_value(
				"Channel Message",
				{"channel_handle": handle_name, "direction": "Inbound", "whatsapp_account": ("!=", "")},
				"whatsapp_account",
				order_by="creation desc",
			)
			if not wa_name:
				# Fall back to any message direction
				wa_name = frappe.db.get_value(
					"Channel Message",
					{"channel_handle": handle_name, "whatsapp_account": ("!=", "")},
					"whatsapp_account",
					order_by="creation desc",
				)
			if wa_name:
				return frappe.get_doc("WhatsApp Account", wa_name)
	wa = _account_repo().get_whatsapp_account(account_type="outgoing")
	if not wa and required:
		frappe.throw(_("No default outgoing WhatsApp account configured"))
	return wa


def initiate_outbound_call(whatsapp_account="", to_number="", sdp=None, sdp_type=None):
	wa = resolve_wa_account(whatsapp_account, to_number)
	phone_number_id = _account_repo().get_phone_number_id(wa, "outgoing")
	if not phone_number_id:
		frappe.throw(_("WhatsApp Account has no phone number configured"))

	result = _meta_call_action(wa, "connect", sdp=sdp, sdp_type="offer", to=to_number)
	meta_call_id = _extract_call_id_from_response(result)

	existing = frappe.db.get_value(CALL_DOCTYPE, {"call_id": meta_call_id}, "name")
	if existing:
		frappe.db.set_value(CALL_DOCTYPE, existing, {"agent": frappe.session.user})
		_sync_crm_best_effort(existing)
		frappe.db.commit()
		return {"success": True, "call_name": existing, "call_id": meta_call_id}

	doc = frappe.get_doc(
		{
			"doctype": CALL_DOCTYPE,
			"call_id": meta_call_id,
			"direction": CallDirection.OUTBOUND,
			"status": CallStatus.RINGING,
			"callee_number": to_number,
			"whatsapp_account": wa.name,
			"agent": frappe.session.user,
			"start_time": now(),
		}
	)
	doc.insert(ignore_permissions=True)
	_sync_crm_best_effort(doc.name)
	frappe.db.commit()
	inbox_events.emit(
		inbox_events.CALL_STARTED,
		{
			"call_name": doc.name,
			"call_id": meta_call_id,
			"direction": CallDirection.OUTBOUND,
			"agent": frappe.session.user,
		},
	)
	return {"success": True, "call_name": doc.name, "call_id": meta_call_id}


def _extract_call_id_from_response(result):
	calls_list = result.get("calls") or []
	if calls_list and isinstance(calls_list, list) and calls_list[0].get("id"):
		return calls_list[0]["id"]
	if result.get("call_id"):
		return result["call_id"]
	fallback = f"outbound-{frappe.generate_hash(length=12)}"
	logger.warning(f"Meta did not return call_id. Using fallback: {fallback}")
	return fallback


def mark_call_connected(call_name):
	if not frappe.db.exists(CALL_DOCTYPE, call_name):
		frappe.throw(_("Call record not found"))

	current_status = frappe.db.get_value(CALL_DOCTYPE, call_name, "status")
	if current_status in CALL_TERMINAL_STATES:
		return {"status": current_status}

	if current_status != CallStatus.CONNECTED:
		frappe.db.set_value(CALL_DOCTYPE, call_name, "status", CallStatus.CONNECTED)
		_sync_crm_best_effort(call_name)
		frappe.db.commit()
		logger.info(f"mark_call_connected: {call_name} -> Connected")

	return {"status": CallStatus.CONNECTED}


def save_call_notes(call_name, notes=""):
	if not frappe.db.exists(CALL_DOCTYPE, call_name):
		frappe.throw(_("Call record not found"))
	frappe.db.set_value(CALL_DOCTYPE, call_name, "notes", notes)
	try:
		from msuite_inbox.inbox.services import crm_sync

		crm_sync.sync_call_notes_to_crm(call_name, notes)
	except Exception:
		logger.exception("CRM note sync failed for %s", call_name)
	frappe.db.commit()
	return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════════
# Call permissions
# ═══════════════════════════════════════════════════════════════════════


def request_call_permission(to_number="", whatsapp_account=None, method="interactive", template_name=None):
	import requests

	wa = resolve_wa_account(whatsapp_account, to_number)
	phone_number_id = _account_repo().get_phone_number_id(wa, "outgoing")
	token = wa.get_password("token")

	if not token:
		frappe.throw(_("No token configured on WhatsApp Account"))

	existing = frappe.db.get_value(
		PERMISSION_DOCTYPE,
		{"user_wa_id": to_number, "whatsapp_account": wa.name},
		["name", "status", "last_request_sent_at"],
		as_dict=True,
	)

	if existing and existing.last_request_sent_at:
		hours_since = (
			get_datetime(now()) - get_datetime(existing.last_request_sent_at)
		).total_seconds() / 3600
		if hours_since < CALL_PERMISSION_COOLDOWN_HOURS:
			time_display = f"{max(1, int(hours_since * 60))}m" if hours_since < 1 else f"{int(hours_since)}h"
			frappe.throw(
				_("Cannot send another request within 24 hours. Last sent {0} ago.").format(time_display)
			)

	payload = _build_permission_payload(method, to_number, template_name)
	resp = requests.post(
		f"{GRAPH_API_BASE}/{phone_number_id}/messages",
		json=payload,
		headers={"Authorization": f"Bearer {token}"},
		timeout=REQUEST_TIMEOUT,
	)

	result = resp.json()
	if not resp.ok:
		error_code = result.get("error", {}).get("code", 0)
		error_msg = result.get("error", {}).get("message", "Unknown error")
		if error_code == 138017:
			perm_status = PermissionStatus.GRANTED
		else:
			friendly = _friendly_call_error(error_code, error_msg)
			try:
				_record_permission_message(
					wa.name,
					to_number,
					message_id=None,
					method=method,
					template_name=template_name,
					failure_reason=friendly,
				)
				frappe.db.commit()
			except Exception:
				frappe.log_error(
					"Failed to record failed call-permission attempt", "WhatsApp Call Permission"
				)
			frappe.throw(_("Failed to send permission request: {0}").format(friendly))
	else:
		perm_status = PermissionStatus.PENDING

	message_id = (result.get("messages") or [{}])[0].get("id") if result.get("messages") else None
	_record_permission_message(wa.name, to_number, message_id, method, template_name)

	updates = {"status": perm_status, "last_request_sent_at": now()}
	if message_id:
		updates["last_request_message_id"] = message_id
	if perm_status == PermissionStatus.GRANTED:
		updates["granted_at"] = now()

	if existing:
		# `frappe.db.set_value` bypasses the doctype's `before_save()`
		# hook (which recomputes `can_request_again_at` from
		# `last_request_sent_at`) — without setting it explicitly here,
		# the retry-cooldown badge goes stale after the first re-request:
		# it keeps showing the *original* request's expiry instead of
		# advancing another 24h, so the UI tells the agent they can
		# retry immediately when the server will still reject it.
		from frappe.utils import add_to_date

		updates["can_request_again_at"] = add_to_date(now(), hours=CALL_PERMISSION_COOLDOWN_HOURS)
		frappe.db.set_value(PERMISSION_DOCTYPE, existing.name, updates)
	else:
		frappe.get_doc(
			{
				"doctype": PERMISSION_DOCTYPE,
				"user_wa_id": to_number,
				"whatsapp_account": wa.name,
				**updates,
			}
		).insert(ignore_permissions=True)

	frappe.db.commit()

	if perm_status == PermissionStatus.GRANTED:
		return {"success": True, "already_granted": True, "message": "Permission already granted."}
	return {"success": True, "meta_response": result}


def _friendly_call_error(code, raw_message):
	"""Translate known Meta error codes into an actionable message —
	the raw Graph API text ("(#100) violated JSON schema...") tells an
	agent nothing about what to actually do."""
	if code == 138000:
		return (
			"Calling is not enabled for this phone number yet. Enable it "
			"in Meta's WhatsApp Manager (Phone numbers → this number → "
			"Calling), or via Settings → WhatsApp → Calling in this app, "
			"then try again."
		)
	if code == 132001:
		return (
			"That template isn't approved in the selected language. Pick "
			"a different template, or re-sync templates from Meta and try "
			"again."
		)
	return raw_message


def _build_permission_payload(method, to_number, template_name=None):
	if method == "interactive":
		# Meta renders the Allow/Deny UI itself for `call_permission_request`
		# — the action is just `{"name": "call_permission_request"}`, no
		# `buttons` array. The previous `buttons: [{"type": "voice_call", ...}]`
		# shape was never valid: Meta's schema only allows button types
		# cta_url/quick_reply/reply/single_select, and rejected `voice_call`
		# plus the extra `title`/`phone_number_id` keys with a 400 (#100).
		payload = {
			"messaging_product": "whatsapp",
			"type": "interactive",
			"interactive": {
				"type": "call_permission_request",
				"body": {"text": "Can we call you on WhatsApp?"},
				"action": {"name": "call_permission_request"},
			},
		}
		if is_bsuid(to_number):
			payload["recipient_type"] = "individual"
			payload["recipient"] = to_number
		else:
			payload["to"] = to_number
		return payload
	elif method == "template":
		if not template_name:
			frappe.throw(_("Template name is required for template-based permission requests"))
		# `template_name` here is actually the WhatsApp Templates doc's
		# unique `name` (`{template_name}-{language_code}`, see its
		# autoname) — NOT the bare template_name. A template can be
		# approved in more than one language under the same
		# template_name; looking it up by `{"template_name": ...}` alone
		# picked an arbitrary row with no language guarantee, which could
		# silently send the wrong language variant and get rejected by
		# Meta with "(#132001) Template name does not exist in the
		# translation". Fetching by the exact doc name removes the
		# ambiguity — the caller (get_call_permission_templates /
		# CallPermissionDialog.vue) already surfaces `name`, not just
		# `template_name`.
		tpl = frappe.db.get_value(
			"WhatsApp Templates",
			template_name,
			["template_name", "language_code"],
			as_dict=True,
		)
		if not tpl:
			frappe.throw(_("Selected template not found: {0}").format(template_name))
		tpl_name = tpl.get("template_name") if isinstance(tpl, dict) else getattr(tpl, "template_name", "")
		tpl_lang = (tpl.get("language_code") if isinstance(tpl, dict) else getattr(tpl, "language_code", None)) or "en_US"
		payload = {
			"messaging_product": "whatsapp",
			"type": "template",
			"template": {
				"name": tpl_name,
				"language": {"code": tpl_lang},
				"components": [],
			},
		}
		if is_bsuid(to_number):
			payload["recipient_type"] = "individual"
			payload["recipient"] = to_number
		else:
			payload["to"] = to_number
		return payload
	else:
		frappe.throw(_("Invalid method: {0}").format(method))


def _record_call_event_in_chat(
	*, call_name, call_id, direction, status, duration_seconds, remote_number, wa_account_name, note=""
):
	"""Write a `Channel Message` of content_type=Call into the conversation
	thread — this lives in Inbox naturally since it talks the dispatcher's
	own NormalizedEvent language directly, no cross-module reach-through."""
	if not (call_id and remote_number and wa_account_name):
		return

	from msuite_inbox.inbox.constants import ChannelType, MessageContentType, SenderType
	from msuite_inbox.inbox.constants import Direction as MsgDirection
	from msuite_inbox.inbox.services.dispatcher import handle as dispatch
	from msuite_inbox.inbox.services.normalizer import NormalizedEvent
	from msuite_inbox.inbox.services.outbound import inbox_for_account

	inbox_name = inbox_for_account(ChannelType.WHATSAPP, wa_account_name)
	if not inbox_name:
		inbox_name = frappe.db.get_value("Inbox", {"channel_type": ChannelType.WHATSAPP}, "name")
	if not inbox_name:
		return

	msg_direction = MsgDirection.INBOUND if direction == CallDirection.INBOUND else MsgDirection.OUTBOUND
	text = _format_call_card_text(direction, status, duration_seconds, note)
	platform_message_id = f"call:{call_id}:{status}:{frappe.generate_hash(length=6)}"

	try:
		dispatch(
			NormalizedEvent(
				channel_type=ChannelType.WHATSAPP,
				inbox=inbox_name,
				platform_handle=(remote_number or "").lstrip("+").strip(),
				direction=msg_direction,
				content_type=MessageContentType.CALL,
				text_content=text,
				platform_message_id=platform_message_id,
				sender_type=SenderType.SYSTEM,
				whatsapp_account=wa_account_name,
				reference_doctype=CALL_DOCTYPE,
				reference_name=call_name,
				raw_payload={
					"call_id": call_id,
					"status": status,
					"duration_seconds": duration_seconds or 0,
					"direction": direction,
				},
			)
		)
	except Exception:
		logger.exception("dispatcher failed to write call card for %s", call_name)


def _format_call_card_text(direction, status, duration_seconds, note):
	is_inbound = direction == CallDirection.INBOUND
	dir_label = "Incoming" if is_inbound else "Outgoing"

	if status == CallStatus.COMPLETED:
		dur = duration_seconds or 0
		return f"{dir_label} call · {_format_duration(dur)}"
	if status == CallStatus.MISSED:
		return "Missed call" if is_inbound else "Outgoing call · not answered"
	if status == CallStatus.REJECTED:
		base = "Call declined" if is_inbound else "Outgoing call · declined"
		return f"{base} · {note}" if note else base
	if status == CallStatus.FAILED:
		base = f"{dir_label} call · failed"
		return f"{base} · {note}" if note else base
	return f"{dir_label} call · {status}"


def _record_permission_message(
	wa_account_name, to_number, message_id, method, template_name, *, perm_status="pending", failure_reason=None
):
	if not message_id and not failure_reason:
		return

	from msuite_inbox.inbox.constants import (
		ChannelType,
		Direction,
		MessageContentType,
		MessageStatus,
		SenderType,
	)
	from msuite_inbox.inbox.services.dispatcher import handle as dispatch
	from msuite_inbox.inbox.services.normalizer import NormalizedEvent
	from msuite_inbox.inbox.services.outbound import inbox_for_account

	inbox_name = inbox_for_account(ChannelType.WHATSAPP, wa_account_name)
	if not inbox_name:
		inbox_name = frappe.db.get_value("Inbox", {"channel_type": ChannelType.WHATSAPP}, "name")
	if not inbox_name:
		return

	display_template_name = template_name or "CALL_PERMISSION_REQUEST"
	clean_num = (to_number or "").lstrip("+").strip()
	status_str = (perm_status or "pending").lower()

	if failure_reason:
		text = f"Call permission request failed: {failure_reason}"
		status_str = "failed"
	elif status_str == "granted":
		text = "Call permission granted by customer. You can now place voice calls."
	elif status_str == "declined":
		text = "Call permission request declined by customer."
	else:
		text = "Call permission request sent to contact via WhatsApp. Awaiting customer consent."

	try:
		raw_pl = {
			"purpose": "call_permission",
			"permission_status": status_str,
			"method": method,
			"template_name": display_template_name,
			"requested_at": frappe.utils.now(),
		}
		if is_bsuid(clean_num):
			raw_pl["bsuid"] = clean_num
		else:
			raw_pl["phone"] = clean_num

		result = dispatch(
			NormalizedEvent(
				channel_type=ChannelType.WHATSAPP,
				inbox=inbox_name,
				platform_handle=clean_num,
				direction=Direction.OUTBOUND,
				content_type=MessageContentType.TEMPLATE,
				text_content=text,
				platform_message_id=message_id or "",
				sender_type=SenderType.SYSTEM,
				template_name=display_template_name,
				whatsapp_account=wa_account_name,
				bsuid=clean_num if is_bsuid(clean_num) else "",
				raw_payload=raw_pl,
			)
		)
		if failure_reason and result.get("message"):
			frappe.db.set_value(
				"Channel Message",
				result["message"],
				{
					"status": MessageStatus.FAILED,
					"status_error": failure_reason[:1000],
				},
				update_modified=False,
			)
	except Exception:
		frappe.log_error("Failed to record call-permission message", "WhatsApp Call Permission")


def check_can_call(to_number="", whatsapp_account=None):
	if not to_number:
		return {"can_call": False, "reason": "No phone number provided", "in_24h_window": False}

	wa = resolve_wa_account(whatsapp_account, to_number)
	if not wa:
		return {"can_call": False, "reason": "No WhatsApp account configured", "in_24h_window": False}

	# Check if the 24h messaging window is open for this specific WABA
	in_24h_window = False
	clean_num = to_number.lstrip("+").strip()
	if is_bsuid(clean_num):
		handle_name = frappe.db.get_value(
			"Channel Handle", {"channel_type": "WhatsApp", "bsuid": clean_num}, "name"
		) or frappe.db.get_value(
			"Channel Handle", {"channel_type": "WhatsApp", "platform_handle": clean_num}, "name"
		)
	else:
		handle_name = frappe.db.get_value(
			"Channel Handle", {"channel_type": "WhatsApp", "platform_handle": clean_num}, "name"
		)
	if handle_name:
		last_inbound = frappe.db.get_value(
			"Channel Message",
			{"channel_handle": handle_name, "direction": "Inbound", "whatsapp_account": wa.name},
			"creation",
			order_by="creation desc",
		)
		if last_inbound:
			delta = frappe.utils.now_datetime() - frappe.utils.get_datetime(last_inbound)
			in_24h_window = delta.total_seconds() < 24 * 60 * 60

	try:
		from msuite_core.services.plans.plan_enforcer import (
			check_feature_or_throw,
			get_current_usage,
			get_feature_limit,
		)

		check_feature_or_throw("calling", "Voice Calling")

		limit = get_feature_limit("calling")
		if limit is not None and limit > 0:
			current = get_current_usage(CALL_DOCTYPE, "month", {"direction": CallDirection.OUTBOUND})
			if current >= int(limit):
				frappe.local.message_log = []
				return {
					"can_call": False,
					"reason": f"Monthly call limit reached ({current}/{int(limit)})",
					"in_24h_window": in_24h_window,
				}
	except Exception as e:
		frappe.local.message_log = []
		return {"can_call": False, "reason": str(e), "in_24h_window": in_24h_window}

	perm = find_permission_by_number(to_number, wa.name)

	if not perm:
		return {
			"can_call": False,
			"reason": "No call permission exists",
			"permission_status": None,
			"can_request_permission": True,
			"in_24h_window": in_24h_window,
		}

	if perm.status != PermissionStatus.GRANTED:
		return {
			"can_call": False,
			"reason": f"Permission status: {perm.status}",
			"permission_status": perm.status,
			"can_request_permission": True,
			"in_24h_window": in_24h_window,
		}

	if (perm.consecutive_missed_calls or 0) >= CALL_PERMISSION_AUTO_REVOKE_THRESHOLD:
		return {
			"can_call": False,
			"reason": "Auto-revoked (consecutive missed calls)",
			"permission_status": PermissionStatus.REVOKED,
			"in_24h_window": in_24h_window,
		}

	if not getattr(perm, "is_permanent", 0):
		expires_dt = None
		if getattr(perm, "expires_at", None):
			expires_dt = get_datetime(perm.expires_at)
		elif perm.granted_at:
			expires_dt = get_datetime(perm.granted_at) + timedelta(seconds=7 * 24 * 3600)
		if expires_dt and get_datetime(now()) > expires_dt:
			return {
				"can_call": False,
				"reason": "Call permission expired. Send a new request.",
				"permission_status": "Expired",
				"can_request_permission": True,
				"in_24h_window": in_24h_window,
			}

	return {
		"can_call": True,
		"reason": "",
		"permission_status": PermissionStatus.GRANTED,
		"consecutive_missed_calls": perm.consecutive_missed_calls or 0,
		"in_24h_window": in_24h_window,
	}


def grant_call_permission(to_number="", whatsapp_account=None):
	"""Manually grant call permission for a phone number (e.g. after customer consents via text/chat or agent override)."""
	if not to_number:
		frappe.throw(_("Phone number is required"))
	wa = resolve_wa_account(whatsapp_account, to_number)
	if not wa:
		frappe.throw(_("No WhatsApp account found for this number"))

	existing = find_permission_by_number(to_number, wa.name)
	now_dt = now()
	updates = {
		"status": PermissionStatus.GRANTED,
		"granted_at": now_dt,
		"is_permanent": 1,
		"consecutive_missed_calls": 0,
		"expires_at": None,
	}
	if existing:
		frappe.db.set_value(PERMISSION_DOCTYPE, existing.name, updates)
	else:
		frappe.get_doc(
			{
				"doctype": PERMISSION_DOCTYPE,
				"user_wa_id": to_number,
				"whatsapp_account": wa.name,
				**updates,
			}
		).insert(ignore_permissions=True)
	frappe.db.commit()

	# Update Channel Message in conversation thread
	import json
	clean_num = to_number.lstrip("+").strip()
	if is_bsuid(clean_num):
		candidates = frappe.db.sql(
			"""
			SELECT m.name, m.platform_payload FROM `tabChannel Message` m
			JOIN `tabChannel Handle` h ON m.channel_handle = h.name
			WHERE (h.platform_handle = %s OR h.bsuid = %s) AND m.platform_payload LIKE '%%call_permission%%'
			ORDER BY m.creation DESC LIMIT 1
			""",
			(clean_num, clean_num),
			as_dict=True,
		)
	elif len(clean_num) >= 10:
		candidates = frappe.db.sql(
			"""
			SELECT m.name, m.platform_payload FROM `tabChannel Message` m
			JOIN `tabChannel Handle` h ON m.channel_handle = h.name
			WHERE h.platform_handle LIKE %s AND INSTR(h.platform_handle, '.') = 0 AND m.platform_payload LIKE '%%call_permission%%'
			ORDER BY m.creation DESC LIMIT 1
			""",
			(f"%{clean_num[-10:]}",),
			as_dict=True,
		)
	else:
		candidates = []
	if candidates:
		msg_doc = frappe.get_doc("Channel Message", candidates[0].name)
		raw = {}
		if msg_doc.platform_payload:
			try:
				raw = json.loads(msg_doc.platform_payload) if isinstance(msg_doc.platform_payload, str) else dict(msg_doc.platform_payload)
			except Exception:
				raw = {}
		raw["permission_status"] = "granted"
		msg_doc.platform_payload = json.dumps(raw)
		msg_doc.text_content = "Call permission granted. You can now place voice calls."
		msg_doc.save(ignore_permissions=True)
		frappe.publish_realtime(
			"msuite_inbox:new_message",
			{
				"conversation": msg_doc.conversation,
				"name": msg_doc.name,
				"direction": msg_doc.direction,
			},
		)

	# Emit realtime update so UI badge immediately flips to Granted
	frappe.publish_realtime(
		"whatsapp_call_permission_update",
		{"user_wa_id": to_number, "whatsapp_account": wa.name, "status": PermissionStatus.GRANTED},
	)

	return {"success": True, "message": _("Call permission granted successfully.")}


def get_call_permission_state(to_number="", whatsapp_account=None):
	"""Rich call-permission state for the conversation-header badge."""
	if not to_number:
		return _empty_permission_state("No phone number")

	# Every Lead/Deal page shows this badge: no account is a state, not an error.
	wa = resolve_wa_account(whatsapp_account, to_number, required=False)
	if not wa:
		return {**_empty_permission_state("No WhatsApp account is connected."), "can_request_permission": False}

	perm = find_permission_by_number(to_number, wa.name)
	if not perm:
		return _empty_permission_state("No request sent yet")

	now_dt = get_datetime(now())
	seconds_until_can_request = _seconds_until(now_dt, perm.can_request_again_at)
	misses = int(perm.consecutive_missed_calls or 0)
	misses_to_revoke = max(0, CALL_PERMISSION_AUTO_REVOKE_THRESHOLD - misses)

	state = {
		"status": perm.status,
		"tone": "neutral",
		"label": "",
		"detail": "",
		"can_call": False,
		"can_request_permission": seconds_until_can_request == 0,
		"timings": {
			"last_request_at": _iso(perm.last_request_sent_at),
			"granted_at": _iso(perm.granted_at),
			"expires_at": None,
			"can_request_again_at": _iso(perm.can_request_again_at),
			"seconds_left_in_window": None,
			"seconds_until_can_request": seconds_until_can_request,
		},
		"counters": {"consecutive_missed_calls": misses, "misses_to_revoke": misses_to_revoke},
	}

	if perm.status == PermissionStatus.PENDING:
		state["tone"] = "warning"
		state["label"] = "Awaiting call permission"
		if perm.last_request_sent_at:
			ago = _humanize_seconds(int((now_dt - get_datetime(perm.last_request_sent_at)).total_seconds()))
			state["detail"] = (
				f"Sent {ago} ago. Re-request available {_humanize_eta(seconds_until_can_request)}."
			)
		else:
			state["detail"] = "Waiting for the contact to tap Allow on WhatsApp."

	elif perm.status == PermissionStatus.GRANTED:
		is_permanent = bool(getattr(perm, "is_permanent", 0))
		stored_expires_at = getattr(perm, "expires_at", None)

		if is_permanent:
			state["tone"] = "success"
			state["label"] = "Can call · permanent"
			state["timings"]["expires_at"] = None
			state["timings"]["seconds_left_in_window"] = None
			bits = ["Granted permanently. No expiry."]
			if misses > 0:
				bits.append(f"{misses} missed; {misses_to_revoke} more would auto-revoke.")
			state["detail"] = " ".join(bits)
			state["can_call"] = misses < CALL_PERMISSION_AUTO_REVOKE_THRESHOLD
			if not state["can_call"]:
				state["status"] = PermissionStatus.REVOKED
				state["tone"] = "danger"
				state["label"] = "Call permission auto-revoked"
				state["detail"] = f"Revoked after {misses} consecutive missed calls."
			return state

		if stored_expires_at:
			expires_dt = get_datetime(stored_expires_at)
		elif perm.granted_at:
			expires_dt = get_datetime(perm.granted_at) + timedelta(seconds=_PERMISSION_WINDOW_SECONDS)
		else:
			state["tone"] = "success"
			state["label"] = "Can call"
			state["detail"] = "Granted (expiry unknown — Meta did not supply a timestamp)."
			state["can_call"] = True
			return state

		secs_left = max(0, int((expires_dt - now_dt).total_seconds()))
		state["timings"]["expires_at"] = expires_dt.isoformat()
		state["timings"]["seconds_left_in_window"] = secs_left

		if secs_left <= 0:
			state["status"] = "Expired"
			state["tone"] = "warning"
			state["label"] = "Call permission expired"
			state["detail"] = "The consent window has lapsed. Send a new request to call again."
			state["can_call"] = False
			state["can_request_permission"] = seconds_until_can_request == 0
		elif misses >= CALL_PERMISSION_AUTO_REVOKE_THRESHOLD:
			state["status"] = PermissionStatus.REVOKED
			state["tone"] = "danger"
			state["label"] = "Call permission auto-revoked"
			state["detail"] = f"Revoked after {misses} consecutive missed calls."
		else:
			state["tone"] = "success"
			state["label"] = f"Can call · {_humanize_seconds(secs_left)} left"
			bits = [f"Granted. Window closes in {_humanize_seconds(secs_left)}."]
			if misses > 0:
				bits.append(f"{misses} missed; {misses_to_revoke} more would auto-revoke.")
			state["detail"] = " ".join(bits)
			state["can_call"] = True

	elif perm.status == PermissionStatus.DECLINED:
		state["tone"] = "danger"
		state["label"] = "Call request declined"
		if seconds_until_can_request > 0:
			state["detail"] = (
				f"Contact tapped Deny. New request available {_humanize_eta(seconds_until_can_request)}."
			)
		else:
			state["detail"] = "Contact tapped Deny. You can send a fresh request now."

	elif perm.status == PermissionStatus.REVOKED:
		state["tone"] = "danger"
		state["label"] = "Call permission revoked"
		bits = []
		if misses >= CALL_PERMISSION_AUTO_REVOKE_THRESHOLD:
			bits.append(f"Auto-revoked after {misses} consecutive missed calls.")
		else:
			bits.append("Permission was revoked.")
		if seconds_until_can_request > 0:
			bits.append(f"New request available {_humanize_eta(seconds_until_can_request)}.")
		else:
			bits.append("You can send a fresh request now.")
		state["detail"] = " ".join(bits)

	else:
		state["tone"] = "neutral"
		state["label"] = perm.status or "Unknown call permission state"
		state["detail"] = "Status not recognised. Check the WhatsApp Call Permission record."

	return state


def _empty_permission_state(detail):
	return {
		"status": None,
		"tone": "neutral",
		"label": "No call permission yet",
		"detail": detail or "No call-permission request has been sent to this contact.",
		"can_call": False,
		"can_request_permission": True,
		"timings": {
			"last_request_at": None,
			"granted_at": None,
			"expires_at": None,
			"can_request_again_at": None,
			"seconds_left_in_window": None,
			"seconds_until_can_request": 0,
		},
		"counters": {
			"consecutive_missed_calls": 0,
			"misses_to_revoke": CALL_PERMISSION_AUTO_REVOKE_THRESHOLD,
		},
	}


def _iso(value):
	if not value:
		return None
	dt = get_datetime(value)
	return dt.isoformat() if dt else None


def _seconds_until(now_dt, target):
	if not target:
		return 0
	target_dt = get_datetime(target)
	return max(0, int((target_dt - now_dt).total_seconds()))


def _humanize_seconds(secs):
	if secs <= 0:
		return "0m"
	if secs < 60:
		return "less than a minute"
	minutes, secs = divmod(secs, 60)
	hours, minutes = divmod(minutes, 60)
	days, hours = divmod(hours, 24)
	if days:
		return f"{days}d {hours}h" if hours else f"{days}d"
	if hours:
		return f"{hours}h {minutes}m" if minutes else f"{hours}h"
	return f"{minutes}m"


def _humanize_eta(secs):
	if secs <= 0:
		return "now"
	return f"in {_humanize_seconds(secs)}"


# ═══════════════════════════════════════════════════════════════════════
# Analytics / lookup helpers
# ═══════════════════════════════════════════════════════════════════════


def get_call_history(phone_number="", limit=5):
	if not phone_number:
		return {"calls": [], "summary": {"total_calls": 0, "missed_count": 0, "total_duration_seconds": 0, "total_duration_display": "00:00"}}
	clean = _format_number(phone_number)
	if len(clean) < 10:
		return {"calls": [], "summary": {"total_calls": 0, "missed_count": 0, "total_duration_seconds": 0, "total_duration_display": "00:00"}}
	last10 = clean[-10:]

	# Fetch recent calls (limited)
	calls = frappe.db.sql(
		"""
        SELECT name, call_id, direction, status, caller_number, callee_number,
               start_time, end_time, duration_seconds, duration_display,
               agent, notes, recording_url, is_acknowledged
        FROM `tabWhatsApp Call`
        WHERE caller_number LIKE %s OR callee_number LIKE %s
        ORDER BY start_time DESC LIMIT %s
    """,
		(f"%{last10}", f"%{last10}", int(limit)),
		as_dict=True,
	)

	# Compute summary stats across ALL calls (not just the limited set)
	stats = frappe.db.sql(
		"""
        SELECT
            COUNT(*) AS total_calls,
            SUM(CASE WHEN status = 'Missed' THEN 1 ELSE 0 END) AS missed_count,
            SUM(CASE WHEN status = 'Completed' THEN COALESCE(duration_seconds, 0) ELSE 0 END) AS total_duration_seconds
        FROM `tabWhatsApp Call`
        WHERE caller_number LIKE %s OR callee_number LIKE %s
    """,
		(f"%{last10}", f"%{last10}"),
		as_dict=True,
	)
	s = stats[0] if stats else {}
	total_dur = int(s.get("total_duration_seconds") or 0)

	return {
		"calls": calls,
		"summary": {
			"total_calls": int(s.get("total_calls") or 0),
			"missed_count": int(s.get("missed_count") or 0),
			"total_duration_seconds": total_dur,
			"total_duration_display": _format_duration(total_dur) if total_dur else "00:00",
		},
	}


def get_call_permission_templates(whatsapp_account=None, to_number=None):
	filters = {"is_call_permission": 1, "status": "APPROVED"}

	if not whatsapp_account and to_number:
		try:
			wa = resolve_wa_account(to_number=to_number)
			if wa:
				whatsapp_account = wa.name
		except Exception:
			pass

	if whatsapp_account:
		filters["whatsapp_account"] = whatsapp_account

	return frappe.get_all(
		"WhatsApp Templates",
		filters=filters,
		fields=["name", "template_name", "language_code", "status", "category"],
		order_by="template_name asc",
	)


def lookup_caller(phone_number=""):
	"""Resolve a phone number to a CRM Lead or Contact for the incoming-call
	overlay. Read-only, minimal fields — see api layer for the
	allow_guest rationale.

	Channel Handle lookups are restricted to WhatsApp and SMS and skip
	BSUID handles (`INSTR(platform_handle, '.') = 0`; phones never contain a dot)
	so non-phone channels (Instagram/Facebook user IDs) and WhatsApp
	business-scoped user ids are never matched as incoming phone callers.
	"""
	if not phone_number:
		return None
	clean = _format_number(phone_number)
	if len(clean) < 10:
		return None
	last10 = clean[-10:]

	# 1. Check open/recent Conversation for immediate active customer name & avatar
	conv = frappe.db.sql(
		"""
		SELECT c.name, c.customer_name, c.customer_phone, c.crm_party_type, c.crm_party,
		       h.profile_picture_url, h.display_name
		FROM `tabConversation` c
		LEFT JOIN `tabChannel Handle` h ON h.name = c.channel_handle
		WHERE c.customer_phone LIKE %s
		ORDER BY (CASE WHEN c.customer_name IS NOT NULL AND c.customer_name != '' AND c.customer_name != c.customer_phone THEN 1 ELSE 2 END),
		         c.modified DESC
		LIMIT 1
		""",
		(f"%{last10}",),
		as_dict=True,
	)
	if conv and conv[0].customer_name and conv[0].customer_name != conv[0].customer_phone:
		image = conv[0].profile_picture_url or ""
		if not image and conv[0].crm_party_type == "CRM Lead" and conv[0].crm_party:
			image = frappe.db.get_value("CRM Lead", conv[0].crm_party, "image") or ""
		return {
			"doctype": conv[0].crm_party_type or "Conversation",
			"docname": conv[0].crm_party or conv[0].name,
			"name": conv[0].customer_name,
			"image": image or "",
			"mobile_no": conv[0].customer_phone or phone_number,
		}

	# 2. Check CRM Lead
	lead = frappe.db.sql(
		"""
		SELECT name, lead_name, image, mobile_no, phone FROM `tabCRM Lead`
		WHERE mobile_no LIKE %s OR phone LIKE %s
		ORDER BY (CASE WHEN lead_name IS NOT NULL AND lead_name != '' AND lead_name != mobile_no THEN 1 ELSE 2 END),
		         modified DESC
		LIMIT 1
		""",
		(f"%{last10}", f"%{last10}"),
		as_dict=True,
	)
	if lead and lead[0].lead_name and lead[0].lead_name != lead[0].mobile_no:
		image = lead[0].image or ""
		if not image:
			handle = frappe.db.sql(
				"""
				SELECT profile_picture_url FROM `tabChannel Handle`
				WHERE channel_type IN (%s, %s)
				  AND platform_handle LIKE %s AND INSTR(platform_handle, '.') = 0
				  AND profile_picture_url IS NOT NULL AND profile_picture_url != ''
				LIMIT 1
				""",
				(ChannelType.WHATSAPP, ChannelType.SMS, f"%{last10}"),
				as_dict=True,
			)
			if handle:
				image = handle[0].profile_picture_url or ""
		return {
			"doctype": "CRM Lead",
			"docname": lead[0].name,
			"name": lead[0].lead_name or "",
			"image": image or "",
			"mobile_no": lead[0].mobile_no or lead[0].phone or phone_number,
		}

	# 3. Check Contact
	contact = frappe.db.sql(
		"""
		SELECT name, full_name, image, mobile_no, phone FROM `tabContact`
		WHERE mobile_no LIKE %s OR phone LIKE %s
		ORDER BY modified DESC
		LIMIT 1
		""",
		(f"%{last10}", f"%{last10}"),
		as_dict=True,
	)
	if contact:
		image = contact[0].image or ""
		if not image:
			handle = frappe.db.sql(
				"""
				SELECT profile_picture_url FROM `tabChannel Handle`
				WHERE channel_type IN (%s, %s)
				  AND platform_handle LIKE %s AND INSTR(platform_handle, '.') = 0
				  AND profile_picture_url IS NOT NULL AND profile_picture_url != ''
				LIMIT 1
				""",
				(ChannelType.WHATSAPP, ChannelType.SMS, f"%{last10}"),
				as_dict=True,
			)
			if handle:
				image = handle[0].profile_picture_url or ""
		return {
			"doctype": "Contact",
			"docname": contact[0].name,
			"name": contact[0].full_name or "",
			"image": image or "",
			"mobile_no": contact[0].mobile_no or contact[0].phone or phone_number,
		}

	# 4. Check Channel Handle
	handle = frappe.db.sql(
		"""
		SELECT name, display_name, profile_picture_url, platform_handle FROM `tabChannel Handle`
		WHERE channel_type IN (%s, %s)
		  AND platform_handle LIKE %s AND INSTR(platform_handle, '.') = 0 AND (profile_picture_url IS NOT NULL OR display_name IS NOT NULL)
		LIMIT 1
		""",
		(ChannelType.WHATSAPP, ChannelType.SMS, f"%{last10}"),
		as_dict=True,
	)
	if handle:
		return {
			"doctype": "Channel Handle",
			"docname": handle[0].name,
			"name": handle[0].display_name or "",
			"image": handle[0].profile_picture_url or "",
			"mobile_no": handle[0].platform_handle or phone_number,
		}

	return None


def call_analytics_summary(whatsapp_account: str | None = None, days: int = 30) -> dict:
	"""Aggregate call counts/duration for the last `days` — backs an
	analytics dashboard without the SPA having to compute it client-side."""
	from frappe.utils import add_to_date

	filters = {"start_time": (">=", add_to_date(now(), days=-days))}
	if whatsapp_account:
		filters["whatsapp_account"] = whatsapp_account

	rows = frappe.get_all(
		CALL_DOCTYPE,
		filters=filters,
		fields=["status", "direction", "duration_seconds"],
	)
	total = len(rows)
	completed = [r for r in rows if r.status == CallStatus.COMPLETED]
	missed = [r for r in rows if r.status == CallStatus.MISSED]
	total_duration = sum((r.duration_seconds or 0) for r in completed)

	return {
		"total_calls": total,
		"completed": len(completed),
		"missed": len(missed),
		"inbound": len([r for r in rows if r.direction == CallDirection.INBOUND]),
		"outbound": len([r for r in rows if r.direction == CallDirection.OUTBOUND]),
		"total_duration_seconds": total_duration,
		"avg_duration_seconds": int(total_duration / len(completed)) if completed else 0,
	}


def get_unread_missed_calls_count(user=None):
	"""Count missed inbound WhatsApp calls not yet acknowledged by the agent."""
	user = user or frappe.session.user
	return frappe.db.count(
		CALL_DOCTYPE,
		{
			"status": CallStatus.MISSED,
			"direction": CallDirection.INBOUND,
			"agent": user,
			"is_acknowledged": 0,
		},
	)


def acknowledge_missed_calls(phone_number=None):
	"""Mark missed calls as acknowledged for a phone number or all for current user."""
	user = frappe.session.user
	if phone_number:
		clean = _format_number(phone_number)
		if len(clean) >= 10:
			last10 = clean[-10:]
			frappe.db.sql(
				"""UPDATE `tabWhatsApp Call`
				   SET is_acknowledged = 1
				   WHERE status = 'Missed' AND direction = 'Inbound'
				   AND agent = %s AND is_acknowledged = 0
				   AND caller_number LIKE %s""",
				(user, f"%{last10}"),
			)
	else:
		frappe.db.sql(
			"""UPDATE `tabWhatsApp Call`
			   SET is_acknowledged = 1
			   WHERE status = 'Missed' AND direction = 'Inbound'
			   AND agent = %s AND is_acknowledged = 0""",
			(user,),
		)
	frappe.db.commit()
