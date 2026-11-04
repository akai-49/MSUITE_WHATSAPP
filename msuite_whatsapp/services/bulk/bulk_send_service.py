"""
Bulk WhatsApp Message service — queueing, per-recipient send orchestration,
pause/resume/retry. Extracted from the doctype controller (see
WHATSAPP_REFACTOR_PLAN.md §5).

Doctype methods (`queue_messages`, `create_single_message`, ...) delegate
here, passing `self` as `doc` so this module can read/write doc state
without owning the Document lifecycle.
"""

from __future__ import annotations

import json
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import get_system_timezone, now_datetime

from msuite_core.utils.phone import normalize_phone
from msuite_whatsapp.services.channels.inbox_channel import is_bsuid
from msuite_whatsapp.services.domain import BulkMessageStatus
from msuite_whatsapp.services.bulk.rate_limit_service import claim_for_account
from msuite_whatsapp.services.validators.bulk_message_validator import to_site_naive_datetime
from msuite_whatsapp.services.validators.error_classifier import classify_meta_error

BULK_MESSAGE_DOCTYPE = "Bulk WhatsApp Message"

# Row statuses a (re)queue run will attempt to send. Mirrors the AWS
# manifest's own sendable set for this doctype
# (aws_pipeline/manifest.py _SPEC["Bulk WhatsApp Message"]["sendable"]) so
# Standard and AWS routing never disagree about what "sendable" means. ""
# covers a row created without an explicit status.
#
# Applies to PER-BLAST rows only (recipient_type "Individual"). Rows under a
# shared `WhatsApp Recipient List` carry other blasts' outcomes in this
# column — see `queue_messages` for how those are filtered instead.
_SENDABLE = ("", "Queued", "Failed", "Retrying")


def queue_messages(doc) -> None:
	"""Enqueue each recipient as a background job."""
	# Audit H11: a Recipient-List blast now copies the list into its OWN rows
	# first, so every per-recipient status/retry write below is scoped to this
	# blast instead of the shared list other blasts also read.
	snapshot_list_recipients(doc)
	recipients = get_recipients(doc)

	# Dedupe by phone and drop rows that aren't sendable or that belong to a
	# number opted out of WhatsApp — *before* anything gets flipped to Queued
	# or handed to the AWS manifest. Without this, a duplicate or an opted-out
	# recipient would get force-included by the flip below (Standard path) or
	# by the AWS manifest builder re-deriving rows from a status this loop
	# never should have set. Mirrors SMS/Email's `to_send` construction.
	#
	# WHERE WHATSAPP DIVERGES FROM SMS/EMAIL: a "Recipient List" blast reads
	# straight off the shared `WhatsApp Recipient List` (see
	# `aws_pipeline/manifest.py::row_parent`) — those rows are reused by every
	# blast pointed at that list, unlike SMS/Email recipient rows which are
	# always freshly created per blast. Their `status` column therefore holds
	# the PREVIOUS blast's outcome, so filtering on it would make a second
	# blast to the same list compute `to_send == []` and silently no-op. For
	# list-backed blasts "already attempted" is read per-blast off Channel
	# Message keyed on `reference_name` instead — the same keying
	# `is_recipient_attempted()` uses, and for exactly the same reason.
	list_backed = row_parent(doc)[1] != BULK_MESSAGE_DOCTYPE  # legacy blasts only
	attempted = attempted_recipients(doc) if list_backed else set()

	to_send = []
	seen = set()
	for r in recipients:
		raw_mobile = r.get("mobile_number") or ""
		if is_bsuid(raw_mobile):
			# Bulk/campaign sends remain phone-only (Meta recommends phone for marketing);
			# stamp skipped BSUID rows with a terminal status so campaigns can complete.
			if r.get("name"):
				frappe.db.set_value(
					"WhatsApp Recipient",
					r["name"],
					{
						"status": "Failed",
						"failure_reason": "BSUID recipients are not supported for bulk marketing campaigns",
					},
					update_modified=False,
				)
			continue
		phone_clean = normalize_phone(raw_mobile)
		if not phone_clean or phone_clean in seen:
			continue
		seen.add(phone_clean)

		# The LIVE opt-out flag is read first, ahead of any stored row status:
		# a stored "Unsubscribed" is only ever a stamp from an earlier run, and
		# on a shared list row it would otherwise exclude a member who has since
		# re-subscribed from that list forever.
		#
		# Opted-out rows are stamped (not just skipped) for the same reason
		# SMS/Email stamp theirs: `dispatch/batched_enqueue.py`'s chunk path
		# re-derives its own sendable set straight from each row's `status`
		# column (`SENDABLE_STATUSES = ("Queued", "Retrying")`), completely
		# independent of this function's `to_send` list. A row left at
		# whatever status it already had — e.g. "Queued" from being queued
		# before the recipient opted out — would still be picked up and sent.
		# The stamp is safe on a shared list row because nothing below ever
		# gates on it: it is re-derived from the live flag on every run.
		if is_opted_out(r.get("mobile_number")):
			if r.get("name"):
				frappe.db.set_value("WhatsApp Recipient", r["name"], "status", "Unsubscribed")
			continue

		if list_backed:
			if phone_clean in attempted:
				continue
		else:
			# Per-blast rows: the row's own status is this blast's state, so
			# it is the sendable filter. "Unsubscribed" is re-openable here
			# precisely because the live opt-out check above just said this
			# number is no longer opted out.
			status = r.get("status")
			if status not in _SENDABLE and status != "Unsubscribed":
				continue

		to_send.append(r)

	if not to_send:
		# Nothing left to send — but the blast still has to settle. Every row
		# may have been legitimately excluded (all duplicates, all opted out,
		# all already sent), and those rows never produce a Channel Message,
		# so nothing else would ever come along and finish this doc. SMS's
		# `queue_messages` calls its completion check on this same path.
		_check_and_update_completion(doc)
		return

	# AWS execution plane. Checked before the per-row flip below: the AWS
	# branch's own bulk flip (`_mark_queued` in aws_pipeline/dispatch.py)
	# only fires after `trigger_campaign` succeeds, so flipping here first
	# would mark rows Queued before AWS has actually accepted the campaign.
	#
	# What the AWS path does NOT do, and the Standard path does: create a
	# Channel Message, Conversation and Channel Handle per recipient, and
	# ensure a CRM Lead. That is ~4 MariaDB rows per recipient — 400k on a 100k
	# blast — which is exactly the load this engine exists to remove, but it
	# also means AWS-routed WhatsApp sends do not appear in the inbox and a
	# reply will not thread onto the outbound message. Phase 4's webhook relay
	# is where that record can be rebuilt, from the delivery callback, without
	# putting the writes back on the send path.
	from msuite_campaigns.aws_pipeline import dispatch as aws_dispatch

	if aws_dispatch.should_use_aws(doc, to_send):
		try:
			aws_dispatch.export_and_enqueue(doc, to_send)
		except Exception:
			doc.db_set("status", BulkMessageStatus.AWS_DISPATCH_FAILED, update_modified=False, commit=True)
			raise
		return

	# Set status of sendable recipients to 'Queued' in the database
	names = [r["name"] for r in to_send if r.get("name")]
	if names:
		placeholders = ", ".join(["%s"] * len(names))
		frappe.db.sql(
			f"UPDATE `tabWhatsApp Recipient` SET status = 'Queued' WHERE name IN ({placeholders})",
			tuple(names),
		)

	# Batched path: one job per 500 recipients instead of one per recipient.
	# Only blasts created by the unified dispatch hub set this flag — Frappe
	# backfills a new Check as 0, so every existing blast falls through to the
	# per-recipient loop below, unchanged.
	if getattr(doc, "use_batched_enqueue", 0):
		from msuite_campaigns.dispatch import batched_enqueue

		batched_enqueue.enqueue_chunks(doc.doctype, doc.name)
		return

	for recipient in to_send:
		frappe.enqueue_doc(
			doc.doctype,
			doc.name,
			"create_single_message",
			queue="long",
			timeout=4000,
			recipient=recipient,
		)


