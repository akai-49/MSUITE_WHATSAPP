"""
Bulk WhatsApp Message scheduler — the 5-minute cron entry point wired
into `hooks.py`. Pure plumbing; orchestration lives in
`services/bulk_send_service.py` and the doctype's own queue methods.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint, get_datetime, now_datetime

BULK_MESSAGE_DOCTYPE = "Bulk WhatsApp Message"


def schedule_bulk_messages() -> None:
	"""
	Background job: process queued bulk messages.

	Called by scheduler. Checks for Scheduled messages whose time has arrived,
	and updates status of completed/failed campaigns.

	Gated on the parent Marketing Campaign's status (LEFT JOIN, same
	pattern as Social Post's `dispatch_due_posts`) — a blast under a
	Paused or Draft umbrella must not auto-fire just because its own
	scheduled_time passed. Standalone blasts (no parent) are unaffected.
	"""
	scheduled = frappe.db.sql(
		"""
        SELECT bw.name, bw.scheduled_time
        FROM `tabBulk WhatsApp Message` bw
        LEFT JOIN `tabMarketing Campaign` parent_c ON parent_c.name = bw.campaign
        WHERE bw.status = 'Scheduled'
          AND bw.docstatus = 1
          AND (parent_c.name IS NULL OR parent_c.status = 'Active')
    """,
		as_dict=True,
	)
	for bulk in scheduled:
		if bulk.scheduled_time and get_datetime(bulk.scheduled_time) <= now_datetime():
			doc = frappe.get_doc(BULK_MESSAGE_DOCTYPE, bulk.name)
			doc.db_set("status", "Queued")
			doc.queue_messages()

	queued = frappe.get_all(
		BULK_MESSAGE_DOCTYPE,
		filters={"status": ["in", ["Queued", "In Progress", "Partially Failed"]], "docstatus": 1},
		fields=["name", "recipient_count", "sent_count", "is_paused"],
	)

	# Auto-retry ecosystem limit (131049) recipients whose 24h / 48h cooldown has elapsed
	retry_due_ecosystem_recipients()

	from msuite_whatsapp.services.bulk.bulk_send_service import latest_status_counts, requeue_deferred

	for bulk in queued:
		# Re-enqueue recipients parked by the rate governor (their phone's
		# 24h cap was hit when their job first ran). They re-check the cap
		# on dispatch, so this is at most one attempt per 5-minute tick.
		if not bulk.is_paused:
			requeue_deferred(bulk.name)

		# Failure count off each recipient's LATEST Channel Message — raw
		# row counts double-count recipients that failed and were retried.
		counts = latest_status_counts(bulk.name)
		failed = counts.get("failed", 0)
		sent = counts.get("sent", 0) + counts.get("delivered", 0) + counts.get("read", 0)
		retrying_cnt = counts.get("retrying", 0)
		# Recipients still at "queued" have no attempt under this blast yet
		# (not sent, not failed) — the blast is still sending (BUG-022 follow-up).
		pending_cnt = counts.get("queued", 0)

		# Check deferred items in redis
		try:
			deferred_count = frappe.cache().llen(f"wa_deferred|{bulk.name}") or 0
		except Exception:
			deferred_count = 0

		if deferred_count > 0 or retrying_cnt > 0 or pending_cnt > 0:
			continue

		total_attempted = max(sent, cint(bulk.sent_count)) + failed
		if total_attempted == 0:
			continue

		new_status = "Partially Failed" if failed > 0 else "Completed"
		frappe.db.set_value(BULK_MESSAGE_DOCTYPE, bulk.name, "status", new_status)


def retry_due_ecosystem_recipients() -> int:
	"""Auto-retry recipients parked in 'Retrying' due to Meta ecosystem limits (131049).

	Cooldown rules:
	  - Attempt 1 (retry_count = 1): retry after 24 hours
	  - Attempt 2 (retry_count = 2): retry after 48 hours
	"""
	from frappe.utils import add_to_date

	now = now_datetime()
	cutoff_24h = add_to_date(now, hours=-24)
	cutoff_48h = add_to_date(now, hours=-48)

	# 1. Fetch due individual recipients (parenttype == 'Bulk WhatsApp Message')
	individual_rows = frappe.db.sql(
		"""
		SELECT r.name, r.parent, r.mobile_number, r.recipient_name, r.recipient_data, r.retry_count, r.modified
		FROM `tabWhatsApp Recipient` r
		INNER JOIN `tabBulk WhatsApp Message` bw ON bw.name = r.parent
		WHERE r.parenttype = 'Bulk WhatsApp Message'
		  AND r.status = 'Retrying'
		  AND r.error_code = '131049'
		  AND bw.docstatus = 1
		  AND bw.is_paused = 0
		  AND (
		    (r.retry_count = 1 AND r.modified <= %s) OR
		    (r.retry_count = 2 AND r.modified <= %s)
		  )
		LIMIT 100
		""",
		(cutoff_24h, cutoff_48h),
		as_dict=True,
	)

	# 2. Fetch due list-backed recipients (parenttype == 'WhatsApp Recipient List')
	list_rows = frappe.db.sql(
		"""
		SELECT r.name, r.parent, r.mobile_number, r.recipient_name, r.recipient_data, r.retry_count, r.modified,
		       bw.name as bulk_name
		FROM `tabWhatsApp Recipient` r
		INNER JOIN `tabBulk WhatsApp Message` bw ON bw.recipient_list = r.parent AND bw.recipient_type = 'Recipient List'
		WHERE r.parenttype = 'WhatsApp Recipient List'
		  AND r.status = 'Retrying'
		  AND r.error_code = '131049'
		  AND bw.docstatus = 1
		  AND bw.is_paused = 0
		  AND bw.status IN ('Queued', 'In Progress', 'Partially Failed')
		  AND (
		    (r.retry_count = 1 AND r.modified <= %s) OR
		    (r.retry_count = 2 AND r.modified <= %s)
		  )
		LIMIT 100
		""",
		(cutoff_24h, cutoff_48h),
		as_dict=True,
	)

	requeued = 0
	for row in individual_rows:
		try:
			recipient_payload = {
				"mobile_number": row.mobile_number,
				"recipient_name": row.recipient_name,
				"recipient_data": row.recipient_data,
			}
			frappe.enqueue_doc(
				BULK_MESSAGE_DOCTYPE,
				row.parent,
				"create_single_message",
				queue="long",
				timeout=4000,
				recipient=recipient_payload,
			)
			requeued += 1
		except Exception:
			frappe.log_error(
				f"Failed to auto-retry ecosystem recipient {row.mobile_number} on {row.parent}",
				"Bulk WhatsApp Message",
			)

	for row in list_rows:
		try:
			recipient_payload = {
				"mobile_number": row.mobile_number,
				"recipient_name": row.recipient_name,
				"recipient_data": row.recipient_data,
			}
			frappe.enqueue_doc(
				BULK_MESSAGE_DOCTYPE,
				row.bulk_name,
				"create_single_message",
				queue="long",
				timeout=4000,
				recipient=recipient_payload,
			)
			requeued += 1
		except Exception:
			frappe.log_error(
				f"Failed to auto-retry ecosystem recipient {row.mobile_number} on {row.bulk_name}",
				"Bulk WhatsApp Message",
			)

	return requeued
