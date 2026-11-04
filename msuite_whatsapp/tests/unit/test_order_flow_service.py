# Copyright (c) 2026, MSuite and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe import _dict

from msuite_whatsapp.services.orders import order_flow_service


class TestOrderFlowService(unittest.TestCase):
	def test_cart_total(self):
		items = [
			{"product_retailer_id": "A", "quantity": 2, "item_price": 150},
			{"product_retailer_id": "B", "quantity": 1, "item_price": 99.5},
		]
		self.assertEqual(order_flow_service._cart_total(items), 399.5)

	def test_cart_with_auto_send_off_is_recorded_and_nothing_sent(self):
		conv = _dict(name="CONV-1", customer_phone="919876543210", inbox="INBOX-1")
		msg = _dict(
			name="MSG-1",
			platform_message_id="wamid.123",
			sender_phone="919876543210",
			content_type="order",
			interactive_payload={
				"order": {
					"catalog_id": "cat_test_1",
					"product_items": [
						{"product_retailer_id": "ITEM-1", "quantity": 2, "item_price": 100, "currency": "INR"}
					],
				}
			},
		)

		mock_order_doc = MagicMock()
		mock_order_doc.name = "ORDER-MOCK-1"
		with patch("frappe.db.get_default", return_value="0"), \
			 patch("frappe.db.get_value", return_value=None), \
			 patch("frappe.log_error"), \
			 patch("frappe.get_doc", return_value=mock_order_doc) as mock_get_doc:
			order_name = order_flow_service.record_inbound_cart_order(conv, msg)
			self.assertEqual(order_name, "ORDER-MOCK-1")
			mock_get_doc.assert_called_once()
			created_data = mock_get_doc.call_args[0][0]
			self.assertEqual(created_data["order_status"], "Awaiting Address")
			self.assertEqual(created_data["channel"], "whatsapp")
			send_res = order_flow_service.send_order_address_flow(conv, msg, order_name=order_name)
			self.assertIsNone(send_res)


	def test_total_is_sum_of_quantity_times_price(self):
		items = [
			{"product_retailer_id": "A", "quantity": 2, "item_price": 150},
			{"product_retailer_id": "B", "quantity": 1, "item_price": 99.5},
		]
		self.assertEqual(order_flow_service._cart_total(items), 399.5)

	def test_unknown_catalog_id_recorded_with_blank_catalog(self):
		conv = _dict(name="CONV-2", customer_phone="919876543210", inbox="INBOX-1")
		msg = _dict(
			name="MSG-2",
			platform_message_id="wamid.unknown.cat",
			sender_phone="919876543210",
			interactive_payload={
				"order": {
					"catalog_id": "UNKNOWN_CAT_999",
					"product_items": [
						{"product_retailer_id": "ITEM-1", "quantity": 1, "item_price": 50, "currency": "INR"}
					],
				}
			},
		)

		mock_doc = MagicMock()
		with patch("frappe.db.get_value") as mock_get_value, \
			 patch("frappe.log_error") as mock_log, \
			 patch("frappe.get_doc", return_value=mock_doc) as mock_get_doc:
			# Return None for existing order and catalog
			mock_get_value.return_value = None
			order_name = order_flow_service.record_inbound_cart_order(conv, msg)
			mock_log.assert_called_once()
			mock_doc.insert.assert_called_once()
			# Inspect call args to get_doc
			created_data = mock_get_doc.call_args[0][0]
			self.assertIsNone(created_data.get("catalog"))
			self.assertEqual(created_data.get("order_status"), "Awaiting Address")
			self.assertEqual(created_data.get("channel"), "whatsapp")

	def test_same_wamid_twice_makes_one_order(self):
		conv = _dict(name="CONV-3", customer_phone="919876543210", inbox="INBOX-1")
		msg = _dict(
			name="MSG-3",
			platform_message_id="wamid.duplicate",
			sender_phone="919876543210",
			interactive_payload={
				"order": {
					"catalog_id": "CAT-1",
					"product_items": [
						{"product_retailer_id": "ITEM-1", "quantity": 1, "item_price": 50, "currency": "INR"}
					],
				}
			},
		)

		with patch("frappe.db.get_value", return_value="EXISTING-ORDER-1") as mock_get_value, \
			 patch("frappe.get_doc") as mock_get_doc:
			name = order_flow_service.record_inbound_cart_order(conv, msg)
			self.assertEqual(name, "EXISTING-ORDER-1")
			mock_get_doc.assert_not_called()

	def test_known_catalog_resolved_by_catalog_id_not_name(self):
		conv = _dict(name="CONV-4", customer_phone="919876543210", inbox="INBOX-1")
		msg = _dict(
			name="MSG-4",
			platform_message_id="wamid.known.cat",
			sender_phone="919876543210",
			interactive_payload={
				"order": {
					"catalog_id": "9988",
					"product_items": [
						{"product_retailer_id": "ITEM-1", "quantity": 1, "item_price": 50, "currency": "INR"}
					],
				}
			},
		)

		mock_doc = MagicMock()
		def get_val(doctype, filters, fieldname=None):
			if doctype == "Meta Commerce Order":
				return None
			if doctype == "Meta Product Catalog" and isinstance(filters, dict) and filters.get("catalog_id") == "9988":
				return "abc123"
			return None

		with patch("frappe.db.get_value", side_effect=get_val), \
			 patch("frappe.get_doc", return_value=mock_doc) as mock_get_doc:
			order_flow_service.record_inbound_cart_order(conv, msg)
			created_data = mock_get_doc.call_args[0][0]
			self.assertEqual(created_data.get("catalog"), "abc123")

	def test_unrelated_flow_with_address_is_ignored(self):
		flow_resp = _dict(flow_token="unrelated_token", contact_phone="919876543210")
		resp_data = {"address_line": "123 Main St", "city": "Mumbai", "pincode": "400001"}
		with patch("frappe.db.get_value", return_value=None), \
			 patch.object(order_flow_service, "_create_sales_order") as mock_so:
			result = order_flow_service.process_address_flow_response(flow_resp, resp_data)
			self.assertEqual(result, "ignored")
			mock_so.assert_not_called()

	def test_incomplete_address_reasks_via_send(self):
		flow_resp = _dict(flow_token="token_1", contact_phone="919876543210", conversation="CONV-1")
		resp_data = {"address_line": "123 Main St", "city": "Mumbai", "pincode": ""} # pincode missing

		mock_order = MagicMock()
		mock_order.name = "ORD-1"
		mock_order.flow_token = "token_1"
		mock_order.address_prompts_sent = 1
		mock_order.order_status = "Awaiting Address"
		mock_order.erpnext_sales_order = None

		with patch("frappe.db.get_value", return_value="ORD-1"), \
			 patch("frappe.get_doc", return_value=mock_order), \
			 patch.object(order_flow_service, "send_order_address_flow") as mock_send:
			result = order_flow_service.process_address_flow_response(flow_resp, resp_data)
			self.assertEqual(result, "reasked")
			# token rotation and the counter belong to send_order_address_flow alone
			mock_send.assert_called_once()
			self.assertEqual(mock_send.call_args.kwargs.get("order_name"), "ORD-1")
			self.assertEqual(mock_order.order_status, "Awaiting Address")

	def test_each_send_increments_prompt_counter_and_rotates_token(self):
		conv = _dict(name="CONV-1", customer_phone="919876543210", inbox="IB")
		msg = _dict(doctype="Channel Message", name="MSG-1", sender_phone="919876543210", whatsapp_account="WA1")
		flow_doc = _dict(flow_id="F1", name="FLOW-1", flow_cta="Go")
		with patch("frappe.db.get_default", return_value=None), \
			 patch.object(order_flow_service, "resolve_order_flow_doc", return_value=flow_doc), \
			 patch("frappe.db.exists", return_value=True), \
			 patch("frappe.db.get_value", return_value=2), \
			 patch("frappe.db.set_value") as mock_set, \
			 patch("msuite_whatsapp.services.flows.flow_response_service.mark_sent"), \
			 patch("msuite_inbox.inbox.services.outbound.send_message"):
			order_flow_service.send_order_address_flow(conv, msg, order_name="ORD-1")
		values = mock_set.call_args.args[2]
		self.assertEqual(values["address_prompts_sent"], 3, "counter must continue from 2, not reset to 1")
		self.assertTrue(values["flow_token"])

	def test_stubborn_customer_is_asked_at_most_max_prompts_times(self):
		"""Simulate the real loop: every send bumps the counter, every answer is incomplete."""
		flow_resp = _dict(flow_token="t", contact_phone="919876543210", conversation="CONV-1")
		resp_data = {"address_line": "1 Main", "city": "Pune", "pincode": ""}
		mock_order = MagicMock()
		mock_order.name = "ORD-1"
		mock_order.address_prompts_sent = 1  # first prompt went out when the cart was recorded
		mock_order.erpnext_sales_order = None

		def fake_send(conv, msg, order_name=None):
			mock_order.address_prompts_sent += 1

		results = []
		with patch("frappe.db.get_value", return_value="ORD-1"), \
			 patch("frappe.get_doc", return_value=mock_order), \
			 patch.object(order_flow_service, "_notify_conversation_agent"), \
			 patch.object(order_flow_service, "send_order_address_flow", side_effect=fake_send) as mock_send:
			for _ in range(6):
				results.append(order_flow_service.process_address_flow_response(flow_resp, resp_data))
		self.assertEqual(results[:3], ["reasked", "reasked", "needs_agent"])
		self.assertEqual(set(results[2:]), {"needs_agent"})
		self.assertEqual(mock_send.call_count, order_flow_service.MAX_ADDRESS_PROMPTS - 1)

	def test_cap_notifies_the_agent(self):
		flow_resp = _dict(flow_token="t", contact_phone="919876543210", conversation="CONV-1")
		mock_order = MagicMock()
		mock_order.address_prompts_sent = order_flow_service.MAX_ADDRESS_PROMPTS
		mock_order.erpnext_sales_order = None
		mock_order.get.return_value = "CONV-1"
		with patch("frappe.db.get_value", return_value="ORD-1"), \
			 patch("frappe.get_doc", return_value=mock_order), \
			 patch.object(order_flow_service, "_notify_conversation_agent") as mock_notify:
			result = order_flow_service.process_address_flow_response(flow_resp, {"city": "Pune"})
		self.assertEqual(result, "needs_agent")
		mock_notify.assert_called_once()
		self.assertEqual(mock_notify.call_args.args[0], "CONV-1")

	def test_old_token_stops_matching_after_reask(self):
		# When second response comes with old token, get_value for that token returns None
		flow_resp = _dict(flow_token="old_token", contact_phone="919876543210")
		resp_data = {"address_line": "123 Main St", "city": "Mumbai", "pincode": "400001"}
		with patch("frappe.db.get_value", return_value=None):
			result = order_flow_service.process_address_flow_response(flow_resp, resp_data)
			self.assertEqual(result, "ignored")

	def test_reask_is_capped(self):
		flow_resp = _dict(flow_token="token_3", contact_phone="919876543210", conversation="CONV-1")
		resp_data = {"address_line": "123 Main St", "city": "Mumbai", "pincode": ""} # pincode missing

		mock_order = MagicMock()
		mock_order.name = "ORD-1"
		mock_order.flow_token = "token_3"
		mock_order.address_prompts_sent = order_flow_service.MAX_ADDRESS_PROMPTS
		mock_order.order_status = "Awaiting Address"
		mock_order.erpnext_sales_order = None

		with patch("frappe.db.get_value", return_value="ORD-1"), \
			 patch("frappe.get_doc", return_value=mock_order), \
			 patch.object(order_flow_service, "_notify_conversation_agent"), \
			 patch.object(order_flow_service, "send_order_address_flow") as mock_send:
			result = order_flow_service.process_address_flow_response(flow_resp, resp_data)
			self.assertEqual(result, "needs_agent")
			mock_send.assert_not_called()
			self.assertTrue(mock_order.last_error)

	def test_two_submissions_same_token_one_sales_order(self):
		flow_resp = _dict(flow_token="token_done", contact_phone="919876543210", conversation="CONV-1")
		resp_data = {"address_line": "123 Main St", "city": "Mumbai", "pincode": "400001"}

		mock_order = MagicMock()
		mock_order.name = "ORD-1"
		mock_order.flow_token = "token_done"
		mock_order.erpnext_sales_order = "SO-2026-0001"

		with patch("frappe.db.get_value", return_value="ORD-1"), \
			 patch("frappe.get_doc", return_value=mock_order), \
			 patch.object(order_flow_service, "_create_sales_order") as mock_so:
			result = order_flow_service.process_address_flow_response(flow_resp, resp_data)
			self.assertEqual(result, "already_done")
			mock_so.assert_not_called()

	def test_complete_address_creates_sales_order_and_flips_status(self):
		flow_resp = _dict(flow_token="token_valid", contact_phone="919876543210", conversation="CONV-1")
		resp_data = {"address_line": "123 Main St", "city": "Mumbai", "pincode": "400001", "full_name": "Test User"}

		mock_order = MagicMock()
		mock_order.name = "ORD-1"
		mock_order.flow_token = "token_valid"
		mock_order.erpnext_sales_order = None
		mock_order.order_status = "Awaiting Address"

		with patch("frappe.db.get_value", return_value="ORD-1"), \
			 patch("frappe.get_doc", return_value=mock_order), \
			 patch.object(order_flow_service, "_upsert_customer", return_value="CUST-1"), \
			 patch.object(order_flow_service, "_upsert_address", return_value="ADDR-1"), \
			 patch.object(order_flow_service, "_create_sales_order", return_value="SO-001"), \
			 patch("frappe.db.commit"), \
			 patch("msuite_inbox.inbox.services.outbound.send_message"):
			result = order_flow_service.process_address_flow_response(flow_resp, resp_data)
			self.assertEqual(result, "created")
			self.assertEqual(mock_order.order_status, "Created")
			self.assertEqual(mock_order.erpnext_sales_order, "SO-001")
			self.assertEqual(mock_order.delivery_address, "ADDR-1")

	def test_same_name_different_phone_makes_two_customers(self):
		created = []
		def mock_insert(self_doc):
			created.append((self_doc.customer_name, self_doc.mobile_no))
			self_doc.name = f"CUST-{len(created)}"
			return self_doc

		with patch("frappe.db.get_value", return_value=None), \
			 patch("frappe.get_doc") as mock_get_doc:
			mock_doc_instance = MagicMock()
			mock_doc_instance.insert.side_effect = lambda: mock_insert(mock_doc_instance)
			mock_get_doc.return_value = mock_doc_instance

			c1 = order_flow_service._upsert_customer("Asha", "919800000001")
			c2 = order_flow_service._upsert_customer("Asha", "919800000002")
			self.assertNotEqual(c1, c2)

	def test_same_phone_reuses_customer_across_formats(self):
		def mock_get_value(doctype, filters, fieldname=None):
			if doctype == "Customer" and isinstance(filters, dict):
				if filters.get("mobile_no") == "+919800000001":
					return "CUST-EXISTING"
			return None

		with patch("frappe.db.get_value", side_effect=mock_get_value), \
			 patch("frappe.get_doc") as mock_get_doc:
			c1 = order_flow_service._upsert_customer("Asha", "+91 98000 00001")
			c2 = order_flow_service._upsert_customer("Asha", "919800000001")
			self.assertEqual(c1, "CUST-EXISTING")
			self.assertEqual(c2, "CUST-EXISTING")
			mock_get_doc.assert_not_called()

	def test_address_deduped_by_customer_line_and_pincode(self):
		existing_links = [
			{"link_name": "CUST-1", "parent": "ADDR-1", "address_line1": "1 MG Rd", "pincode": "411001"}
		]

		def mock_sql(query, values=None, *args, **kwargs):
			as_dict = kwargs.get("as_dict", False)
			# If searching for CUST-1 + 1 MG Rd + 411001, return ADDR-1
			if "tabDynamic Link" in str(query) and values:
				cust, line, pin = values[0], values[1], values[2]
				for r in existing_links:
					if r["link_name"] == cust and r["address_line1"] == line and r["pincode"] == pin:
						return [frappe._dict(name=r["parent"])] if as_dict else [(r["parent"],)]
			return []

		with patch("frappe.db.sql", side_effect=mock_sql), \
			 patch("frappe.get_doc") as mock_get_doc:
			# Same customer, line, pincode -> reused
			a1 = order_flow_service._upsert_address("CUST-1", "Asha", "1 MG Rd", "Pune", "411001", "919800000001")
			self.assertEqual(a1, "ADDR-1")

			# Different customer, same line, pincode -> new doc inserted
			mock_addr_doc = MagicMock()
			mock_addr_doc.name = "ADDR-2"
			mock_get_doc.return_value = mock_addr_doc
			a2 = order_flow_service._upsert_address("CUST-2", "Asha", "1 MG Rd", "Pune", "411001", "919800000001")
			self.assertEqual(a2, "ADDR-2")
			mock_addr_doc.insert.assert_called_once()

	def test_sales_order_header_and_rows(self):
		order_doc = _dict(
			name="ORD-1",
			currency="USD",
			items=[_dict(retailer_id="SKU-A", qty=2, unit_price=250)],
		)
		mock_so_doc = MagicMock()
		mock_so_doc.name = "SO-100"

		def mock_get_doc_fn(*args, **kwargs):
			dt_or_dict = args[0] if args else kwargs.get("doctype")
			if isinstance(dt_or_dict, dict) and dt_or_dict.get("doctype") == "Sales Order":
				mock_so_doc._data = dt_or_dict
				mock_so_doc.flags = _dict()
				return mock_so_doc
			return MagicMock()

		looked_up = []

		def mock_get_value(doctype, filters=None, fieldname=None, **kwargs):
			looked_up.append(doctype)
			if doctype == "Company":
				return "Test Company"
			if doctype == "Item":
				return "SKU-A"
			if doctype == "Selling Settings":
				return "Standard Selling"
			return None

		with patch("frappe.db.exists", return_value=True), \
			 patch("frappe.db.get_value", side_effect=mock_get_value), \
			 patch("frappe.utils.nowdate", return_value="2026-10-10"), \
			 patch("frappe.utils.add_days", return_value="2026-10-13"), \
			 patch("frappe.log_error"), \
			 patch("frappe.get_doc", side_effect=mock_get_doc_fn):

			so_name = order_flow_service._create_sales_order("CUST-1", "ADDR-1", order_doc)
			self.assertEqual(so_name, "SO-100")
			so_data = mock_so_doc._data
			self.assertEqual(so_data["currency"], "USD")
			self.assertEqual(so_data["delivery_date"], "2026-10-13")
			self.assertEqual(len(so_data["items"]), 1)
			self.assertEqual(so_data["items"][0]["item_code"], "SKU-A")
			self.assertEqual(so_data["items"][0]["qty"], 2)
			self.assertEqual(so_data["items"][0]["rate"], 250)
			# Validate that flags.ignore_mandatory was NOT set
			self.assertFalse(getattr(mock_so_doc.flags, "ignore_mandatory", False))
			self.assertNotIn("Channel Message", looked_up, "items come from the order, not the latest chat message")

	def test_sales_order_uses_this_orders_cart_not_a_newer_one(self):
		"""Cart A's address submission must not be billed with cart B's items."""
		order_a = _dict(name="ORD-A", currency="INR", items=[_dict(retailer_id="SKU-A", qty=1, unit_price=100)])
		mock_so_doc = MagicMock()
		mock_so_doc.name = "SO-A"

		def mock_get_doc_fn(*args, **kwargs):
			dt = args[0] if args else None
			if isinstance(dt, dict) and dt.get("doctype") == "Sales Order":
				mock_so_doc._data = dt
				mock_so_doc.flags = _dict()
				return mock_so_doc
			return MagicMock()

		def mock_get_value(doctype, filters=None, fieldname=None, **kwargs):
			return {"Company": "Test Company", "Item": "SKU-A", "Selling Settings": "Std"}.get(doctype)

		with patch("frappe.db.exists", return_value=True), \
			 patch("frappe.db.get_value", side_effect=mock_get_value), \
			 patch("frappe.utils.nowdate", return_value="2026-10-10"), \
			 patch("frappe.utils.add_days", return_value="2026-10-13"), \
			 patch("frappe.log_error"), \
			 patch("frappe.get_doc", side_effect=mock_get_doc_fn):
			order_flow_service._create_sales_order("CUST-1", "ADDR-1", order_a)
		self.assertEqual([i["item_code"] for i in mock_so_doc._data["items"]], ["SKU-A"])

	def test_insert_failure_keeps_order_awaiting_address_with_error(self):
		flow_resp = _dict(flow_token="tok_err", contact_phone="919876543210", conversation="CONV-1")
		resp_data = {"address_line": "123 Main St", "city": "Mumbai", "pincode": "400001"}

		mock_order = MagicMock()
		mock_order.name = "ORD-ERR"
		mock_order.flow_token = "tok_err"
		mock_order.erpnext_sales_order = None
		mock_order.order_status = "Awaiting Address"

		with patch("frappe.db.get_value", return_value="ORD-ERR"), \
			 patch("frappe.get_doc", return_value=mock_order), \
			 patch.object(order_flow_service, "_upsert_customer", return_value="CUST-1"), \
			 patch.object(order_flow_service, "_upsert_address", return_value="ADDR-1"), \
			 patch.object(order_flow_service, "_create_sales_order", side_effect=Exception("Insert failed warehouse missing")), \
			 patch.object(order_flow_service, "_notify_conversation_agent") as mock_notify, \
			 patch("frappe.log_error") as mock_log:
			result = order_flow_service.process_address_flow_response(flow_resp, resp_data)
			self.assertEqual(result, "needs_agent")
			self.assertEqual(mock_order.order_status, "Awaiting Address")
			self.assertIsNone(mock_order.erpnext_sales_order)
			self.assertTrue(mock_order.last_error)
			mock_notify.assert_called_once()
			mock_log.assert_called_once()

	def test_confirmation_sent_only_when_sales_order_created(self):
		flow_resp = _dict(flow_token="tok_no_so", contact_phone="919876543210", conversation="CONV-1")
		resp_data = {"address_line": "123 Main St", "city": "Mumbai", "pincode": "400001"}

		mock_order = MagicMock()
		mock_order.name = "ORD-NOSO"
		mock_order.flow_token = "tok_no_so"
		mock_order.erpnext_sales_order = None
		mock_order.order_status = "Awaiting Address"

		with patch("frappe.db.get_value", return_value="ORD-NOSO"), \
			 patch("frappe.get_doc", return_value=mock_order), \
			 patch.object(order_flow_service, "_upsert_customer", return_value="CUST-1"), \
			 patch.object(order_flow_service, "_upsert_address", return_value="ADDR-1"), \
			 patch.object(order_flow_service, "_create_sales_order", return_value=None), \
			 patch.object(order_flow_service, "_notify_conversation_agent"), \
			 patch("msuite_inbox.inbox.services.outbound.send_message") as mock_send:
			result = order_flow_service.process_address_flow_response(flow_resp, resp_data)
			self.assertEqual(result, "needs_agent")
			mock_send.assert_not_called()