def is_opted_out(number: str) -> bool:
	"""True when this number has unsubscribed from WhatsApp on its Audience
	Member record or Channel Handle metadata.

	WhatsApp's own opt-out concept — same `Audience Member` registry SMS's
	`is_opted_out` checks, but keyed on `unsubscribed_whatsapp` instead of
	`unsubscribed_sms` (see `audience/doctype/audience/audience.py`'s
	`members_for`, which already splits opt-out by channel this way).
	For BSUID handles, the opt-out flag is stored on Channel Handle metadata.
	"""
	if not number:
		return False
	from msuite_whatsapp.services.channels.inbox_channel import is_bsuid
	clean = str(number).strip()
	if is_bsuid(clean):
		import json
		handle = frappe.db.get_value(
			"Channel Handle",
			{"channel_type": "WhatsApp", "bsuid": clean},
			["name", "metadata"],
			as_dict=True,
		) or frappe.db.get_value(
			"Channel Handle",
			{"channel_type": "WhatsApp", "platform_handle": clean},
			["name", "metadata"],
			as_dict=True,
		)
		if handle and handle.metadata:
			meta = json.loads(handle.metadata) if isinstance(handle.metadata, str) else dict(handle.metadata or {})
			return bool(meta.get("opted_out"))
		return False
	return bool(
		frappe.db.exists(
			"Audience Member",
			{"phone_e164": number, "unsubscribed_whatsapp": 1},
		)
	)


def row_parent(doc) -> tuple[str, str]:
	"""`(parent, parenttype)` of this blast's WhatsApp Recipient rows — the
	single source of truth (aws_pipeline.manifest and dispatch.batched_enqueue
	delegate here).

	The blast's own rows win whenever they exist: Individual blasts, and
	Recipient-List blasts snapshotted by `snapshot_list_recipients` (audit
	H11). Only legacy list-backed blasts that were never snapshotted still
	resolve to the shared `WhatsApp Recipient List`.
	"""
	name = doc if isinstance(doc, str) else getattr(doc, "name", None) or doc.get("name")
	if frappe.db.exists("WhatsApp Recipient", {"parent": name, "parenttype": BULK_MESSAGE_DOCTYPE}):
		return name, BULK_MESSAGE_DOCTYPE
	if isinstance(doc, str):
		rtype, rlist = frappe.db.get_value(BULK_MESSAGE_DOCTYPE, name, ["recipient_type", "recipient_list"]) or (
			None,
			None,
		)
	else:
		rtype = getattr(doc, "recipient_type", None) or (doc.get("recipient_type") if hasattr(doc, "get") else None)
		rlist = getattr(doc, "recipient_list", None) or (doc.get("recipient_list") if hasattr(doc, "get") else None)
	if rtype == "Recipient List" and rlist:
		return rlist, "WhatsApp Recipient List"
	return name, BULK_MESSAGE_DOCTYPE


