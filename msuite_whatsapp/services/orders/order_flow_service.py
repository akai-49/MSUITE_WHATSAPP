"""WhatsApp Order Flow Service — delivery address collection for cart/order messages.

When an inbound WhatsApp Order message is received:
1. `send_order_address_flow()` sends an interactive WhatsApp Flow asking for:
   - Full Name
   - Mobile Number
   - Delivery Address
   - City
   - Pincode
2. If Meta Flow API is not yet published for the WABA account, falls back to an interactive address prompt.
3. `process_address_flow_response()` processes the customer's Flow submission or text reply:
   - Creates/Updates the ERPNext Customer and Address records.
   - Sends a confirmation message back to WhatsApp.
"""

from __future__ import annotations

import json

import frappe
from frappe import _

FLOW_DOCTYPE = "WhatsApp Flow"


def resolve_order_flow_doc(target_flow_name: str | None = None, whatsapp_account: str | None = None):
	"""Dynamically resolve the WhatsApp Flow document configured by the merchant or fallback."""
	# 1. Check user-configured flow name by primary key or flow_name field
	if target_flow_name:
		target_clean = str(target_flow_name).strip()
		if frappe.db.exists(FLOW_DOCTYPE, target_clean):
			doc = frappe.get_doc(FLOW_DOCTYPE, target_clean)
			_ensure_flow_created_on_meta(doc)
			return doc

		existing_by_name = frappe.db.get_value(FLOW_DOCTYPE, {"flow_name": target_clean}, "name")
		if existing_by_name and isinstance(existing_by_name, str):
			doc = frappe.get_doc(FLOW_DOCTYPE, existing_by_name)
			_ensure_flow_created_on_meta(doc)
			return doc

	# No explicitly configured flow resolved. Do not guess by picking an
	# arbitrary/most-recently-modified Published flow — with more than one
	# Published flow in the system (e.g. a lead-gen survey alongside the
	# order-delivery form) that would silently send the wrong form to a
	# customer. Callers already handle None by falling back to a plain-text
	# prompt (see send_order_address_flow), which is the safe default.
	return None


def get_or_create_order_address_flow(whatsapp_account: str | None = None) -> str:
	"""Backward-compatible shim returning the name of the resolved order flow, or empty string if none."""
	doc = resolve_order_flow_doc(whatsapp_account=whatsapp_account)
	return str(getattr(doc, "name", "")) if doc else ""


def _ensure_flow_created_on_meta(doc) -> None:
	"""Best-effort attempt to create the flow shell on Meta Graph API if flow_id is empty."""
	if getattr(doc, "flow_id", None) or not getattr(doc, "whatsapp_account", None):
		return
	try:
		from msuite_whatsapp.services.flows import flow_service

		flow_service.create_on_whatsapp(doc)
	except Exception as e:
		frappe.log_error(title="order_flow_service: create_on_whatsapp failed", message=str(e))


def _cart_total(product_items: list[dict]) -> float:
	return sum(float(p.get("quantity") or 1) * float(p.get("item_price") or 0) for p in product_items)


def record_inbound_cart_order(conversation_doc, message_doc) -> str | None:
	# Same detection as dispatcher._maybe_send_order_address_flow: the cart lives in interactive_payload.
	payload = getattr(message_doc, "interactive_payload", None) or {}
	if isinstance(payload, str):
		try:
			payload = json.loads(payload)
		except Exception:
			payload = {}
	order_data = payload.get("order") or (payload if payload.get("type") == "order" else {})
	items = (order_data or {}).get("product_items") or []
	if not items:
		return None
	wamid = getattr(message_doc, "platform_message_id", None)
	if wamid:
		if existing := frappe.db.get_value("Meta Commerce Order", {"meta_order_id": wamid}, "name"):
			return existing
	catalog = frappe.db.get_value("Meta Product Catalog", {"catalog_id": order_data.get("catalog_id")}, "name")
	if not catalog and order_data.get("catalog_id"):
		frappe.log_error(title="WhatsApp cart from unknown catalog", message=str(order_data.get("catalog_id")))
	doc = frappe.get_doc({
		"doctype": "Meta Commerce Order",
		"channel": "whatsapp",
		"meta_order_id": wamid,
		"catalog": catalog,
		"currency": items[0].get("currency") or "INR",
		"total_amount": _cart_total(items),
		"conversation": getattr(conversation_doc, "name", None),
		"customer_phone": getattr(conversation_doc, "customer_phone", None) or getattr(message_doc, "sender_phone", None),
		"order_status": "Awaiting Address",
		"raw_payload": json.dumps(order_data),
		"items": [
			{
				"retailer_id": p.get("product_retailer_id"),
				"item_name": frappe.db.get_value("Item", p.get("product_retailer_id"), "item_name") or p.get("product_retailer_id"),
				"qty": float(p.get("quantity") or 1),
				"unit_price": float(p.get("item_price") or 0),
			}
			for p in items
		],
	})
	doc.insert(ignore_permissions=True)
	return doc.name


