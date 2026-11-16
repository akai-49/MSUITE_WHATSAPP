"""What the campaign bulk engines ask WhatsApp for, through this channel's campaign adapter."""

from __future__ import annotations

import frappe
from frappe import _

from msuite_campaigns.aws_pipeline.manifest import _dynamo_campaign_id
from msuite_whatsapp.constants import GRAPH_API_URL, GRAPH_API_VERSION
from msuite_whatsapp.services.bulk.bulk_send_service import row_parent  # noqa: F401


def manifest_header(doc) -> dict:
	"""Everything WhatsAppSenderLambda needs to make the POST — and nothing
	that would let it build a message body.

	The body is assembled per recipient by `_wa_row` using Frappe's own
	`_build_send_body`. See that function's note: porting 450 lines of Meta
	payload assembly into Lambda is the largest drift risk in this project,
	and it buys nothing the exporter cannot do.

	The Meta token is not here and is not named here — the provider injects
	its Secrets Manager id into the SQS trigger.
	"""
	from msuite_whatsapp.queries import account_repository as accounts

	account = accounts.get_account_doc(doc.whatsapp_account)

	return {
		"v": 1,
		"channel": "whatsapp",
		"bulk_doctype": "Bulk WhatsApp Message",
		"bulk_doc_name": doc.name,
		"campaign_id": _dynamo_campaign_id(doc, "whatsapp"),
		"base_url": GRAPH_API_URL,
		"version": GRAPH_API_VERSION,
		"phone_number_id": accounts.get_phone_number_id(account, "outgoing"),
	}


def manifest_row(bulk_doc, row) -> dict:
	"""One recipient, carrying the fully-built Meta message body.

	`_build_send_body` is the same function the Standard path calls, so the
	two engines put byte-identical JSON on the wire. A body is ~1-3 KB, well
	inside SQS's 256 KB per-message limit.
	"""
	from msuite_whatsapp.services.channels.inbox_channel import _build_send_body
	from msuite_whatsapp.services.bulk import bulk_send_service as wa

	row = row if isinstance(row, dict) else row.as_dict()
	number = (row.get("mobile_number") or "").strip()

	recipient_data = wa._parse_recipient_data(row)
	body_param = wa.build_body_param(bulk_doc, recipient_data) if bulk_doc.template_variables else None

	payload = {
		"type": "template",
		"template": bulk_doc.template,
		"body_param": body_param,
		"attach": bulk_doc.attach or None,
		"whatsapp_account": bulk_doc.whatsapp_account or None,
		"sender_type": "Bot",
		"thumbnail_product_retailer_id": bulk_doc.get("thumbnail_product_retailer_id") or None,
	}

	mpm_action = wa.get_mpm_action_json(bulk_doc)
	if mpm_action:
		payload["product_catalog_json"] = mpm_action

	if bulk_doc.get("is_carousel_template") and bulk_doc.get("carousel_catalog"):
		payload["catalog"] = bulk_doc.carousel_catalog
		payload["product_retailer_ids"] = list(
			dict.fromkeys(r.item_code for r in (bulk_doc.product_ids or []) if r.item_code)
		)[:10]

	meta_body = _build_send_body(number, payload)
	if meta_body is None:
		frappe.throw(
			_("Could not build a WhatsApp message body for {0} — check the template on {1}.").format(
				number, bulk_doc.name
			)
		)

	return {
		"recipient_id": row.get("name"),
		"to": number,
		"meta_body": meta_body,
		"attempt_count": 0,
	}


def send_one(doc, row: dict) -> None:
	from msuite_whatsapp.services.bulk import bulk_send_service

	bulk_send_service.create_single_message(
		doc,
		{
			"name": row.get("name"),  # lets the engine update exactly this row
			"mobile_number": row.get("mobile_number"),
			"recipient_name": row.get("recipient_name"),
			"recipient_data": row.get("recipient_data"),
		},
	)