def snapshot_list_recipients(doc) -> int:
	"""Copy a Recipient-List blast's recipients into its own child rows, once.

	Before this, every send wrote status / retry_count / error_code onto the
	SHARED list rows, so a second blast to the same list inherited the first
	one's outcomes and concurrent blasts clobbered each other (audit H11).
	Same model Bulk Email already uses (`_snapshot_list_recipients`).

	Phones this blast already messaged (a legacy blast being resumed/requeued)
	are copied as "Sent" so they are not sent again.
	"""
	if not (doc.get("recipient_type") == "Recipient List" and doc.get("recipient_list")):
		return 0
	# Serialise concurrent snapshot attempts on the blast row.
	frappe.db.get_value(BULK_MESSAGE_DOCTYPE, doc.name, "name", for_update=True)
	if frappe.db.exists("WhatsApp Recipient", {"parent": doc.name, "parenttype": BULK_MESSAGE_DOCTYPE}):
		return 0

	rows = frappe.get_all(
		"WhatsApp Recipient",
		filters={"parent": doc.recipient_list, "parenttype": "WhatsApp Recipient List"},
		fields=["mobile_number", "recipient_name", "country_code", "recipient_data"],
		order_by="idx asc",
	)
	# Skip blank and duplicate numbers here: queue_messages would skip them
	# too, but a skipped row left at "Queued" keeps the blast "pending" forever.
	unique, seen = [], set()
	for r in rows:
		phone_clean = normalize_phone(r.mobile_number)
		if phone_clean and phone_clean not in seen:
			seen.add(phone_clean)
			unique.append(r)
	rows = unique
	if not rows:
		return 0
	attempted = attempted_recipients(doc)
	now = frappe.utils.now()
	user = frappe.session.user
	values = [
		(
			frappe.generate_hash(length=10),
			now,
			now,
			user,
			user,
			doc.name,
			BULK_MESSAGE_DOCTYPE,
			"recipients",
			idx,
			doc.docstatus or 0,
			r.mobile_number,
			r.recipient_name,
			r.country_code,
			r.recipient_data,
			"Sent" if normalize_phone(r.mobile_number) in attempted else "Queued",
		)
		for idx, r in enumerate(rows, start=1)
	]
	frappe.db.bulk_insert(
		"WhatsApp Recipient",
		fields=[
			"name", "creation", "modified", "owner", "modified_by",
			"parent", "parenttype", "parentfield", "idx", "docstatus",
			"mobile_number", "recipient_name", "country_code", "recipient_data", "status",
		],
		values=values,
	)
	frappe.db.set_value(BULK_MESSAGE_DOCTYPE, doc.name, "recipient_count", len(values), update_modified=False)
	return len(values)


def get_recipients(doc) -> list[dict]:
	"""This blast's recipient rows (own rows, or the shared list for legacy
	list-backed blasts — see `row_parent`)."""
	parent, parenttype = row_parent(doc)
	return frappe.get_all(
		"WhatsApp Recipient",
		filters={"parent": parent, "parenttype": parenttype},
		fields=["name", "status", "mobile_number", "recipient_name", "recipient_data"],
		order_by="idx asc",
	)


