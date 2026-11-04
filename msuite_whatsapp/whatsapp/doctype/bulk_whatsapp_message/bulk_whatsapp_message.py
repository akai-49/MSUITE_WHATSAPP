"""
Bulk WhatsApp Message — controller.

Workflow:
  1. User selects template + recipients (individual or from a list)
  2. Maps template variables via the unified mapping UI
  3. Submits → status moves to Queued (or Scheduled if future time set)
  4. Background jobs send to each recipient through the Inbox pipeline
  5. Status updates: In Progress → Completed / Partially Failed

Lifecycle hooks and validation only — queueing, sending, pause/resume/retry
orchestration lives in `services/bulk_send_service.py` (see
WHATSAPP_REFACTOR_PLAN.md §5). Thin delegating methods are kept on the
doctype since they're called via `frappe.enqueue_doc` (which dispatches
to a doc method by name) and by the whitelisted wrappers in
`utils/bulk_messaging.py` that the SPA calls directly.
"""

import frappe
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import get_datetime, now_datetime

from msuite_whatsapp.services.domain import BulkMessageStatus
from msuite_whatsapp.services.bulk import bulk_send_service
from msuite_whatsapp.services.validators import bulk_message_validator


class BulkWhatsAppMessage(Document):
	def autoname(self):
		self.name = make_autoname("BULK-WA-.YYYY.-.#####")

	def before_insert(self):
		"""A new blast (incl. Amend / Duplicate, which copy child rows) must
		start with clean per-recipient state. Since audit H11 a Recipient-List
		blast snapshots the list into these rows on first queue; copied rows
		would make that snapshot skip and carry the old blast's "Sent"/"Failed"
		statuses, so nothing would be re-sent."""
		if self.recipient_type == "Recipient List" and self.recipient_list:
			self.set("recipients", [])
			return
		for row in self.recipients or []:
			row.status = ""
			row.error_code = ""
			row.failure_reason = ""
			row.is_retryable = 0
			row.retry_count = 0

	def validate(self):
		# Wizard "Save Draft" from the Brief/Audience steps (flag set by
		# insert_bulk_message) may have no audience or template yet. All
		# checks run again when the broadcast is sent/scheduled.
		if self.flags.partial_draft:
			self.recipient_count = len(self.recipients or [])
			return
		self.recipient_count = bulk_message_validator.validate_recipients(self)
		bulk_message_validator.validate_mpm_configuration(self)
		bulk_message_validator.validate_carousel_configuration(self)
		bulk_message_validator.validate_template_approved(self)
		bulk_message_validator.validate_offer_options(self)

	def after_insert(self):
		# Active-campaign auto-discovery — see Social Post's identical
		# hook for why this is a log-only seam, not a second dispatcher.
		from msuite_campaigns.campaign.services.relationships import register_with_campaign

		register_with_campaign("Bulk WhatsApp Message", self.name, self.campaign)

	def on_update(self):
		# `campaign` is commonly set AFTER creation (the marketer picks
		# a blast first, then links it via `link_whatsapp_blast`) —
		# re-check on every update, not just at insert time.
		from msuite_campaigns.campaign.services.relationships import register_with_campaign

		register_with_campaign("Bulk WhatsApp Message", self.name, self.campaign)

	def on_submit(self):
		"""Queue messages or schedule for later."""
		if self.scheduled_time and get_datetime(self.scheduled_time) > now_datetime():
			frappe.db.set_value(self.doctype, self.name, "status", BulkMessageStatus.SCHEDULED, update_modified=False)
			self.status = BulkMessageStatus.SCHEDULED
			return

		frappe.db.set_value(self.doctype, self.name, "status", BulkMessageStatus.QUEUED, update_modified=False)
		self.status = BulkMessageStatus.QUEUED
		self.queue_messages()

	def on_cancel(self):
		# Frappe's cancel() only flips docstatus — without this, a
		# Scheduled blast cancelled before it ever ran (e.g. via the
		# campaign adapter's stop()) keeps showing status "Scheduled"
		# forever, indistinguishable from one still pending.
		frappe.db.set_value(
			self.doctype,
			self.name,
			{"status": BulkMessageStatus.CANCELLED, "is_paused": 1},
			update_modified=False,
		)
		self.status = BulkMessageStatus.CANCELLED
		self.is_paused = 1

	def queue_messages(self):
		bulk_send_service.queue_messages(self)

	def create_single_message(self, recipient):
		"""Background-job entry point — see bulk_send_service for the
		full pause-gate / rate-gate / send / completion-tracking flow."""
		bulk_send_service.create_single_message(self, recipient)

	@frappe.whitelist()
	def pause_sending(self):
		"""Pause this broadcast. Recipients not yet attempted are skipped
		by `create_single_message` until `resume_sending` is called."""
		self.check_permission("write")  # audit H8: run_doc_method only checks read
		current_status = frappe.db.get_value(self.doctype, self.name, "status")
		if current_status not in (BulkMessageStatus.QUEUED, BulkMessageStatus.IN_PROGRESS):
			frappe.throw(frappe._("Only Queued or In Progress broadcasts can be paused."))
		frappe.db.set_value(self.doctype, self.name, "is_paused", 1, update_modified=False)
		frappe.db.commit()
		self.is_paused = 1
		frappe.msgprint(frappe._("Broadcast paused."), alert=True)

	@frappe.whitelist()
	def resume_sending(self):
		"""Resume a paused broadcast and re-enqueue any recipient that was
		skipped while paused."""
		self.check_permission("write")  # audit H8: run_doc_method only checks read
		res = frappe.db.get_value(self.doctype, self.name, ["status", "is_paused"], as_dict=True)
		if not res:
			frappe.throw(frappe._("Broadcast {0} not found.").format(self.name))
		if res.status == BulkMessageStatus.CANCELLED:
			frappe.throw(frappe._("This broadcast was cancelled and cannot be resumed."))
		if not res.is_paused:
			frappe.msgprint(frappe._("This broadcast is not paused."), alert=True)
			return
		frappe.db.set_value(self.doctype, self.name, "is_paused", 0, update_modified=False)
		frappe.db.commit()
		self.is_paused = 0
		requeued = bulk_send_service.requeue_unattempted(self)
		frappe.msgprint(
			frappe._("Broadcast resumed. {0} pending recipient(s) re-queued.").format(requeued),
			alert=True,
		)

	@frappe.whitelist()
	def cancel_sending(self):
		"""Stop a broadcast permanently. Already-enqueued jobs for
		not-yet-attempted recipients will see `is_paused` and no-op."""
		self.check_permission("write")  # audit H8: run_doc_method only checks read
		current_status = frappe.db.get_value(self.doctype, self.name, "status")
		if current_status in (BulkMessageStatus.COMPLETED, BulkMessageStatus.CANCELLED):
			frappe.throw(frappe._("This broadcast has already finished and cannot be cancelled."))
		frappe.db.set_value(
			self.doctype,
			self.name,
			{"is_paused": 1, "status": BulkMessageStatus.CANCELLED},
			update_modified=False,
		)
		frappe.db.commit()
		self.is_paused = 1
		self.status = BulkMessageStatus.CANCELLED
		bulk_send_service.clear_deferred(self.name)
		frappe.msgprint(frappe._("Broadcast cancelled."), alert=True)

	@frappe.whitelist()
	def retry_failed(self):
		"""Re-send every previously-failed recipient through the real
		outbound pipeline."""
		self.check_permission("write")  # audit H8: run_doc_method only checks read
		return bulk_send_service.retry_failed(self)

	def get_progress(self):
		"""Get delivery progress stats — counted off Channel Message rows."""
		return bulk_send_service.get_progress(self)
