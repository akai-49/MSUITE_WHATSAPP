"""WhatsApp Flow Response service — persists Meta's nfm_reply submissions.

Two entry points:
  * `mark_sent()` — called by `flow_service.send_test` right before the
    flow message goes out, so we own the flow_token before Meta ever
    sees it and can correlate the reply that comes back. Without this,
    an inbound nfm_reply carries no reliable pointer back to which
    WhatsApp Flow doc it came from — Meta's `nfm_reply.name` is just the
    literal string "flow", not the flow's actual name.
  * `capture_from_message()` — called by the inbox dispatcher's inbound
    post-persist side effects for every nfm_reply message. Best-effort:
    the dispatcher wraps it in `_try(...)`, so any exception here is
    logged and swallowed rather than losing the Channel Message.
"""

from __future__ import annotations

import json

import frappe

DOCTYPE = "WhatsApp Flow Response"


def mark_sent(flow_doc, phone: str, flow_token: str, conversation: str | None = None) -> str:
	"""Create the 'Sent' half of a flow response before the message is sent."""
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"flow": flow_doc.name,
			"flow_name_snapshot": flow_doc.flow_name,
			"whatsapp_account": flow_doc.whatsapp_account,
			"status": "Sent",
			"contact_phone": phone,
			"flow_token": flow_token,
			"conversation": conversation or "",
			"sent_at": frappe.utils.now_datetime(),
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def capture_from_message(message_doc, event) -> None:
	"""Parse an inbound nfm_reply Channel Message into a Flow Response.

	Matches against the `Sent` row created by `mark_sent()` via
	`flow_token`. If no match is found (token unknown/expired, or the
	flow was triggered outside this system) a standalone `Completed`
	record is still saved rather than dropping the submission.
	"""
	payload = getattr(message_doc, "interactive_payload", None) or {}
	if isinstance(payload, str):
		try:
			payload = json.loads(payload)
		except Exception:
			payload = {}
	if not isinstance(payload, dict) or payload.get("type") != "nfm_reply":
		return

	nfm = payload.get("nfm_reply") or {}
	raw = nfm.get("response_json")
	if not raw:
		return

	try:
		response = json.loads(raw) if isinstance(raw, str) else (raw or {})
	except (ValueError, TypeError):
		frappe.log_error(
			title="flow_response_service: invalid response_json",
			message=f"message={message_doc.name} raw={raw!r}",
		)
		return

	if not isinstance(response, dict):
		return

	flow_token = response.get("flow_token") or ""
	existing_name = frappe.db.exists(DOCTYPE, {"flow_token": flow_token}) if flow_token else None

	doc = frappe.get_doc(DOCTYPE, existing_name) if existing_name else frappe.new_doc(DOCTYPE)
	doc.status = "Completed"
	doc.completed_at = frappe.utils.now_datetime()
	doc.channel_message = (
		message_doc.name
		if (message_doc and getattr(message_doc, "name", None) and frappe.db.exists("Channel Message", message_doc.name))
		else None
	)
	doc.conversation = (
		message_doc.conversation
		if (message_doc and getattr(message_doc, "conversation", None) and frappe.db.exists("Conversation", message_doc.conversation))
		else (doc.get("conversation") or "")
	)
	doc.contact_phone = getattr(message_doc, "sender_phone", None) or doc.get("contact_phone") or ""
	doc.contact_name = getattr(message_doc, "sender_name", None) or doc.get("contact_name") or ""
	doc.whatsapp_account = getattr(message_doc, "whatsapp_account", None) or doc.get("whatsapp_account") or ""
	doc.response_json = json.dumps(response, indent=2)
	if flow_token:
		doc.flow_token = flow_token
	if not doc.flow_name_snapshot:
		doc.flow_name_snapshot = "Unknown (no matching Sent record)"

	field_defs = _flow_field_labels(doc.flow) if doc.flow else {}

	doc.fields = []
	for key, value in response.items():
		if key == "flow_token":
			continue
		label, field_type = field_defs.get(key, (key, ""))
		doc.append(
			"fields",
			{
				"field_name": key,
				"field_label": label,
				"field_type": field_type,
				"value": _stringify(value),
				"value_json": json.dumps(value),
			},
		)

	doc.flags.ignore_permissions = True
	if existing_name:
		doc.save(ignore_permissions=True)
	else:
		doc.insert(ignore_permissions=True)

	# Link or create CRM Lead and record submission in Forms tab
	try:
		_sync_with_crm_lead(doc, message_doc, response)
	except Exception as lead_err:
		frappe.log_error(title="flow_response_service: CRM Lead sync failed", message=str(lead_err))

	# Enrich message interactive_payload with resolved flow_name for chat bubbles
	if doc.flow_name_snapshot and doc.flow_name_snapshot != "Unknown (no matching Sent record)":
		if isinstance(payload, dict):
			payload["flow_name"] = doc.flow_name_snapshot
			if getattr(message_doc, "name", None) and frappe.db.exists("Channel Message", message_doc.name):
				frappe.db.set_value(
					"Channel Message",
					message_doc.name,
					"interactive_payload",
					json.dumps(payload),
					update_modified=False,
				)

	try:
		flow_token = getattr(doc, "flow_token", None) or response.get("flow_token")
		if flow_token and frappe.db.exists("Meta Commerce Order", {"flow_token": flow_token}):
			from msuite_whatsapp.services.orders import order_flow_service

			order_flow_service.process_address_flow_response(doc, response)
	except Exception as e:
		frappe.log_error(title="flow_response_service: address processing failed", message=str(e))