def create_single_message(doc, recipient: dict) -> None:
	"""Send one templated WhatsApp message through the inbox pipeline.

	Each recipient lands as an outbound Channel Message linked back to
	this Bulk job via `reference_doctype`/`reference_name`. The send goes
	through the shared `inbox.services.outbound.send_to_phone` helper so:
	  • the recipient gets a Channel Handle (find-or-create)
	  • the message lands on a Conversation (reuse open or create)
	  • status / sent-at / read-at populate naturally as Meta sends the webhook
	  • rollups can count Channel Message rows where reference_name= this bulk job

	Pause gate: `queue_messages` enqueues every recipient upfront as a
	separate background job, so we can't stop in-flight sends from the
	queue side. This early-return is the per-job gate that picks up the
	pause flag (set by the parent Campaign cascade, or by a per-blast
	Pause button) and skips the send. The job is ack'd as no-op so RQ
	doesn't retry; the marketer can Resume and re-queue failed recipients
	afterwards.

	Rate gate: before calling Meta, checks the phone's rolling 24h send
	count against its portfolio's Meta-assigned messaging limit (see
	`services/rate_limit_service.py`) — protects against a wave of 429s
	and quality-rating damage on large broadcasts.
	"""
	from msuite_inbox.inbox.services.outbound import send_to_phone

	# Re-read the flag from the DB — the in-memory `doc.is_paused` is from
	# when the job was enqueued, but the marketer may have paused mid-batch.
	if frappe.db.get_value(BULK_MESSAGE_DOCTYPE, doc.name, "is_paused"):
		return

	# Prevent duplicate sends if queue_messages was invoked twice for the same broadcast
	phone_clean = normalize_phone(recipient.get("mobile_number"))
	if phone_clean and is_recipient_attempted(doc.doctype, doc.name, phone_clean):
		return

	# is_recipient_attempted is check-then-send: two jobs for the same phone
	# (a duplicate enqueue, a resume racing the original) could both pass it.
	# Claim (blast, phone) atomically — before the rate limiter, so a losing
	# duplicate doesn't consume quota; released on failure/deferral.
	claim_key = _send_claim_key(doc.name, phone_clean)
	if phone_clean and not _claim_send(claim_key):
		return

	if _is_rate_limited(doc, phone_clean):
		_release_send_claim(claim_key)
		_defer_recipient(doc, recipient)
		return

	# Only move Queued/Scheduled → In Progress. An unconditional write here
	# used to clobber Partially Failed back to In Progress whenever a
	# successful job ran after a failed one, leaving the blast stuck
	# "In Progress" forever (sent_count never reaches recipient_count when
	# any recipient failed, so no finalizer would ever fire).
	frappe.db.sql(
		f"UPDATE `tab{BULK_MESSAGE_DOCTYPE}` SET status = %s WHERE name = %s AND status IN (%s, %s)",
		(BulkMessageStatus.IN_PROGRESS, doc.name, BulkMessageStatus.QUEUED, BulkMessageStatus.SCHEDULED),
	)
	recipient_data = _parse_recipient_data(recipient)

	body_param = recipient.get("body_param") if recipient.get("body_param") is not None else None
	if body_param is None and doc.template_variables:
		body_param = build_body_param(doc, recipient_data)

	thumbnail_product_retailer_id = getattr(doc, "thumbnail_product_retailer_id", None)
	if not thumbnail_product_retailer_id and doc.template:
		thumbnail_product_retailer_id = frappe.db.get_value(
			"WhatsApp Templates", doc.template, "thumbnail_product_retailer_id"
		)

	payload = {
		"type": "template",
		"template": doc.template,
		"body_param": body_param,
		"attach": doc.attach or None,
		"whatsapp_account": doc.whatsapp_account or None,
		"sender_type": "Bot",
		"thumbnail_product_retailer_id": thumbnail_product_retailer_id or None,
	}

	mpm_action = get_mpm_action_json(doc)
	if mpm_action:
		payload["product_catalog_json"] = mpm_action

	if getattr(doc, "is_carousel_template", 0) and doc.carousel_catalog:
		payload["catalog"] = doc.carousel_catalog
		payload["product_retailer_ids"] = list(
			dict.fromkeys(row.item_code for row in (doc.product_ids or []) if row.item_code)
		)[:10]

	# Auto-create or link CRM Lead for recipient (using name if provided, otherwise phone)
	_ensure_lead_for_bulk_recipient(
		phone=recipient.get("mobile_number"),
		recipient_name=recipient.get("recipient_name"),
		bulk_doc=doc,
	)

	try:
		# Inside the try: an offer that ended while the blast was queued fails
		# this recipient with a clear reason, before any Meta call.
		payload.update(_offer_payload_extras(doc))
		send_result = send_to_phone(
			phone=recipient.get("mobile_number"),
			payload=payload,
			reference_doctype=doc.doctype,
			reference_name=doc.name,
		)
	except Exception as e:
		_release_send_claim(claim_key)
		error_code, failure_reason, is_retryable = classify_meta_error(e)
		frappe.db.set_value(
			BULK_MESSAGE_DOCTYPE, doc.name, "status", BulkMessageStatus.PARTIALLY_FAILED, update_modified=False
		)

		phone = recipient.get("mobile_number")
		if phone:
			# This blast's own rows (audit H11) — never the shared list for
			# snapshotted blasts; legacy list-backed blasts keep old behaviour.
			parent_name, parent_dt = row_parent(doc)

			# Get current retry_count for this recipient
			current_retries = 0
			existing = frappe.db.sql(
				"""
				SELECT retry_count FROM `tabWhatsApp Recipient`
				WHERE parenttype = %s AND parent = %s AND (mobile_number = %s OR REPLACE(mobile_number, '+', '') = REPLACE(%s, '+', ''))
				LIMIT 1
				""",
				(parent_dt, parent_name, phone, phone),
				as_dict=True,
			)
			if existing:
				current_retries = int(existing[0].get("retry_count") or 0)

			is_deferred = (error_code == "131049")
			max_retries = 2 if is_deferred else 3
			should_auto_retry = is_retryable and current_retries < max_retries
			next_status = "Retrying" if should_auto_retry else "Failed"
			next_retry_count = current_retries + 1 if should_auto_retry else current_retries

			frappe.db.sql(
				"""
				UPDATE `tabWhatsApp Recipient`
				SET status = %s, error_code = %s, failure_reason = %s, is_retryable = %s, retry_count = %s
				WHERE parenttype = %s AND parent = %s AND (mobile_number = %s OR REPLACE(mobile_number, '+', '') = REPLACE(%s, '+', ''))
				""",
				(
					next_status,
					error_code,
					failure_reason,
					1 if is_retryable else 0,
					next_retry_count,
					parent_dt,
					parent_name,
					phone,
					phone,
				),
			)

			# Standard transient errors use fast backoff (10-30s).
			# Ecosystem limit (131049) waits for 24-48h cooldown and is picked up by bulk_message_scheduler.
			if should_auto_retry and not is_deferred:
				delay_seconds = 10 * (current_retries + 1)
				frappe.enqueue_doc(
					doc.doctype,
					doc.name,
					"create_single_message",
					queue="long",
					timeout=4000,
					recipient=recipient,
					delay=delay_seconds,
				)

		_check_and_update_completion(doc)
		return

	# The WhatsApp channel does not raise on a Meta rejection: it records a
	# "failed" Channel Message and returns ok=False.
	sent_ok = not (isinstance(send_result, dict) and send_result.get("ok") is False)

	parent_name, parent_dt = row_parent(doc)
	if parent_dt == BULK_MESSAGE_DOCTYPE:
		# Own rows (Individual or snapshotted list): settle this row and bump
		# the counter atomically — O(1) per send. The old per-send COUNT over
		# every Channel Message of the blast made a large blast O(N^2)
		# (audit H11). Completion is settled once nothing is pending.
		if sent_ok:
			_mark_own_row(doc.name, recipient, "Sent")
			frappe.db.sql(
				f"UPDATE `tab{BULK_MESSAGE_DOCTYPE}` SET sent_count = COALESCE(sent_count, 0) + 1 WHERE name = %s",
				(doc.name,),
			)
		else:
			_mark_own_row(doc.name, recipient, "Failed")
			_release_send_claim(claim_key)  # let Retry Failed re-send it
		if not _has_pending_rows(doc.name):
			_check_and_update_completion(doc)
	else:
		# Legacy list-backed blast (never snapshotted): unchanged behaviour.
		actual_sent = frappe.db.count(
			"Channel Message",
			filters={"reference_doctype": doc.doctype, "reference_name": doc.name, "status": ["!=", "failed"]},
		)
		actual_total = frappe.db.count("WhatsApp Recipient", {"parent": parent_name, "parenttype": parent_dt})
		frappe.db.sql(
			f"UPDATE `tab{BULK_MESSAGE_DOCTYPE}` SET sent_count = %s, recipient_count = GREATEST(recipient_count, %s) WHERE name = %s",
			(actual_sent, actual_total, doc.name),
		)
		_check_and_update_completion(doc)
	frappe.db.commit()


def _offer_expiry_to_ms(doc) -> int | None:
	"""Convert `doc.offer_expires_at` (naive, site time zone) to UNIX milliseconds.

	Returns None when no expiry is set. Raises `frappe.ValidationError` if the
	expiry is not in the future (the offer ended while the blast was queued).
	"""
	if not doc.get("offer_expires_at"):
		return None
	expiry = to_site_naive_datetime(doc.offer_expires_at)
	if expiry <= now_datetime():
		frappe.throw(_("Offer ended before this message could be sent."))
	return int(expiry.replace(tzinfo=ZoneInfo(get_system_timezone())).timestamp() * 1000)