def send_order_address_flow(conversation_doc, message_doc, order_name: str | None = None) -> dict | None:
	"""Send an interactive WhatsApp Flow message (or text fallback) prompting the customer for delivery details."""
	from msuite_inbox.inbox.services import outbound
	from msuite_whatsapp.api.v1.app.order_settings import (
		DEFAULT_PROMPT_TEXT,
		KEY_AUTO_SEND,
		KEY_PROMPT_TEXT,
		KEY_SELECTED_FLOW,
	)
	from msuite_whatsapp.services.flows import flow_response_service

	raw_auto_send = frappe.db.get_default(KEY_AUTO_SEND)
	if raw_auto_send is not None and str(raw_auto_send).strip() in ("0", "false", "False"):
		return None

	phone = getattr(conversation_doc, "customer_phone", None) or getattr(message_doc, "sender_phone", None)
	if not phone:
		return None

	configured_flow = frappe.db.get_default(KEY_SELECTED_FLOW)
	flow_doc = resolve_order_flow_doc(
		target_flow_name=str(configured_flow).strip() if configured_flow else None,
		whatsapp_account=getattr(message_doc, "whatsapp_account", None),
	)
	prompt_text = frappe.db.get_default(KEY_PROMPT_TEXT) or DEFAULT_PROMPT_TEXT

	flow_id = getattr(flow_doc, "flow_id", None) if flow_doc else None
	# If the flow has a flow_id registered on Meta, send the native Interactive Flow
	if flow_doc and flow_id:
		flow_token = frappe.generate_hash(length=16)

		if order_name and frappe.db.exists("Meta Commerce Order", order_name):
			# The one place a prompt is counted. Resetting this to 1 would make the cap unreachable.
			already_sent = int(frappe.db.get_value("Meta Commerce Order", order_name, "address_prompts_sent") or 0)
			frappe.db.set_value(
				"Meta Commerce Order",
				order_name,
				{
					"flow_token": flow_token,
					"address_prompts_sent": already_sent + 1,
				},
				update_modified=False,
			)

		try:
			flow_response_service.mark_sent(
				flow_doc=flow_doc,
				phone=phone,
				flow_token=flow_token,
				conversation=conversation_doc.name,
			)
		except Exception as e:
			frappe.log_error(title="send_order_address_flow: mark_sent failed", message=str(e))

		payload = {
			"type": "flow",
			"flow": str(getattr(flow_doc, "name", "")),
			"flow_cta": getattr(flow_doc, "flow_cta", None) or "Enter Delivery Address",
			"flow_token": flow_token,
			"text": str(prompt_text),
		}
	else:
		# Fallback text prompt if Meta Flow API isn't registered yet for this WABA
		payload = {
			"type": "text",
			"text": str(prompt_text),
		}

	return outbound.send_message(
		channel_type="WhatsApp",
		platform_handle=phone,
		payload=payload,
		inbox=conversation_doc.inbox,
		account=getattr(message_doc, "whatsapp_account", None),
		reference_doctype=message_doc.doctype,
		reference_name=message_doc.name,
	)



MAX_ADDRESS_PROMPTS = 3