def _sync_with_crm_lead(flow_response_doc, message_doc, response: dict) -> str | None:
	"""Associate WhatsApp Flow Response with a CRM Lead (or auto-create one if missing)

	and append a submission record under the lead's Forms tab (meta_form_submissions).
	"""
	from msuite_whatsapp.services.validators.recipient_validator import clean_mobile

	lead_name = None

	# 1. Check message reference
	if getattr(message_doc, "reference_doctype", None) == "CRM Lead" and getattr(message_doc, "reference_name", None):
		if frappe.db.exists("CRM Lead", message_doc.reference_name):
			lead_name = message_doc.reference_name

	# 2. Check conversation reference (crm_party / crm_party_type)
	if not lead_name and getattr(message_doc, "conversation", None):
		conv_party_type, conv_party = (
			frappe.db.get_value(
				"Conversation",
				message_doc.conversation,
				["crm_party_type", "crm_party"],
			)
			or (None, None)
		)
		if conv_party_type == "CRM Lead" and conv_party and frappe.db.exists("CRM Lead", conv_party):
			lead_name = conv_party

	# 3. Lookup by phone number
	raw_phone = flow_response_doc.contact_phone or (getattr(message_doc, "sender_phone", None) if message_doc else None)
	cleaned_phone, _ = clean_mobile(raw_phone) if raw_phone else (None, None)

	if not lead_name and (cleaned_phone or raw_phone):
		variants = set()
		for p in (cleaned_phone, raw_phone):
			if not p:
				continue
			p_str = str(p).strip().replace(" ", "").replace("-", "")
			variants.add(p_str)
			variants.add(f"+{p_str.lstrip('+')}")
			variants.add(p_str.lstrip("+"))
			# If 12-digit Indian number starting with 91, also add 10-digit
			if p_str.startswith("91") and len(p_str) == 12:
				variants.add(p_str[2:])
				variants.add(f"+91{p_str[2:]}")
			elif len(p_str) == 10:
				variants.add(f"91{p_str}")
				variants.add(f"+91{p_str}")

		phone_variants = list(variants)
		lead_name = frappe.db.get_value(
			"CRM Lead",
			{"mobile_no": ["in", phone_variants]},
			"name",
		) or frappe.db.get_value(
			"CRM Lead",
			{"phone": ["in", phone_variants]},
			"name",
		)
		if not lead_name and frappe.db.has_column("CRM Lead", "whatsapp_no"):
			lead_name = frappe.db.get_value(
				"CRM Lead",
				{"whatsapp_no": ["in", phone_variants]},
				"name",
			)

	# 4. If lead not found, auto-create the CRM Lead with submitted flow fields
	if not lead_name:
		extracted_name = ""
		first_name = ""
		last_name = ""
		email = ""
		organization = ""

		for f in flow_response_doc.fields:
			fname_lower = (f.field_name or "").lower().replace("_", "")
			flabel_lower = (f.field_label or "").lower()
			val = (f.value or "").strip()
			if not val:
				continue
			if any(k in fname_lower or k in flabel_lower for k in ("fullname", "leadname", "customername", "yourname", "name")):
				if not extracted_name and len(val) > 1:
					extracted_name = val
			elif "firstname" in fname_lower or "firstname" in flabel_lower:
				first_name = val
			elif "lastname" in fname_lower or "lastname" in flabel_lower:
				last_name = val
			elif "email" in fname_lower or "email" in flabel_lower or ("@" in val and "." in val):
				email = val
			elif any(k in fname_lower or k in flabel_lower for k in ("organization", "company", "business")):
				organization = val

		if not extracted_name:
			if first_name or last_name:
				extracted_name = f"{first_name} {last_name}".strip()
			elif flow_response_doc.contact_name:
				extracted_name = flow_response_doc.contact_name
			else:
				extracted_name = f"WhatsApp Lead ({cleaned_phone or raw_phone})"

		final_first_name = first_name or (extracted_name.split()[0] if extracted_name else "Lead")
		final_last_name = last_name or (" ".join(extracted_name.split()[1:]) if extracted_name and len(extracted_name.split()) > 1 else "")

		source_name = "WhatsApp Flow"
		if frappe.db.exists("DocType", "CRM Lead Source") and not frappe.db.exists("CRM Lead Source", source_name):
			try:
				src_doc = frappe.get_doc({"doctype": "CRM Lead Source", "source_name": source_name})
				src_doc.insert(ignore_permissions=True)
			except Exception:
				source_name = "WhatsApp Inbound" if frappe.db.exists("CRM Lead Source", "WhatsApp Inbound") else None

		new_lead = frappe.get_doc(
			{
				"doctype": "CRM Lead",
				"lead_name": extracted_name,
				"first_name": final_first_name,
				"last_name": final_last_name,
				"mobile_no": cleaned_phone or raw_phone,
				"phone": cleaned_phone or raw_phone,
				"email": email or None,
				"organization": organization or None,
				"source": source_name,
				"status": "New",
			}
		)
		new_lead.insert(ignore_permissions=True)
		lead_name = new_lead.name

	# 5. Append submission row to CRM Lead meta_form_submissions (Forms tab)
	lead_doc = frappe.get_doc("CRM Lead", lead_name)

	# Check for deduplication against this flow response
	exists_in_lead = any(
		row.platform_lead_id in (flow_response_doc.name, flow_response_doc.flow_token)
		for row in (lead_doc.get("meta_form_submissions") or [])
	)

	answers_lines = []
	for f in flow_response_doc.fields:
		lbl = f.field_label or f.field_name or "Field"
		answers_lines.append(f"{lbl}: {f.value}")
	answers_text = "\n".join(answers_lines)

	if not exists_in_lead:
		lead_doc.append(
			"meta_form_submissions",
			{
				"platform_lead_id": flow_response_doc.name,
				"form_type": "WhatsApp Flow",
				"form_name": flow_response_doc.flow_name_snapshot or "WhatsApp Flow",
				"whatsapp_flow": flow_response_doc.flow or None,
				"meta_captured_at": flow_response_doc.completed_at or frappe.utils.now_datetime(),
				"meta_form_answers": answers_text,
				"meta_raw_answers": flow_response_doc.response_json or json.dumps(response),
			},
		)
		lead_doc.flags.ignore_permissions = True
		lead_doc.save(ignore_permissions=True)

	# 6. Store lead reference on WhatsApp Flow Response doc
	flow_response_doc.db_set("lead", lead_name)
	frappe.db.commit()

	return lead_name


def _flow_field_labels(flow_name: str) -> dict[str, tuple[str, str]]:
	"""field_name -> (label, field_type) for every field on this Flow, so
	a raw response key like 'account_type' can show 'Account Type'
	instead of the bare key."""
	try:
		rows = frappe.get_all(
			"WhatsApp Flow Field",
			filters={"parent": flow_name, "parenttype": "WhatsApp Flow"},
			fields=["field_name", "label", "field_type"],
		)
	except Exception:
		return {}
	return {r.field_name: (r.label or r.field_name, r.field_type) for r in rows}


def _stringify(value) -> str:
	if isinstance(value, list):
		return ", ".join(str(v) for v in value)
	if isinstance(value, dict):
		return json.dumps(value)
	return "" if value is None else str(value)