def _offer_payload_extras(doc) -> dict:
	"""Offer keys for the send payload (`limited_time_offer_expiry_ms`,
	`coupon_code`, `tap_target`); only those the blast actually sets.
	Raises `frappe.ValidationError` via `_offer_expiry_to_ms` when the offer ended."""
	extras: dict = {}
	expiry_ms = _offer_expiry_to_ms(doc)
	if expiry_ms is not None:
		extras["limited_time_offer_expiry_ms"] = expiry_ms
	if doc.get("coupon_code"):
		extras["coupon_code"] = doc.coupon_code
	if doc.get("tap_target_url") or doc.get("tap_target_title"):
		extras["tap_target"] = {"url": doc.get("tap_target_url"), "title": doc.get("tap_target_title")}
	return extras


_PENDING_ROW_STATUSES = ("", "Queued", "Retrying")
_SEND_CLAIM_TTL = 60 * 60


def _send_claim_key(doc_name: str, phone_clean: str) -> str:
	return f"bulk_wa_send|{doc_name}|{phone_clean}"


def _claim_send(key: str) -> bool:
	"""Redis SET NX EX — True if this job owns the (blast, phone) send."""
	try:
		cache = frappe.cache()
		return bool(cache.set(cache.make_key(key), 1, nx=True, ex=_SEND_CLAIM_TTL))
	except Exception:
		# Fail open (as the rate limiter does): a Redis blip must not stop a
		# blast; is_recipient_attempted still guards the common case.
		return True


def _release_send_claim(key: str) -> None:
	try:
		cache = frappe.cache()
		cache.delete(cache.make_key(key))
	except Exception:
		pass


def _mark_own_row(doc_name: str, recipient: dict, status: str) -> None:
	"""Set status on this blast's own row for `recipient` (by row name when
	known, else by phone within this blast)."""
	row_name = recipient.get("name")
	if row_name and frappe.db.get_value("WhatsApp Recipient", row_name, "parent") == doc_name:
		frappe.db.set_value("WhatsApp Recipient", row_name, "status", status, update_modified=False)
		return
	phone = recipient.get("mobile_number")
	if phone:
		frappe.db.sql(
			"""UPDATE `tabWhatsApp Recipient` SET status = %s
			WHERE parenttype = %s AND parent = %s AND (mobile_number = %s OR mobile_number = %s)""",
			(status, BULK_MESSAGE_DOCTYPE, doc_name, phone, f"+{normalize_phone(phone)}"),
		)


def _has_pending_rows(doc_name: str) -> bool:
	return bool(
		frappe.db.exists(
			"WhatsApp Recipient",
			{"parent": doc_name, "parenttype": BULK_MESSAGE_DOCTYPE, "status": ["in", _PENDING_ROW_STATUSES]},
		)
	)


def _is_rate_limited(doc, recipient_phone: str) -> bool:
	"""Check (and provisionally claim a slot against) the business portfolio's
	rolling-24h limit of unique recipients. Meta shares one limit across every
	number in a portfolio, so the key is the account's `business_id` (the account
	itself when it has none). Returns True if this send should be deferred
	instead of fired - i.e. `recipient_phone` would be over the limit."""
	if not getattr(doc, "whatsapp_account", None) or not recipient_phone:
		return False
	return not claim_for_account(doc.whatsapp_account, recipient_phone, fail_open=False)


def _deferred_key(doc_name: str) -> str:
	# RedisWrapper.rpush/lpop run the key through make_key, which adds the
	# site namespace — no manual prefixing needed.
	return f"wa_deferred|{doc_name}"


def _defer_recipient(doc, recipient: dict) -> None:
	"""Park a recipient whose send was deferred by the rate governor.

	Immediately re-enqueueing here created a hot loop: the re-run hit the
	same (still exhausted) cap and re-enqueued again, churning the long
	queue for up to 24h. Instead the recipient goes onto a Redis list and
	the 5-minute bulk scheduler (`schedule_bulk_messages`) drains it —
	each drained recipient re-checks the cap and, if still over, parks
	itself again. Worst case one attempt per recipient per 5 minutes.
	"""
	frappe.cache().rpush(_deferred_key(doc.name), json.dumps(recipient))


def clear_deferred(doc_name: str) -> None:
	"""Drop any rate-deferred recipients parked for this broadcast — used
	on cancel so the scheduler never resurrects them."""
	try:
		cache = frappe.cache()
		cache.unlink(cache.make_key(_deferred_key(doc_name)))
	except Exception:
		pass


def requeue_deferred(doc_name: str) -> int:
	"""Drain the deferred-recipient list for a broadcast and re-enqueue
	each entry. Called by the bulk scheduler. Returns how many were
	re-enqueued."""
	cache = frappe.cache()
	key = _deferred_key(doc_name)
	count = 0
	while True:
		raw = cache.lpop(key)
		if raw is None:
			break
		try:
			recipient = json.loads(raw)
		except (json.JSONDecodeError, TypeError):
			continue
		frappe.enqueue_doc(
			BULK_MESSAGE_DOCTYPE,
			doc_name,
			"create_single_message",
			queue="long",
			timeout=4000,
			recipient=recipient,
		)
		count += 1
	return count


