"""
WhatsApp's registration with the Campaign channel-adapter registry.

Moved here from `campaign/api/runner.py` (`_preview_whatsapp`,
`_whatsapp_firability`, `_run_whatsapp`, `_set_paused_flag_whatsapp`,
`_stop_whatsapp`) — Campaign's orchestrator must not contain WhatsApp-
specific lifecycle rules (Architecture Correction Rule 1).

Also the first place WhatsApp is treated as 1:N under a Campaign
(`Bulk WhatsApp Message.campaign`, added by
`patches.add_campaign_link_to_bulk_whatsapp_message`) instead of the
old single `Marketing Campaign.whatsapp_blast` Link — every function
here lists ALL broadcasts under the campaign, not just one.

Registered via `hooks.py`:
    campaign_channel_adapters = [..., "msuite_whatsapp.services.channels.campaign_adapter.ADAPTER", ...]
"""

from __future__ import annotations

import frappe

from msuite_whatsapp.services.bulk import bulk_channel

# Only pre-flight blasts can be cancelled cleanly. Queued / In Progress
# would orphan partial deliveries — Meta has no "stop blast" primitive.
_STOPPABLE_STATUSES = ("Draft", "Scheduled")
_PAUSEABLE_STATUSES = ("Queued", "In Progress")


def _rows(campaign: str) -> list[dict]:
	return frappe.get_all(
		"Bulk WhatsApp Message",
		filters={"campaign": campaign},
		fields=["name", "title", "status", "docstatus", "recipient_count", "is_paused", "scheduled_time"],
		order_by="modified desc",
	)


def preview(campaign: str) -> list[dict]:
	out = []
	for r in _rows(campaign):
		ready, reason = _firability(r)
		out.append(
			{
				"name": r.name,
				"title": r.title or r.name,
				"status": r.status,
				"recipients": r.recipient_count or 0,
				"ready": ready,
				"reason": reason,
			}
		)
	return out


def _firability(row) -> tuple[bool, str]:
	if row.docstatus == 2:
		return False, "Blast was cancelled"
	if row.status in ("Queued", "In Progress", "Completed", "Failed", "Partially Failed"):
		return False, f"Already {row.status}"
	if not (row.recipient_count or 0):
		return False, "No recipients — open the Blast and add some"
	return True, ""


def run(name: str) -> dict:
	blast = frappe.get_doc("Bulk WhatsApp Message", name)
	recipients = blast.recipient_count or 0
	if blast.docstatus == 0:
		blast.submit()
	else:
		blast.db_set("status", "Queued", update_modified=True)
		blast.queue_messages()
	return {"outcome": "fired", "message": f"Queued {recipients} recipient(s)"}


def pause(campaign: str) -> list[dict]:
	out = []
	for r in _rows(campaign):
		base = {"name": r.name, "status": r.status}
		if r.status not in _PAUSEABLE_STATUSES:
			out.append(
				{**base, "outcome": "skipped", "reason": f"Status is {r.status} — pause has no effect."}
			)
			continue
		if r.is_paused:
			out.append({**base, "outcome": "skipped", "reason": "Already paused."})
			continue
		try:
			frappe.get_doc("Bulk WhatsApp Message", r.name).pause_sending()
			out.append({**base, "outcome": "fired", "message": "New sends will skip until resumed."})
		except Exception as e:
			out.append({**base, "outcome": "failed", "message": str(e)[:200]})
	return out


def resume(campaign: str) -> list[dict]:
	out = []
	for r in _rows(campaign):
		base = {"name": r.name, "status": r.status}
		if r.status not in _PAUSEABLE_STATUSES:
			out.append(
				{**base, "outcome": "skipped", "reason": f"Status is {r.status} — resume has no effect."}
			)
			continue
		if not r.is_paused:
			out.append({**base, "outcome": "skipped", "reason": "Already resumed."})
			continue
		try:
			frappe.get_doc("Bulk WhatsApp Message", r.name).resume_sending()
			out.append(
				{
					**base,
					"outcome": "fired",
					"message": "New sends will dispatch normally; pending recipients re-queued.",
				}
			)
		except Exception as e:
			out.append({**base, "outcome": "failed", "message": str(e)[:200]})
	return out


def stop(campaign: str) -> list[dict]:
	out = []
	for r in _rows(campaign):
		base = {"name": r.name, "status": r.status}
		if r.status not in _STOPPABLE_STATUSES:
			out.append(
				{
					**base,
					"outcome": "skipped",
					"reason": f"Blast is {r.status} — in-flight sends can't be aborted.",
				}
			)
			continue
		try:
			blast = frappe.get_doc("Bulk WhatsApp Message", r.name)
			if blast.docstatus == 1:
				blast.cancel()
			else:
				blast.db_set("status", "Draft", update_modified=True)
			out.append({**base, "outcome": "fired", "message": "Cancelled."})
		except Exception as e:
			out.append({**base, "outcome": "failed", "message": str(e)[:200]})
	return out


def rollup(campaign: str, days: int) -> dict:
	from msuite_whatsapp.api.v1.app.analytics_query import campaign_rollup

	return campaign_rollup(campaign, days)


def refresh(campaign: str) -> dict:
	from msuite_whatsapp.services.analytics.sync import refresh_campaign

	return refresh_campaign(campaign)


ADAPTER = {
	"key": "whatsapp",
	"label": "WhatsApp",
	"preview": preview,
	"run": run,
	"pause": pause,
	"resume": resume,
	"stop": stop,
	"rollup": rollup,
	"refresh": refresh,
	"bulk_doctype": "Bulk WhatsApp Message",
	"row_parent": bulk_channel.row_parent,
	"manifest_header": bulk_channel.manifest_header,
	"manifest_row": bulk_channel.manifest_row,
	"send_one": bulk_channel.send_one,
	"sync_secret": bulk_channel.sync_secret,
	"record_outbound": bulk_channel.record_outbound,
}