def process_address_flow_response(flow_response_doc, response_data: dict) -> str:
	"""Process submitted address fields, update/create ERPNext Customer, Address, and Sales Order records,
	and notify the buyer on WhatsApp. Returns one of:
	'created' | 'reasked' | 'needs_agent' | 'ignored' | 'already_done'
	"""
	flow_token = getattr(flow_response_doc, "flow_token", None) or response_data.get("flow_token")
	if not flow_token:
		return "ignored"

	order_name = frappe.db.get_value("Meta Commerce Order", {"flow_token": flow_token}, "name")
	if not order_name:
		return "ignored"

	order_doc = frappe.get_doc("Meta Commerce Order", order_name, for_update=True)
	if getattr(order_doc, "erpnext_sales_order", None):
		return "already_done"

	full_name = str(response_data.get("full_name") or response_data.get("contact_name") or "").strip()
	mobile_no = str(
		response_data.get("mobile_number")
		or response_data.get("phone")
		or getattr(flow_response_doc, "contact_phone", None)
		or getattr(order_doc, "customer_phone", None)
		or ""
	).strip()
	address_line = str(
		response_data.get("address_line1")
		or response_data.get("address_line")
		or response_data.get("address")
		or ""
	).strip()
	city = str(response_data.get("city") or "").strip()
	pincode = str(response_data.get("pincode") or response_data.get("zip") or "").strip()

	# Complete means address_line1 (or address_line), city, pincode all non-blank after .strip()
	is_complete = bool(address_line and city and pincode)
	if not is_complete:
		prompts_sent = int(getattr(order_doc, "address_prompts_sent", None) or 0)
		if prompts_sent >= MAX_ADDRESS_PROMPTS:
			cap_msg = f"Address incomplete after {prompts_sent} attempts. Requires agent assistance."
			if hasattr(order_doc, "db_set"):
				order_doc.db_set("last_error", cap_msg)
			else:
				order_doc.last_error = cap_msg
			cap_conversation = getattr(flow_response_doc, "conversation", None) or order_doc.get("conversation")
			_notify_conversation_agent(cap_conversation, cap_msg)
			return "needs_agent"

		# Re-send the Flow; send_order_address_flow rotates flow_token and counts the prompt.
		conversation_name = getattr(flow_response_doc, "conversation", None) or order_doc.get("conversation")
		conv_doc = frappe.get_doc("Conversation", conversation_name) if conversation_name else None
		msg_doc = None
		channel_message_name = getattr(flow_response_doc, "channel_message", None)
		if channel_message_name and frappe.db.exists("Channel Message", channel_message_name):
			msg_doc = frappe.get_doc("Channel Message", channel_message_name)
		else:
			# Synthetic or minimal message doc for sending
			msg_doc = frappe._dict({
				"doctype": "Channel Message",
				"name": channel_message_name,
				"sender_phone": mobile_no,
				"whatsapp_account": getattr(flow_response_doc, "whatsapp_account", None),
			})

		if conv_doc:
			send_order_address_flow(conv_doc, msg_doc, order_name=order_doc.name)
		return "reasked"

	# 1. Upsert Customer in ERPNext
	customer_name = _upsert_customer(full_name=full_name, mobile_no=mobile_no)

	# 2. Upsert Address in ERPNext
	address_name = _upsert_address(
		customer_name=customer_name,
		full_name=full_name,
		address_line=address_line,
		city=city,
		pincode=pincode,
		mobile_no=mobile_no,
	)

	# 3. Create Sales Order in ERPNext containing items from the WhatsApp cart
	conversation_name = getattr(flow_response_doc, "conversation", None) or order_doc.get("conversation")
	try:
		sales_order_name = _create_sales_order(
			customer_name=customer_name,
			address_name=address_name,
			order_doc=order_doc,
		)
	except Exception as err:
		frappe.log_error(title="Failed to create ERPNext Sales Order from WhatsApp cart", message=str(err))
		error_msg = f"Failed to create Sales Order: {err}"
		order_doc.last_error = error_msg
		if hasattr(order_doc, "db_set"):
			order_doc.db_set("last_error", error_msg)
		_notify_conversation_agent(conversation_name, error_msg)
		return "needs_agent"

	if not sales_order_name:
		error_msg = "Failed to create Sales Order from cart items."
		order_doc.last_error = error_msg
		if hasattr(order_doc, "db_set"):
			order_doc.db_set("last_error", error_msg)
		_notify_conversation_agent(conversation_name, error_msg)
		return "needs_agent"


	order_doc.order_status = "Created"
	order_doc.erpnext_sales_order = sales_order_name
	order_doc.delivery_address = address_name
	if hasattr(order_doc, "db_set"):
		order_doc.db_set({
			"order_status": "Created",
			"erpnext_sales_order": sales_order_name,
			"delivery_address": address_name,
		})

	frappe.db.commit()


	# 4. Send confirmation WhatsApp message with Sales Order number
	phone = getattr(flow_response_doc, "contact_phone", None) or mobile_no
	if phone:
		from msuite_inbox.inbox.services import outbound

		so_msg = f"\n📦 Order ID: *{sales_order_name}*" if sales_order_name else ""
		confirm_text = (
			f"Thank you {full_name or 'Customer'}! 🚚{so_msg}\n\n"
			f"Your delivery address has been saved:\n"
			f"{address_line}, {city} - {pincode}\n\n"
			f"We will update you here as soon as your order is dispatched!"
		)
		outbound.send_message(
			channel_type="WhatsApp",
			platform_handle=phone,
			payload={"type": "text", "text": confirm_text},
			account=getattr(flow_response_doc, "whatsapp_account", None),
		)

	return "created"