def _resolve_variable_value(entry, recipient_data: dict) -> str:
	"""Extract the resolved string value from a variable mapping entry.

	Handles all mapping variations:
	  - Unified wizard: {"type": "field", "value": "recipient_name"} or {"type": "static", "value": "xyz"}
	  - Classic wizard: {"mode": "unique", "key": "recipient_name"} or {"mode": "common", "value": "xyz"}
	  - String field name: "recipient_name"
	  - Direct primitive value: "Some String" or 123
	"""
	if isinstance(entry, dict):
		mode = entry.get("mode")
		val_type = entry.get("type")

		# Field mapping
		if mode == "unique" or val_type == "field":
			key = entry.get("key") or entry.get("value") or ""
			return str(recipient_data.get(key, "") if key else "")

		# Static text
		if mode in ("common", "static") or val_type in ("static", "custom"):
			return str(entry.get("value") or entry.get("staticText") or "")

		# Generic dict fallback
		if "value" in entry:
			val = entry.get("value")
			if isinstance(val, str) and val in recipient_data and val_type != "static":
				return str(recipient_data.get(val, "") or "")
			return str(val or "")
		if "key" in entry:
			return str(recipient_data.get(entry.get("key", ""), "") or "")
		return ""

	if isinstance(entry, str):
		if entry in recipient_data:
			return str(recipient_data.get(entry, "") or "")
		return entry

	if entry is not None:
		return str(entry)
	return ""


def build_body_param(doc, recipient_data: dict) -> str:
	"""
	Build body_param JSON for a WhatsApp Message.

	For NAMED templates: returns {"student": "John", "course": "BE"}
	For POSITIONAL templates: returns {"1": "John", "2": "BE"}

	Supports:
	  - Dict mapping: {"1": {"type": "field", "value": "recipient_name"}, "2": {"type": "static", "value": "xyz"}}
	  - Dict mapping with named keys: {"name": {"type": "field", "value": "recipient_name"}}
	  - List mapping: [{"mode": "unique", "key": "field_name"}, {"mode": "common", "value": "fixed text"}]
	  - List mapping with types: [{"type": "field", "value": "field_name"}, ...]
	  - List of strings: ["recipient_name", "first_name"]
	  - Direct scalar dict: {"1": "John", "2": "BE"}
	"""
	is_named = False
	var_names = []
	if doc.template:
		tpl = frappe.get_cached_doc("WhatsApp Templates", doc.template)
		if tpl and tpl.parameter_format == "NAMED":
			import re

			is_named = True
			var_names = re.findall(r"\{\{(\w+)\}\}", tpl.template or "")

	try:
		mapping = json.loads(doc.template_variables) if doc.template_variables else None
	except (json.JSONDecodeError, TypeError):
		return json.dumps(recipient_data)

	if not mapping:
		return json.dumps(recipient_data)

	if isinstance(mapping, list):
		ordered = {}
		for i, entry in enumerate(mapping):
			key = var_names[i] if is_named and i < len(var_names) else str(i + 1)
			ordered[key] = _resolve_variable_value(entry, recipient_data)
		return json.dumps(ordered)

	if isinstance(mapping, dict):
		ordered = {}
		for k, entry in mapping.items():
			key = str(k)
			if is_named and key.isdigit():
				idx = int(key) - 1
				if 0 <= idx < len(var_names):
					key = var_names[idx]
			ordered[key] = _resolve_variable_value(entry, recipient_data)
		return json.dumps(ordered)

	return json.dumps(recipient_data)


def get_mpm_action_json(doc) -> dict | None:
	"""Build Meta 'action' JSON for Multi-Product Messages."""
	if not doc.is_mpm or not doc.thumbnail_product_retailer_id or not doc.product_ids:
		return None

	products = list(dict.fromkeys(row.item_code for row in doc.product_ids if row.item_code))
	if len(products) > 30:
		products = products[:30]
		frappe.msgprint(
			_("Only the first 30 products were included (WhatsApp limit)."),
			indicator="orange",
		)

	return {
		"thumbnail_product_retailer_id": doc.thumbnail_product_retailer_id,
		"sections": [
			{
				"title": doc.mpm_header or "Our Products",
				"product_items": [{"product_retailer_id": pid} for pid in products],
			}
		],
	}


def is_recipient_attempted(doc_doctype: str, doc_name: str, phone_clean: str) -> bool:
	"""Fast O(1) check if a single recipient phone has already been attempted for this broadcast."""
	if not phone_clean:
		return False
	handles = frappe.db.get_all(
		"Channel Handle",
		filters={"platform_handle": ["in", [phone_clean, f"+{phone_clean}"]]},
		pluck="name",
	)
	if not handles:
		return False
	return bool(
		frappe.db.exists(
			"Channel Message",
			{
				"reference_doctype": doc_doctype,
				"reference_name": doc_name,
				"channel_handle": ["in", handles],
				# A failed attempt must not block a retry — otherwise
				# retry_failed's re-enqueued jobs all returned here as no-ops.
				"status": ["!=", "failed"],
			},
		)
	)


def _row_parent(doc) -> tuple[str, str]:
	"""Back-compat alias of `row_parent`."""
	return row_parent(doc)


def _check_and_update_completion(doc) -> None:
	"""Settle the blast once all attempted sends are finished."""
	curr_status = frappe.db.get_value(BULK_MESSAGE_DOCTYPE, doc.name, "status")
	if curr_status in (BulkMessageStatus.CANCELLED, BulkMessageStatus.COMPLETED):
		return

	if row_parent(doc)[1] == BULK_MESSAGE_DOCTYPE:
		if _has_pending_rows(doc.name):
			return
	else:
		parent, parenttype = row_parent(doc)
		pending = frappe.db.count(
			"WhatsApp Recipient",
			{"parent": parent, "parenttype": parenttype, "status": ["in", ("Queued", "Retrying")]},
		)
		if pending:
			return
		try:
			deferred_count = frappe.cache().llen(_deferred_key(doc.name)) or 0
		except Exception:
			deferred_count = 0
		if deferred_count > 0:
			return

	failed_count = frappe.db.count(
		"Channel Message",
		filters={"reference_doctype": doc.doctype, "reference_name": doc.name, "status": "failed"},
	)
	sent_count = frappe.db.count(
		"Channel Message",
		filters={"reference_doctype": doc.doctype, "reference_name": doc.name, "status": ["!=", "failed"]},
	)
	total_sent = max(sent_count, doc.sent_count or 0)
	total_attempted = total_sent + failed_count
	if total_attempted == 0:
		return

	new_status = BulkMessageStatus.PARTIALLY_FAILED if failed_count > 0 else BulkMessageStatus.COMPLETED
	frappe.db.sql(
		f"UPDATE `tab{BULK_MESSAGE_DOCTYPE}` SET status = %s "
		"WHERE name = %s AND status != %s",
		(new_status, doc.name, BulkMessageStatus.CANCELLED),
	)