def sync_secret(bulk_doc) -> None:
	"""Give the AWS senders the live token before a send."""
	from msuite_campaigns.aws_pipeline import client
	from msuite_whatsapp.queries import account_repository as accounts

	acc_name = bulk_doc.get("whatsapp_account") or accounts.find_default_account("outgoing")
	if acc_name:
		acc = accounts.get_account_doc(acc_name)
		token = acc.get_password("token", raise_exception=False) or ""
		if token:
			client.sync_channel_secret("whatsapp", {"access_token": token})


def record_outbound(bulk_doc) -> None:
	"""Record each recipient's message in the Inbox, so an agent sees what the AWS send delivered."""
	from msuite_inbox.inbox.constants import ChannelType, SenderType
	from msuite_inbox.inbox.services import outbound
	from msuite_whatsapp.services.bulk import bulk_send_service

	from msuite_whatsapp.services.channels import inbox_channel as wa_channel
	from msuite_whatsapp.queries.account_repository import find_default_account

	bulk_name = bulk_doc.name

	whatsapp_account = bulk_doc.get("whatsapp_account") or find_default_account("outgoing") or ""
	template_name = bulk_doc.get("template") or ""

	parent, parenttype = bulk_send_service.row_parent(bulk_doc)
	recipients = frappe.get_all(
		"WhatsApp Recipient",
		filters={"parent": parent, "parenttype": parenttype},
		fields=["name", "mobile_number", "recipient_name", "recipient_data", "status"],
	)

	inbox_name = outbound.inbox_for_account(
		ChannelType.WHATSAPP, whatsapp_account
	) or outbound._default_inbox_for_channel(ChannelType.WHATSAPP)
	if not inbox_name:
		return

	inbox_doc = frappe.get_doc("Inbox", inbox_name)

	for r in recipients:
		raw_phone = r.get("mobile_number")
		phone = bulk_send_service.normalize_phone(raw_phone)
		if not phone:
			continue

		# Look up or create handle
		handle_doc = outbound._upsert_handle(ChannelType.WHATSAPP, phone)
		if r.get("recipient_name") and not handle_doc.display_name:
			frappe.db.set_value("Channel Handle", handle_doc.name, "display_name", r["recipient_name"], update_modified=False)
			handle_doc.display_name = r["recipient_name"]

		# Check if message already recorded for this broadcast
		existing = frappe.db.get_value(
			"Channel Message",
			{
				"reference_doctype": bulk_doc.doctype,
				"reference_name": bulk_doc.name,
				"channel_handle": handle_doc.name,
			},
			"name",
		)
		if existing:
			continue

		recipient_data = bulk_send_service._parse_recipient_data(r)
		body_param = r.get("body_param") if r.get("body_param") is not None else None
		if body_param is None and bulk_doc.get("template_variables"):
			body_param = bulk_send_service.build_body_param(bulk_doc, recipient_data)

		payload = {
			"type": "template",
			"template": template_name,
			"body_param": body_param,
			"sender_type": SenderType.BOT,
			"sender_name": "Campaign Bot",
			"reference_doctype": bulk_doc.doctype,
			"reference_name": bulk_doc.name,
			"whatsapp_account": whatsapp_account,
		}

		conversation_doc = outbound._upsert_outbound_conversation(
			inbox_doc,
			handle_doc,
			payload,
			reference_doctype=bulk_doc.doctype,
			reference_name=bulk_doc.name,
		)

		msg_res = wa_channel._record_outbound(
			conversation_doc,
			handle_doc,
			payload,
			platform_message_id=f"aws-wa-{bulk_name}-{r.get('name') or frappe.generate_hash(length=8)}",
			ok=True,
			error=None,
			whatsapp_account=whatsapp_account,
		)
		if msg_res.get("message") and r.get("status"):
			st = r.get("status")
			if st in ("Read", "Delivered", "Sent", "Failed"):
				frappe.db.set_value("Channel Message", msg_res["message"], "status", st, update_modified=False)