def _notify_conversation_agent(conversation_name: str, message: str) -> None:
	"""Notify assigned agent/team or inbox members about an order issue."""
	if not conversation_name:
		return
	try:
		from msuite_core.services.notifications import create_notification_log
		from msuite_inbox.inbox.services.visibility import audience_for_conversation

		audience = audience_for_conversation(conversation_name)
		recipients = audience if audience is not None else [frappe.session.user or "Administrator"]
		for user in recipients:
			if user:
				create_notification_log(
					recipient=user,
					subject="WhatsApp Order Requires Attention",
					doc_type="Conversation",
					doc_name=conversation_name,
					status=message[:100],
				)
	except Exception as e:
		frappe.log_error(title="Failed to notify agent about WhatsApp order", message=str(e))


def _upsert_customer(full_name: str, mobile_no: str) -> str:
	"""Find or create an ERPNext Customer by normalised mobile only. Never match by name."""
	from msuite_whatsapp.services.validators.recipient_validator import clean_mobile

	cleaned_phone = None
	if mobile_no:
		cleaned, _ = clean_mobile(mobile_no)
		cleaned_phone = cleaned or mobile_no

	customer_name = None
	if cleaned_phone:
		customer_name = frappe.db.get_value("Customer", {"mobile_no": cleaned_phone}, "name")

	if customer_name and isinstance(customer_name, str):
		return str(customer_name)

	if not full_name:
		full_name = f"Customer {cleaned_phone}" if cleaned_phone else "WhatsApp Customer"

	cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name") or "Individual"
	ter = frappe.db.get_value("Territory", {"is_group": 0}, "name") or "India"

	cust = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": full_name,
			"customer_type": "Individual",
			"customer_group": cg,
			"territory": ter,
			"mobile_no": cleaned_phone,
		}
	)
	cust.flags.ignore_permissions = True
	cust.insert()
	return str(cust.name)