def attempted_recipients(doc) -> set[str]:
	"""Phones (digits only) that already have a Channel Message under this
	broadcast — i.e. `create_single_message` actually ran for them,
	whether it succeeded or failed."""
	rows = frappe.get_all(
		"Channel Message",
		filters={"reference_doctype": doc.doctype, "reference_name": doc.name},
		fields=["channel_handle"],
	)
	handle_names = {r.channel_handle for r in rows if r.channel_handle}
	if not handle_names:
		return set()
	phones = frappe.get_all(
		"Channel Handle",
		filters={"name": ("in", list(handle_names))},
		pluck="platform_handle",
	)
	return {normalize_phone(p) for p in phones if p}


def requeue_unattempted(doc) -> int:
	"""Enqueue recipients that were skipped entirely (paused before their
	job ever ran) — they have no Channel Message row at all."""
	attempted = attempted_recipients(doc)
	pending = [r for r in get_recipients(doc) if normalize_phone(r.get("mobile_number")) not in attempted]
	if not pending:
		return 0

	frappe.db.set_value(BULK_MESSAGE_DOCTYPE, doc.name, "status", BulkMessageStatus.IN_PROGRESS, update_modified=False)
	for recipient in pending:
		frappe.enqueue_doc(
			doc.doctype,
			doc.name,
			"create_single_message",
			queue="long",
			timeout=4000,
			recipient=recipient,
		)
	return len(pending)


def retry_failed(doc) -> int:
	"""Re-send every previously-failed recipient through the real outbound
	pipeline (not just flip a status flag)."""
	failed_msgs = frappe.get_all(
		"Channel Message",
		filters={
			"reference_doctype": doc.doctype,
			"reference_name": doc.name,
			"status": "failed",
		},
		fields=["name", "channel_handle"],
	)
	if not failed_msgs:
		frappe.msgprint(_("No failed messages to retry."), alert=True)
		return 0

	handle_names = {m.channel_handle for m in failed_msgs if m.channel_handle}
	phones = (
		frappe.get_all(
			"Channel Handle",
			filters={"name": ("in", list(handle_names))},
			pluck="platform_handle",
		)
		if handle_names
		else []
	)
	failed_phones = {normalize_phone(p) for p in phones if p}

	retry_recipients = [
		r for r in get_recipients(doc) if normalize_phone(r.get("mobile_number")) in failed_phones
	]
	if not retry_recipients:
		frappe.msgprint(_("No failed messages to retry."), alert=True)
		return 0

	# The old failed Channel Message rows are left as-is (history). They
	# used to be flipped to "queued", but the retry sends through brand-new
	# Channel Message rows, so the flipped rows never transitioned and
	# permanently inflated the "queued" bucket in get_progress. Progress
	# now counts only each recipient's latest message (see
	# latest_status_counts), so stale rows no longer skew anything.

	frappe.db.set_value(
		BULK_MESSAGE_DOCTYPE,
		doc.name,
		{"retry_count": (doc.retry_count or 0) + 1, "status": BulkMessageStatus.IN_PROGRESS},
		update_modified=False,
	)

	# Set status of retried recipients to 'Queued' (this blast's rows only).
	retried_phones = {r.get("mobile_number") for r in retry_recipients if r.get("mobile_number")}
	if retried_phones:
		parent, parenttype = row_parent(doc)
		frappe.db.set_value(
			"WhatsApp Recipient",
			{"parenttype": parenttype, "parent": parent, "mobile_number": ["in", list(retried_phones)]},
			"status",
			"Queued",
			update_modified=False,
		)

	for recipient in retry_recipients:
		# A send Meta accepted and only later reported failed (webhook) still
		# holds its duplicate-send claim — release it or the retry no-ops.
		_release_send_claim(_send_claim_key(doc.name, normalize_phone(recipient.get("mobile_number"))))
		frappe.enqueue_doc(
			doc.doctype,
			doc.name,
			"create_single_message",
			queue="long",
			timeout=4000,
			recipient=recipient,
		)

	frappe.msgprint(_("{0} message(s) re-queued for retry.").format(len(retry_recipients)), alert=True)
	return len(retry_recipients)


def latest_status_counts(doc_name: str) -> dict[str, int]:
	"""Status counts across each recipient's latest record for this broadcast.
	Aggregates status across tabWhatsApp Recipient and tabChannel Message."""
	parent, parenttype = row_parent(doc_name)

	rows = frappe.db.sql(
		"""
        SELECT LOWER(COALESCE(cm.status, wr.status, 'queued')) AS status, COUNT(*) AS cnt
        FROM `tabWhatsApp Recipient` wr
        LEFT JOIN `tabChannel Handle` ch ON (wr.mobile_number = ch.platform_handle OR REPLACE(wr.mobile_number, '+', '') = REPLACE(ch.platform_handle, '+', ''))
        LEFT JOIN `tabChannel Message` cm ON cm.channel_handle = ch.name
            AND cm.reference_doctype = %s AND cm.reference_name = %s
        WHERE wr.parenttype = %s AND wr.parent = %s
        GROUP BY LOWER(COALESCE(cm.status, wr.status, 'queued'))
        """,
		(BULK_MESSAGE_DOCTYPE, doc_name, parenttype, parent),
		as_dict=True,
	)
	return {r.status.lower(): r.cnt for r in rows}


