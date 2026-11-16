"""
Bulk WhatsApp Message API — Vue SPA-facing CRUD.

Relocated from `api/v1/whatsapp/crud.py` (see WHATSAPP_REFACTOR_PLAN.md §9).
The dotted path `msuite_whatsapp.api.v1.app.crud.*` is preserved via
a re-export shim in that module since the SPA calls it by that exact path.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint

from msuite_whatsapp.services.plans.plan_enforcer import check_feature_or_throw
from msuite_whatsapp.services.analytics import broadcast_metrics
from msuite_whatsapp.services.permissions.checks import (
	check_create,
	check_delete,
	check_read,
	check_write,
	safe_doc_dict,
)

BULK_MESSAGE_DOCTYPE = "Bulk WhatsApp Message"


@frappe.whitelist()
def get_bulk_metrics() -> dict:
	check_read(BULK_MESSAGE_DOCTYPE)

	total = frappe.db.count(BULK_MESSAGE_DOCTYPE)
	draft = frappe.db.count(BULK_MESSAGE_DOCTYPE, {"docstatus": 0, "status": "Draft"})
	scheduled = frappe.db.count(BULK_MESSAGE_DOCTYPE, {"status": "Scheduled"})
	in_progress = frappe.db.count(BULK_MESSAGE_DOCTYPE, {"status": ["in", ["Queued", "In Progress"]]})
	completed = frappe.db.count(BULK_MESSAGE_DOCTYPE, {"status": "Completed"})
	partially_failed = frappe.db.count(BULK_MESSAGE_DOCTYPE, {"status": "Partially Failed"})

	return {
		"total": total,
		"draft": draft,
		"scheduled": scheduled,
		"inProgress": in_progress,
		"completed": completed,
		"partiallyFailed": partially_failed,
	}


@frappe.whitelist()
def list_bulk_messages(filters: str = "[]", search: str = "", limit: int = 100) -> list:
	check_read(BULK_MESSAGE_DOCTYPE)

	parsed_filters = json.loads(filters or "[]")
	if search and search.strip():
		parsed_filters.append(["title", "like", f"%{search.strip()}%"])

	rows = frappe.get_all(
		BULK_MESSAGE_DOCTYPE,
		fields=[
			"name",
			"title",
			"status",
			"template",
			"recipient_type",
			"recipient_list",
			"recipient_count",
			"sent_count",
			"scheduled_time",
			"is_paused",
			"owner",
			"creation",
			"modified",
			"docstatus",
		],
		filters=parsed_filters,
		order_by="modified desc",
		limit=limit,
	)

	if rows:
		names = [r.name for r in rows]
		failed_counts = dict(
			frappe.db.sql(
				"""
            SELECT reference_name, COUNT(*)
            FROM `tabChannel Message`
            WHERE reference_doctype = %s AND reference_name IN %s AND status = 'failed'
            GROUP BY reference_name
            """,
				(BULK_MESSAGE_DOCTYPE, names),
			)
		)
		sent_counts = dict(
			frappe.db.sql(
				"""
            SELECT reference_name, COUNT(*)
            FROM `tabChannel Message`
            WHERE reference_doctype = %s AND reference_name IN %s AND status != 'failed'
            GROUP BY reference_name
            """,
				(BULK_MESSAGE_DOCTYPE, names),
			)
		)

		rec_list_names = list({r.recipient_list for r in rows if r.recipient_type == "Recipient List" and r.recipient_list})
		rec_list_counts = {}
		if rec_list_names:
			rec_list_counts = dict(
				frappe.db.sql(
					"""
                SELECT parent, COUNT(*)
                FROM `tabWhatsApp Recipient`
                WHERE parenttype = 'WhatsApp Recipient List' AND parent IN %s
                GROUP BY parent
                """,
					(rec_list_names,),
				)
			)

		# Blasts that own their rows (Individual, or a Recipient List snapshotted
		# per blast since audit H11) are counted off those rows.
		own_counts = dict(
			frappe.db.sql(
				"""
            SELECT parent, COUNT(*)
            FROM `tabWhatsApp Recipient`
            WHERE parenttype = %s AND parent IN %s
            GROUP BY parent
            """,
				(BULK_MESSAGE_DOCTYPE, names),
			)
		)

		for r in rows:
			r["failed_count"] = failed_counts.get(r.name, 0)
			actual_sent = max(sent_counts.get(r.name, 0), r.get("sent_count") or 0)
			r["sent_count"] = actual_sent
			legacy_list = r.recipient_type == "Recipient List" and r.name not in own_counts

			if r.name in own_counts:
				r["recipient_count"] = own_counts[r.name]
			elif r.recipient_type == "Recipient List" and r.recipient_list in rec_list_counts:
				r["recipient_count"] = rec_list_counts[r.recipient_list]
			elif r.recipient_type != "Recipient List":
				# Individual broadcasts: use stored count (set by validate_recipients)
				r["recipient_count"] = r.get("recipient_count") or 0

			total_attempted = (r.get("sent_count") or 0) + r["failed_count"]

			# Reconcile status: Settle In Progress / Queued broadcasts if all sends finished
			if r.docstatus == 1 and r.status in ("In Progress", "Queued", "Scheduled") and not r.is_paused:
				if total_attempted > 0:
					if total_attempted >= (r.get("recipient_count") or 0) or legacy_list:
						new_status = "Partially Failed" if r["failed_count"] > 0 else "Completed"
						if r.status != new_status:
							frappe.db.set_value(BULK_MESSAGE_DOCTYPE, r.name, "status", new_status, update_modified=False)
							r["status"] = new_status

	return rows


@frappe.whitelist()
def get_bulk_message(name: str) -> dict:
	check_read(BULK_MESSAGE_DOCTYPE, name)
	doc = frappe.get_doc(BULK_MESSAGE_DOCTYPE, name)
	doc_dict = doc.as_dict()

	failed_count = frappe.db.count(
		"Channel Message",
		{"reference_doctype": BULK_MESSAGE_DOCTYPE, "reference_name": name, "status": "failed"},
	)
	sent_count = frappe.db.count(
		"Channel Message",
		{"reference_doctype": BULK_MESSAGE_DOCTYPE, "reference_name": name, "status": ["!=", "failed"]},
	)
	doc_dict["failed_count"] = failed_count
	actual_sent = max(sent_count, doc_dict.get("sent_count") or 0)
	doc_dict["sent_count"] = actual_sent

	# Compute true recipient count from the authoritative source — never
	# inflate it from delivery-attempt totals (retries, re-sends produce
	# multiple Channel Message rows per recipient).
	from msuite_whatsapp.services.bulk.bulk_send_service import row_parent

	rp_parent, rp_type = row_parent(doc)
	doc_dict["recipient_count"] = frappe.db.count("WhatsApp Recipient", {"parent": rp_parent, "parenttype": rp_type})

	total_attempted = actual_sent + failed_count

	if doc.docstatus == 1 and doc.status in ("In Progress", "Queued", "Scheduled") and not doc.is_paused:
		if total_attempted > 0:
			legacy_list = doc.recipient_type == "Recipient List" and rp_type != BULK_MESSAGE_DOCTYPE
			if total_attempted >= (doc_dict.get("recipient_count") or 0) or legacy_list:
				new_status = "Partially Failed" if failed_count > 0 else "Completed"
				if doc.status != new_status:
					frappe.db.set_value(BULK_MESSAGE_DOCTYPE, name, "status", new_status, update_modified=False)
					doc_dict["status"] = new_status

	return doc_dict


@frappe.whitelist()
def insert_bulk_message(doc: str, submit: int = 0, name: str = "") -> dict:
	"""Create a Bulk WhatsApp Message; with `submit=1` also submit it so
	`on_submit` fires (queue immediately, or park as Scheduled).

	`status` and `sent_count` are server-managed — a client used to be
	able to write status="Queued" onto a docstatus-0 draft, producing a
	broadcast that *looked* queued but could never send (the whole send
	pipeline hangs off on_submit / docstatus 1).

	With `name` (a draft this wizard saved earlier) the draft is updated in
	place instead of inserting a new record — repeated "Save Draft" clicks
	and the final send then all land on one broadcast (BUG-021).
	"""
	data = json.loads(doc or "{}")
	data = safe_doc_dict(data, BULK_MESSAGE_DOCTYPE)
	data.pop("status", None)
	data.pop("sent_count", None)
	data.pop("is_paused", None)
	data.pop("retry_count", None)
	if name:
		check_write(BULK_MESSAGE_DOCTYPE, name)
		db_doc = frappe.get_doc(BULK_MESSAGE_DOCTYPE, name)
		if db_doc.docstatus != 0:
			frappe.throw(_("This broadcast has already been sent or scheduled, so it can't be changed."))
		db_doc.update(data)
	else:
		check_create(BULK_MESSAGE_DOCTYPE)
		db_doc = frappe.get_doc(data)
	if not cint(submit):
		# A draft can be saved from any wizard step, before an audience or
		# template is picked; completeness is enforced on submit.
		db_doc.flags.partial_draft = True
		db_doc.flags.ignore_mandatory = True
	if name:
		db_doc.save()
	else:
		db_doc.insert()
	if cint(submit):
		db_doc.submit()
	frappe.db.commit()
	return db_doc.as_dict()


@frappe.whitelist()
def delete_bulk_message(name: str):
	check_delete(BULK_MESSAGE_DOCTYPE, name)
	doc = frappe.get_doc(BULK_MESSAGE_DOCTYPE, name)
	if doc.docstatus == 1:
		frappe.db.set_value(BULK_MESSAGE_DOCTYPE, name, "docstatus", 2)
	frappe.delete_doc(BULK_MESSAGE_DOCTYPE, name, force=True)
	frappe.db.commit()
	return {"status": "success"}


@frappe.whitelist()
def bulk_delete_bulk_messages(names: str | list) -> dict:
	"""Batch delete multiple bulk whatsapp messages."""
	name_list = json.loads(names) if isinstance(names, str) else (names or [])
	deleted, failed = [], []
	for name in name_list:
		if not frappe.has_permission(BULK_MESSAGE_DOCTYPE, "delete", doc=name):
			failed.append({"name": name, "reason": "No delete permission"})
			continue
		try:
			doc = frappe.get_doc(BULK_MESSAGE_DOCTYPE, name)
			if doc.docstatus == 1:
				frappe.db.set_value(BULK_MESSAGE_DOCTYPE, name, "docstatus", 2)
			frappe.delete_doc(BULK_MESSAGE_DOCTYPE, name, force=True)
			deleted.append(name)
		except Exception as e:
			frappe.log_error(title="bulk_delete_bulk_messages", message=str(e))
			failed.append({"name": name, "reason": str(e)})
	frappe.db.commit()
	return {"deleted": deleted, "failed": failed}


@frappe.whitelist()
def get_bulk_message_logs(
	bulk_message: str, status: str = "", search: str = "", start: int = 0, page_length: int = 50
) -> dict:
	check_read(BULK_MESSAGE_DOCTYPE, bulk_message)

	# Determine parent name & parenttype in tabWhatsApp Recipient
	from msuite_whatsapp.services.bulk.bulk_send_service import row_parent

	recipient_parent, parenttype = row_parent(bulk_message)

	query_filters = ["wr.parenttype = %(parenttype)s", "wr.parent = %(recipient_parent)s"]
	query_params = {
		"doctype": BULK_MESSAGE_DOCTYPE,
		"bulk_message": bulk_message,
		"parenttype": parenttype,
		"recipient_parent": recipient_parent or "",
	}

	if status and status.strip() and status != "all":
		query_filters.append("LOWER(COALESCE(cm.status, wr.status, 'queued')) = %(status)s")
		query_params["status"] = status.strip().lower()

	if search and search.strip():
		query_filters.append(
			"(wr.mobile_number LIKE %(search)s OR wr.recipient_name LIKE %(search)s OR ch.display_name LIKE %(search)s)"
		)
		query_params["search"] = f"%{search.strip()}%"

	where_clause = " AND ".join(query_filters)

	# Count query
	count_query = f"""
        SELECT COUNT(*)
        FROM `tabWhatsApp Recipient` wr
        LEFT JOIN `tabChannel Handle` ch ON (wr.mobile_number = ch.platform_handle OR REPLACE(wr.mobile_number, '+', '') = REPLACE(ch.platform_handle, '+', ''))
        LEFT JOIN `tabChannel Message` cm ON cm.channel_handle = ch.name
            AND cm.reference_doctype = %(doctype)s AND cm.reference_name = %(bulk_message)s
        WHERE {where_clause}
    """
	total = frappe.db.sql(count_query, query_params)[0][0]

	# Data query
	data_query = f"""
        SELECT
            COALESCE(cm.name, wr.name) AS name,
            wr.mobile_number AS mobile_number,
            COALESCE(wr.recipient_name, ch.display_name, wr.mobile_number) AS recipient_name,
            LOWER(COALESCE(cm.status, wr.status, 'queued')) AS status,
            cm.status_error,
            cm.failure_reason,
            COALESCE(cm.modified, wr.modified) AS modified
        FROM `tabWhatsApp Recipient` wr
        LEFT JOIN `tabChannel Handle` ch ON (wr.mobile_number = ch.platform_handle OR REPLACE(wr.mobile_number, '+', '') = REPLACE(ch.platform_handle, '+', ''))
        LEFT JOIN `tabChannel Message` cm ON cm.channel_handle = ch.name
            AND cm.reference_doctype = %(doctype)s AND cm.reference_name = %(bulk_message)s
        WHERE {where_clause}
        ORDER BY modified DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """
	query_params["limit"] = cint(page_length)
	query_params["offset"] = cint(start)

	rows = frappe.db.sql(data_query, query_params, as_dict=True)

	return {"rows": rows, "total": total}


@frappe.whitelist()
def get_bulk_failure_summary(bulk_message: str) -> dict:
	"""Return aggregated failure reasons, error codes, and retryable counts for a Bulk Message campaign."""
	check_read(BULK_MESSAGE_DOCTYPE, bulk_message)

	from msuite_whatsapp.services.bulk.bulk_send_service import row_parent

	doc = frappe.get_doc(BULK_MESSAGE_DOCTYPE, bulk_message)
	parent_name, parent_dt = row_parent(doc)

	rows = frappe.db.sql(
		"""
		SELECT error_code, failure_reason, is_retryable, COUNT(*) AS count
		FROM `tabWhatsApp Recipient`
		WHERE parenttype = %s AND parent = %s AND status IN ('Failed', 'Retrying')
		GROUP BY error_code, failure_reason, is_retryable
		ORDER BY count DESC
		""",
		(parent_dt, parent_name),
		as_dict=True,
	)

	total_failed = sum(r.get("count", 0) for r in rows)
	retryable_count = sum(r.get("count", 0) for r in rows if r.get("is_retryable"))

	return {
		"bulk_message": bulk_message,
		"total_failed": total_failed,
		"retryable_count": retryable_count,
		"non_retryable_count": total_failed - retryable_count,
		"breakdown": rows,
	}


@frappe.whitelist()
def get_broadcast_metrics(bulk_message: str) -> dict:
	"""Sent/Delivered/Read/Failed, route breakdowns and click/conversion attribution of one broadcast.

	Args:
	    bulk_message: name of the Bulk WhatsApp Message.

	Returns: see `analytics.broadcast_metrics.get_broadcast_metrics`.

	Raises:
	    frappe.PermissionError: no read permission on the broadcast (checked first) or the
	        analytics feature is off for the plan.
	    frappe.DoesNotExistError: unknown name.
	"""
	# perm: read permission on the broadcast, then the analytics plan feature
	check_read(BULK_MESSAGE_DOCTYPE, bulk_message)
	check_feature_or_throw("analytics", "Analytics", product="WA")
	return broadcast_metrics.get_broadcast_metrics(bulk_message)


@frappe.whitelist()
def get_campaign_metrics(campaign: str) -> dict:
	"""Metrics summed over the Bulk WhatsApp Messages of a Marketing Campaign.

	Args:
	    campaign: name of the Marketing Campaign.

	Returns: see `analytics.broadcast_metrics.get_campaign_metrics` (only broadcasts the caller can
	    read are included).

	Raises:
	    frappe.PermissionError: no read permission on the campaign (checked first) or the analytics
	        feature is off for the plan.
	"""
	# perm: read permission on the campaign, then the analytics plan feature
	check_read("Marketing Campaign", campaign)
	check_feature_or_throw("analytics", "Analytics", product="WA")
	return broadcast_metrics.get_campaign_metrics(campaign)