def _upsert_address(
	customer_name: str,
	full_name: str,
	address_line: str,
	city: str,
	pincode: str,
	mobile_no: str,
) -> str:
	"""Create or reuse an Address record linked to the Customer via Dynamic Link, address_line1, and pincode."""
	from msuite_whatsapp.services.validators.recipient_validator import clean_mobile

	cleaned_phone = None
	if mobile_no:
		cleaned, _ = clean_mobile(mobile_no)
		cleaned_phone = cleaned or mobile_no

	# Dedupe through tabDynamic Link joined to address_line1 and pincode
	existing = frappe.db.sql(
		"""SELECT dl.parent
		FROM `tabDynamic Link` dl
		JOIN `tabAddress` addr ON addr.name = dl.parent
		WHERE dl.link_doctype = 'Customer'
		  AND dl.link_name = %s
		  AND addr.address_line1 = %s
		  AND addr.pincode = %s
		LIMIT 1""",
		(customer_name, address_line, pincode),
	)
	if existing and existing[0] and existing[0][0]:
		return str(existing[0][0])

	company = frappe.db.get_default("company")
	if not company:
		try:
			company = frappe.db.get_single_value("Global Defaults", "default_company")
		except Exception:
			company = None
	if not company:
		try:
			company = frappe.db.get_value("Company", {}, "name")
		except Exception:
			company = None
	country = None
	if company:
		try:
			country = frappe.db.get_value("Company", company, "country")
		except Exception:
			country = None
	if not country:
		country = "India"

	address_title = f"{full_name} - Shipping" if full_name else f"{customer_name} - Shipping"

	addr = frappe.get_doc(
		{
			"doctype": "Address",
			"address_title": address_title,
			"address_type": "Shipping",
			"address_line1": address_line,
			"city": city or "Default City",
			"pincode": pincode or "",
			"country": country,
			"phone": cleaned_phone,
			"is_shipping_address": 1,
			"links": [
				{
					"link_doctype": "Customer",
					"link_name": customer_name,
				}
			],
		}
	)
	addr.flags.ignore_permissions = True
	addr.insert()
	return str(addr.name)


def _create_sales_order(
	customer_name: str,
	address_name: str | None,
	order_doc,
) -> str | None:
	"""Create and submit a Sales Order from the cart stored on `order_doc` (its child rows), never from
	whatever cart message happens to be newest in the conversation."""
	if not frappe.db.exists("DocType", "Sales Order"):
		return None

	product_items = [
		{
			"product_retailer_id": row.get("retailer_id") if hasattr(row, "get") else getattr(row, "retailer_id", None),
			"quantity": row.get("qty") if hasattr(row, "get") else getattr(row, "qty", None),
			"item_price": row.get("unit_price") if hasattr(row, "get") else getattr(row, "unit_price", None),
		}
		for row in (order_doc.get("items") or [])
	]
	if not product_items:
		return None

	company = (
		frappe.db.get_default("company")
		or frappe.db.get_value("Global Defaults", None, "default_company")
		or frappe.db.get_value("Company", {}, "name")
	)
	if not company:
		return None

	currency = order_doc.get("currency") or "INR"
	selling_price_list = (
		frappe.db.get_value("Selling Settings", None, "selling_price_list")
		or frappe.db.get_default("selling_price_list")
		or frappe.db.get_value("Price List", {"selling": 1}, "name")
	)

	so_items = []
	for p in product_items:
		sku = str(p.get("product_retailer_id") or "").strip()
		qty = float(p.get("quantity") or 1)
		rate = float(p.get("item_price") or 0)

		if not sku:
			continue

		# Resolve ERPNext Item by item_code or item_name
		item_code = frappe.db.get_value("Item", sku, "name")
		if not item_code:
			item_code = frappe.db.get_value("Item", {"item_code": sku}, "name")
		if not item_code:
			item_code = frappe.db.get_value("Item", {"item_name": sku}, "name")

		if item_code:
			so_items.append(
				{
					"item_code": item_code,
					"qty": qty,
					"rate": rate,
				}
			)

	if not so_items:
		return None

	from frappe.utils import add_days, nowdate

	so_data = {
		"doctype": "Sales Order",
		"customer": customer_name,
		"company": company,
		"currency": currency,
		"delivery_date": add_days(nowdate(), 3),
		"customer_address": address_name,
		"shipping_address_name": address_name,
		"items": so_items,
	}
	if selling_price_list:
		so_data["selling_price_list"] = selling_price_list

	so = frappe.get_doc(so_data)
	so.flags.ignore_permissions = True
	# Do NOT set ignore_mandatory
	so.insert()

	try:
		so.submit()
	except Exception as sub_err:
		frappe.log_error(title="Sales Order submit warning", message=str(sub_err))

	return str(so.name)