def get_progress(doc) -> dict:
	"""Get delivery progress stats — counted off each recipient's status."""
	counts = latest_status_counts(doc.name)
	queued = counts.get("queued", 0)
	sent = counts.get("sent", 0)
	delivered = counts.get("delivered", 0)
	read = counts.get("read", 0)
	failed = counts.get("failed", 0)
	# Permanently excluded by `queue_messages` (opted out). They will never
	# produce a Channel Message, so counting them as still-outstanding left
	# `pending` stuck above zero for the life of the blast.
	unsubscribed = counts.get("unsubscribed", 0)
	attempted = queued + sent + delivered + read + failed + unsubscribed

	parent, parenttype = row_parent(doc)
	actual_total = frappe.db.count("WhatsApp Recipient", {"parent": parent, "parenttype": parenttype})

	total = max(actual_total, attempted, doc.recipient_count or 0)
	succeeded = sent + delivered + read

	# `percent` divides by the same excluded-aware denominator `pending`
	# uses. Dividing by raw `total` (Unsubscribed rows included) let a blast
	# with an opt-out report `pending: 0` — nothing left to do — alongside
	# `percent < 100`, two numbers on the same payload contradicting each
	# other. Permanently-excluded rows can never succeed, so they belong in
	# neither side of the fraction.
	sendable_total = max(total - unsubscribed, 0)
	if sendable_total:
		percent = round(succeeded / sendable_total * 100, 1)
	else:
		# Every recipient permanently excluded: nothing is outstanding, so
		# report done rather than a stuck 0 that `pending: 0` contradicts.
		percent = 100.0 if total else 0

	return {
		"total": total,
		"queued": queued,
		"sent": sent,
		"delivered": delivered,
		"read": read,
		"failed": failed,
		"unsubscribed": unsubscribed,
		"pending": max(total - attempted, 0),
		"retry_count": doc.retry_count or 0,
		"is_paused": bool(doc.is_paused),
		"percent": percent,
	}


# ── Helpers ──────────────────────────────────────────────────────────────


def _parse_recipient_data(recipient: dict) -> dict:
	"""Parse recipient_data JSON string into a dict, merging the built-in
	recipient fields so variable mappings can target `recipient_name`,
	`first_name`, `mobile_number`, and `email_address` alongside imported CSV columns."""
	data = {}
	raw = recipient.get("recipient_data")
	if raw:
		try:
			data = json.loads(raw) if isinstance(raw, str) else raw
		except (json.JSONDecodeError, TypeError):
			pass

	if not isinstance(data, dict):
		data = {}

	name = recipient.get("recipient_name") or recipient.get("full_name") or recipient.get("name")
	if name and "recipient_name" not in data:
		data["recipient_name"] = str(name).strip()
	if name:
		name_parts = str(name).strip().split()
		if name_parts and "first_name" not in data:
			data["first_name"] = name_parts[0]

	mobile = recipient.get("mobile_number") or recipient.get("phone_e164") or recipient.get("phone")
	if mobile and "mobile_number" not in data:
		data["mobile_number"] = str(mobile).strip()

	email = recipient.get("email_address") or recipient.get("email")
	if email and "email_address" not in data:
		data["email_address"] = str(email).strip()

	return data


def _ensure_lead_for_bulk_recipient(phone: str | None, recipient_name: str | None, bulk_doc) -> str | None:
	"""Ensures a CRM Lead exists for the broadcast recipient and links handle & conversation.
	Uses recipient_name if present, otherwise falls back to phone number."""
	if not phone:
		return None

	try:
		from custom_crm.api.v1.lead import find_existing_party
		from custom_crm.utils.lead_factory import create_lead_for_source

		from msuite_inbox.inbox.services.outbound import _upsert_handle

		handle = _upsert_handle("WhatsApp", phone)

		name_clean = (recipient_name or "").strip()
		phone_clean = (handle.platform_handle or "").lstrip("+")

		# Update display name on handle if provided and handle has generic/empty name
		if name_clean and (not handle.display_name or handle.display_name == handle.platform_handle):
			handle.db_set("display_name", name_clean)

		# If handle already linked to a CRM party, return it
		if handle.crm_party:
			return handle.crm_party

		# Check DB for existing Lead / Contact / Deal by phone
		match = find_existing_party(
			phone=phone_clean or None,
			priority=("Contact", "CRM Deal", "CRM Lead"),
			skip_user_contacts=True,
		)

		if match:
			party_type, party_name = match
			handle.db_set("crm_party", party_name)
			handle.db_set("crm_party_type", party_type)
			return party_name

		# Create new CRM Lead: use recipient_name if provided, otherwise phone number
		lead_name_input = name_clean if name_clean else (handle.platform_handle or phone_clean)
		campaign_name = getattr(bulk_doc, "campaign", None) or ""

		extra_fields = {}
		if campaign_name:
			extra_fields["marketing_campaign"] = campaign_name

		# Resolve Organization linked to the sending WhatsApp Account
		organization = None
		if getattr(bulk_doc, "whatsapp_account", None):
			organization = frappe.db.get_value(
				"WhatsApp Account", bulk_doc.whatsapp_account, "crm_organization"
			)

		source = "WhatsApp Template"
		if not frappe.db.exists("CRM Lead Source", source):
			try:
				s_doc = frappe.get_doc({"doctype": "CRM Lead Source", "source_name": source})
				s_doc.flags.ignore_permissions = True
				s_doc.insert()
			except Exception:
				pass

		new_lead_name = create_lead_for_source(
			source=source,
			full_name=lead_name_input,
			mobile_no=phone_clean or None,
			phone=phone_clean or None,
			organization=organization or None,
			extra_fields=extra_fields or None,
			caller_verified_auth=True,  # internal helper called only from this file's own bulk WhatsApp send dispatch flow (permission-checked in TASK-2.3), never directly externally triggered
		)

		# Link handle to the new lead
		handle.db_set("crm_party", new_lead_name)
		handle.db_set("crm_party_type", "CRM Lead")

		return new_lead_name
	except Exception as e:
		frappe.logger("bulk_whatsapp").warning(f"Failed to auto-create lead for bulk recipient {phone}: {e}")
		return None
