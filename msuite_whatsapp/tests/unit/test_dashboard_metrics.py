"""
Unit tests for WhatsApp Overview Dashboard metrics:
- Pure rule helper for Aivo facts (ties, empty, single item)
- get_dashboard_metrics (no snapshots, missing permissions, zero sent, unknown category, multiple accounts)
- Derived reply rate edges (zero sent, inbound before/after outbound, multiple inbounds).
"""

import unittest
from unittest.mock import MagicMock, patch

import frappe
from msuite_whatsapp.services.analytics.aivo_facts import get_whatsapp_aivo_facts
from msuite_whatsapp.services.analytics.broadcast_metrics import summarize_status_counts
from msuite_whatsapp.api.v1.app.accounts import get_dashboard_metrics
from msuite_whatsapp.api.v1.app.analytics_query import calculate_reply_rate


class TestSummarizeStatusCounts(unittest.TestCase):
	"""Tests for summarize_status_counts helper in broadcast_metrics."""

	def test_summarize_status_counts_empty_rows(self):
		"""Empty rows return zero counts and None rates."""
		res = summarize_status_counts([])
		self.assertEqual(res["totals"], {"queued": 0, "sent": 0, "delivered": 0, "read": 0, "failed": 0})
		self.assertEqual(res["rates"], {"delivery": None, "read": None})

	def test_summarize_status_counts_only_failed(self):
		"""Only failed messages leave sent count at 0 and rates None."""
		res = summarize_status_counts([{"status": "failed", "count": 5}])
		self.assertEqual(res["totals"]["failed"], 5)
		self.assertEqual(res["totals"]["sent"], 0)
		self.assertEqual(res["rates"], {"delivery": None, "read": None})

	def test_summarize_status_counts_read_without_delivered_rows(self):
		"""Read implies delivered implies sent."""
		res = summarize_status_counts([{"status": "read", "count": 3}])
		self.assertEqual(res["totals"]["read"], 3)
		self.assertEqual(res["totals"]["delivered"], 3)
		self.assertEqual(res["totals"]["sent"], 3)
		self.assertEqual(res["rates"], {"delivery": 1.0, "read": 1.0})

	def test_summarize_status_counts_unknown_status(self):
		"""Unknown statuses are ignored in standard counts and give None rates."""
		res = summarize_status_counts([{"status": "unknown_xyz", "count": 4}])
		self.assertEqual(res["totals"]["sent"], 0)
		self.assertEqual(res["rates"], {"delivery": None, "read": None})

	def test_summarize_status_counts_mixed_case_status(self):
		"""Case insensitive status matching."""
		res = summarize_status_counts([{"status": "Delivered", "count": 2}, {"status": "READ", "count": 1}])
		self.assertEqual(res["totals"]["read"], 1)
		self.assertEqual(res["totals"]["delivered"], 3)
		self.assertEqual(res["totals"]["sent"], 3)
		self.assertEqual(res["rates"]["delivery"], 1.0)
		self.assertAlmostEqual(res["rates"]["read"], 1 / 3)


class TestAivoFactsPureHelper(unittest.TestCase):
	"""Tests for the pure rule-based Aivo facts helper."""

	def test_empty_facts(self):
		"""Empty inputs return has_issues=False and healthy status."""
		facts = get_whatsapp_aivo_facts(
			rejected_templates=[],
			quality_rating="GREEN",
			category_metrics=[],
		)
		self.assertFalse(facts["has_issues"])
		self.assertEqual(facts["title"], "All systems healthy")
		self.assertEqual(len(facts["issues"]), 0)
		self.assertTrue(any(s["value"] == "High" for s in facts["stats"]))

	def test_single_rejected_template(self):
		"""Single rejected template produces Meta rejection issue."""
		rejected = [{"name": "offer_oct", "template_name": "Offer Oct", "rejection_reason": "PROMOTIONAL_CONTENT"}]
		facts = get_whatsapp_aivo_facts(
			rejected_templates=rejected,
			quality_rating="GREEN",
			category_metrics=[],
		)
		self.assertTrue(facts["has_issues"])
		self.assertIn("1 template rejected by Meta", facts["title"])
		self.assertEqual(len(facts["issues"]), 1)
		self.assertEqual(facts["issues"][0]["chip"], "Meta rejection")
		self.assertEqual(facts["issues"][0]["severity"], "danger")
		self.assertEqual(len(facts["issues"][0]["rejects"]), 1)
		self.assertEqual(facts["issues"][0]["rejects"][0]["reason"], "PROMOTIONAL_CONTENT")

	def test_multiple_rejected_templates(self):
		"""Multiple rejected templates pluralize title and list all templates."""
		rejected = [
			{"name": "tpl_1", "template_name": "Tpl 1", "rejection_reason": "INVALID_FORMAT"},
			{"name": "tpl_2", "template_name": "Tpl 2", "rejection_reason": "TAG_VIOLATION"},
		]
		facts = get_whatsapp_aivo_facts(
			rejected_templates=rejected,
			quality_rating="GREEN",
		)
		self.assertTrue(facts["has_issues"])
		self.assertIn("2 templates rejected by Meta", facts["title"])
		self.assertEqual(len(facts["issues"][0]["rejects"]), 2)

	def test_quality_rating_yellow_and_red(self):
		"""Yellow quality rating creates Medium warning; Red creates Critical danger."""
		facts_yellow = get_whatsapp_aivo_facts(quality_rating="YELLOW")
		self.assertTrue(facts_yellow["has_issues"])
		self.assertEqual(facts_yellow["issues"][0]["chip"], "Quality dip")
		self.assertEqual(facts_yellow["issues"][0]["severity"], "warn")

		facts_red = get_whatsapp_aivo_facts(quality_rating="RED")
		self.assertTrue(facts_red["has_issues"])
		self.assertEqual(facts_red["issues"][0]["chip"], "Critical quality")
		self.assertEqual(facts_red["issues"][0]["severity"], "danger")

	def test_lowest_delivery_and_ties(self):
		"""Lowest delivery below 90% flags issue; ties resolve deterministically."""
		# Tie between Marketing and Utility both at 75.0%
		category_metrics = [
			{"category": "Utility", "sent": 100, "delivered": 75, "delivery_rate": 75.0},
			{"category": "Marketing", "sent": 200, "delivered": 150, "delivery_rate": 75.0},
			{"category": "Authentication", "sent": 50, "delivered": 49, "delivery_rate": 98.0},
		]
		facts = get_whatsapp_aivo_facts(
			quality_rating="GREEN",
			category_metrics=category_metrics,
		)
		self.assertTrue(facts["has_issues"])
		delivery_issues = [i for i in facts["issues"] if i["chip"] == "Delivery drop"]
		self.assertEqual(len(delivery_issues), 1)
		# Ties sorted alphabetically: Marketing before Utility
		self.assertIn("Marketing delivery rate is 75.0%", delivery_issues[0]["title"])

	def test_zero_sent_categories_no_delivery_issue(self):
		"""Zero sent messages in categories do not trigger delivery drop issues."""
		category_metrics = [
			{"category": "Marketing", "sent": 0, "delivered": 0, "delivery_rate": 0.0},
			{"category": "Utility", "sent": 0, "delivered": 0, "delivery_rate": 0.0},
		]
		facts = get_whatsapp_aivo_facts(
			quality_rating="GREEN",
			category_metrics=category_metrics,
		)
		self.assertFalse(facts["has_issues"])


class TestDashboardMetrics(unittest.TestCase):
	"""Tests for get_dashboard_metrics endpoint."""

	@patch("frappe.has_permission", return_value=True)
	@patch("frappe.get_list", return_value=[])
	@patch.object(frappe.db, "sql", return_value=[])
	def test_no_analytics_snapshots(self, mock_sql, mock_get_list, mock_perm):
		"""Dashboard runs smoothly when no analytics snapshots or data exist."""
		res = get_dashboard_metrics(period="month")

		self.assertIn("metrics", res)
		self.assertIn("summary", res)
		self.assertIn("category_rollup", res)
		self.assertIn("account_standing", res)
		self.assertIn("delivery_health", res)
		self.assertIn("aivo_facts", res)
		self.assertEqual(res["metrics"]["messagesSent"], 0)
		self.assertEqual(res["summary"]["sent"], 0)
		self.assertEqual(len(res["category_rollup"]), 3)

	@patch("frappe.has_permission")
	@patch("frappe.get_list")
	@patch.object(frappe.db, "sql", return_value=[])
	def test_missing_permission_one_doctype_bug_023(self, mock_sql, mock_get_list, mock_perm):
		"""Missing read permission on one doctype empties only its own section (BUG-023)."""
		def perm_side_effect(doctype, ptype="read"):
			if doctype in ("WhatsApp Flow", "Channel Message"):
				return False
			return True

		mock_perm.side_effect = perm_side_effect

		def get_list_side_effect(doctype, **kwargs):
			if doctype == "WhatsApp Templates":
				if kwargs.get("pluck") == "name":
					return ["tpl_1", "tpl_2"]
				return [
					{
						"name": "tpl_1",
						"template_name": "Tpl 1",
						"status": "APPROVED",
						"category": "MARKETING",
						"total_sent": 50,
						"total_delivered": 45,
						"total_read": 30,
						"rejection_reason": None,
					},
					{
						"name": "tpl_2",
						"template_name": "Tpl 2",
						"status": "APPROVED",
						"category": "UTILITY",
						"total_sent": 20,
						"total_delivered": 18,
						"total_read": 15,
						"rejection_reason": None,
					},
				]
			return []

		mock_get_list.side_effect = get_list_side_effect

		res = get_dashboard_metrics(period="month")

		# Active flows is 0 because permission is missing
		self.assertEqual(res["metrics"]["activeFlows"], 0)
		# Templates are counted and populated
		self.assertEqual(res["metrics"]["templates"], 2)
		self.assertEqual(res["summary"]["templatesApproved"], 2)
		self.assertEqual(res["summary"]["sent"], 70)
		self.assertEqual(res["summary"]["delivered"], 63)

	@patch("frappe.has_permission", return_value=True)
	@patch("frappe.get_list", return_value=[])
	@patch.object(frappe.db, "sql", return_value=[])
	def test_zero_sent_no_division_by_zero(self, mock_sql, mock_get_list, mock_perm):
		"""Zero messages sent returns None rates with no division by zero."""
		res = get_dashboard_metrics(period="month")

		self.assertEqual(res["metrics"]["deliveryRate"], 0)
		self.assertIsNone(res["summary"]["deliveredPct"])
		self.assertIsNone(res["summary"]["readPct"])
		self.assertEqual(res["summary"]["replyPct"], 0.0)
		for cat in res["category_rollup"]:
			self.assertIsNone(cat["delivery_rate"])
			self.assertIsNone(cat["read_rate"])
		self.assertIsNone(res["delivery_health"]["delivered_pct"])
		self.assertIsNone(res["delivery_health"]["read_pct"])
		self.assertIsNone(res["previous_period"]["delivery_rate"])
		self.assertIsNone(res["previous_period"]["read_rate"])

	@patch("frappe.has_permission", return_value=True)
	@patch("frappe.get_list")
	@patch.object(frappe.db, "sql", return_value=[])
	def test_unknown_category_handled(self, mock_sql, mock_get_list, mock_perm):
		"""Templates or messages with unknown categories do not crash."""
		def get_list_side_effect(doctype, **kwargs):
			if doctype == "WhatsApp Templates":
				if kwargs.get("pluck") == "name":
					return ["tpl_unknown"]
				return [
					{
						"name": "tpl_unknown",
						"template_name": "Unknown Category Tpl",
						"status": "APPROVED",
						"category": "CUSTOM_PROMOTIONAL",
						"total_sent": 10,
						"total_delivered": 8,
						"total_read": 5,
						"rejection_reason": None,
					}
				]
			return []

		mock_get_list.side_effect = get_list_side_effect

		res = get_dashboard_metrics(period="month")
		self.assertIn("category_rollup", res)
		cat_names = [c["category"] for c in res["category_rollup"]]
		self.assertIn("Marketing", cat_names)
		self.assertIn("Utility", cat_names)
		self.assertIn("Authentication", cat_names)

	@patch("frappe.has_permission", return_value=True)
	@patch("frappe.get_list", return_value=[])
	@patch.object(frappe.db, "sql")
	def test_multiple_accounts(self, mock_sql, mock_get_list, mock_perm):
		"""Multiple connected accounts surface lowest quality rating or respect account_name."""
		def sql_side_effect(query, *args, **kwargs):
			if "tabWhatsApp Phone Number" in str(query):
				return [
					{
						"quality_rating": "GREEN",
						"messaging_limit_tier": "TIER_10K",
						"is_default_outgoing": 1,
						"status": "Active",
						"account_name": "Account 1",
						"account_id": "ACC-1",
					},
					{
						"quality_rating": "YELLOW",
						"messaging_limit_tier": "TIER_1K",
						"is_default_outgoing": 0,
						"status": "Active",
						"account_name": "Account 2",
						"account_id": "ACC-2",
					},
				]
			return []

		mock_sql.side_effect = sql_side_effect

		res = get_dashboard_metrics(period="month")
		self.assertEqual(res["summary"]["quality"], "Medium")
		self.assertEqual(res["summary"]["tier"], "1K")

	@patch("frappe.has_permission", return_value=True)
	@patch("frappe.get_list")
	@patch.object(frappe.db, "sql")
	def test_current_and_previous_period_split_from_one_query(self, mock_sql, mock_get_list, mock_perm):
		"""Current and previous periods are split from a single query result."""
		def get_list_side_effect(doctype, **kwargs):
			if doctype == "WhatsApp Templates":
				if kwargs.get("pluck") == "name":
					return ["tpl_1"]
				return [
					{
						"name": "tpl_1",
						"template_name": "tpl_promo",
						"category": "MARKETING",
						"status": "APPROVED",
						"total_sent": 0,
						"total_delivered": 0,
						"total_read": 0,
						"rejection_reason": None,
					}
				]
			return []

		mock_get_list.side_effect = get_list_side_effect

		def sql_side_effect(query, params=None, **kwargs):
			q = str(query)
			if "tabChannel Message" in q and "in_current" in q:
				return [
					{"template_name": "tpl_promo", "pricing_category": "", "status": "sent", "in_current": 1, "count": 10},
					{"template_name": "tpl_promo", "pricing_category": "", "status": "delivered", "in_current": 1, "count": 80},
					{"template_name": "tpl_promo", "pricing_category": "", "status": "read", "in_current": 1, "count": 10},
					{"template_name": "tpl_promo", "pricing_category": "", "status": "delivered", "in_current": 0, "count": 30},
					{"template_name": "tpl_promo", "pricing_category": "", "status": "read", "in_current": 0, "count": 20},
				]
			return []

		mock_sql.side_effect = sql_side_effect

		res = get_dashboard_metrics(period="month")
		self.assertEqual(res["summary"]["sent"], 100)
		self.assertEqual(res["summary"]["delivered"], 90)
		self.assertEqual(res["summary"]["read"], 10)
		self.assertEqual(res["summary"]["deliveredPct"], 90.0)
		self.assertEqual(res["summary"]["readPct"], 11.1)

		self.assertEqual(res["previous_period"]["sent"], 50)
		self.assertEqual(res["previous_period"]["delivered"], 50)
		self.assertEqual(res["previous_period"]["read"], 20)
		self.assertEqual(res["previous_period"]["delivery_rate"], 100.0)
		self.assertEqual(res["previous_period"]["read_rate"], 40.0)

	@patch("frappe.has_permission", return_value=True)
	@patch("frappe.get_list")
	@patch.object(frappe.db, "sql")
	def test_rows_on_boundary_second_and_empty_previous_period(self, mock_sql, mock_get_list, mock_perm):
		"""Rows on boundary second with in_current=1 are counted in current, and empty previous period yields None rates."""
		def get_list_side_effect(doctype, **kwargs):
			if doctype == "WhatsApp Templates":
				if kwargs.get("pluck") == "name":
					return ["tpl_1"]
				return [
					{
						"name": "tpl_1",
						"template_name": "tpl_bound",
						"category": "MARKETING",
						"status": "APPROVED",
						"total_sent": 0,
						"total_delivered": 0,
						"total_read": 0,
						"rejection_reason": None,
					}
				]
			return []

		mock_get_list.side_effect = get_list_side_effect

		def sql_side_effect(query, params=None, **kwargs):
			q = str(query)
			if "tabChannel Message" in q and "in_current" in q:
				return [
					{"template_name": "tpl_bound", "pricing_category": "", "status": "read", "in_current": 1, "count": 5},
				]
			return []

		mock_sql.side_effect = sql_side_effect

		res = get_dashboard_metrics(period="month")
		self.assertEqual(res["summary"]["sent"], 5)
		self.assertEqual(res["summary"]["delivered"], 5)
		self.assertEqual(res["summary"]["read"], 5)
		self.assertEqual(res["previous_period"]["sent"], 0)
		self.assertIsNone(res["previous_period"]["delivery_rate"])
		self.assertIsNone(res["previous_period"]["read_rate"])

	@patch("frappe.has_permission", return_value=True)
	@patch("frappe.get_list")
	@patch.object(frappe.db, "sql")
	def test_template_name_mapped_by_name_and_template_name(self, mock_sql, mock_get_list, mock_perm):
		"""Template category is mapped by doc name as well as template_name."""
		def get_list_side_effect(doctype, **kwargs):
			if doctype == "WhatsApp Templates":
				if kwargs.get("pluck") == "name":
					return ["tpl_doc_1", "tpl_doc_2"]
				return [
					{
						"name": "tpl_doc_1",
						"template_name": "meta_tpl_promo",
						"category": "MARKETING",
						"status": "APPROVED",
						"total_sent": 0,
						"total_delivered": 0,
						"total_read": 0,
						"rejection_reason": None,
					},
					{
						"name": "tpl_doc_2",
						"template_name": "meta_tpl_util",
						"category": "UTILITY",
						"status": "APPROVED",
						"total_sent": 0,
						"total_delivered": 0,
						"total_read": 0,
						"rejection_reason": None,
					},
				]
			return []

		mock_get_list.side_effect = get_list_side_effect

		def sql_side_effect(query, params=None, **kwargs):
			q = str(query)
			if "tabChannel Message" in q and "in_current" in q:
				return [
					{"template_name": "tpl_doc_1", "pricing_category": "", "status": "read", "in_current": 1, "count": 10},
					{"template_name": "meta_tpl_util", "pricing_category": "", "status": "read", "in_current": 1, "count": 20},
				]
			return []

		mock_sql.side_effect = sql_side_effect

		res = get_dashboard_metrics(period="month")
		rollup = {c["category"]: c for c in res["category_rollup"]}
		self.assertEqual(rollup["Marketing"]["sent"], 10)
		self.assertEqual(rollup["Marketing"]["read"], 10)
		self.assertEqual(rollup["Utility"]["sent"], 20)
		self.assertEqual(rollup["Utility"]["read"], 20)

	@patch("frappe.has_permission", return_value=True)
	@patch("frappe.get_list")
	@patch.object(frappe.db, "sql")
	def test_one_message_never_counted_twice(self, mock_sql, mock_get_list, mock_perm):
		"""A message matching a template is counted once without double counting."""
		def get_list_side_effect(doctype, **kwargs):
			if doctype == "WhatsApp Templates":
				if kwargs.get("pluck") == "name":
					return ["order_update"]
				return [
					{
						"name": "order_update",
						"template_name": "order_update",
						"category": "UTILITY",
						"status": "APPROVED",
						"total_sent": 0,
						"total_delivered": 0,
						"total_read": 0,
						"rejection_reason": None,
					},
				]
			return []

		mock_get_list.side_effect = get_list_side_effect

		def sql_side_effect(query, params=None, **kwargs):
			q = str(query)
			if "tabChannel Message" in q and "in_current" in q:
				return [
					{"template_name": "order_update", "pricing_category": "", "status": "sent", "in_current": 1, "count": 1},
				]
			return []

		mock_sql.side_effect = sql_side_effect

		res = get_dashboard_metrics(period="month")
		rollup = {c["category"]: c for c in res["category_rollup"]}
		self.assertEqual(rollup["Utility"]["sent"], 1)
		self.assertEqual(res["summary"]["sent"], 1)

	@patch("frappe.has_permission", return_value=True)
	@patch("frappe.get_list")
	@patch.object(frappe.db, "sql")
	def test_unknown_category_goes_to_other_and_left_out_of_rollup(self, mock_sql, mock_get_list, mock_perm):
		"""Unknown category maps to Other and is omitted from the 3 rollup categories."""
		def get_list_side_effect(doctype, **kwargs):
			if doctype == "WhatsApp Templates":
				if kwargs.get("pluck") == "name":
					return ["tpl_weird"]
				return [
					{
						"name": "tpl_weird",
						"template_name": "tpl_weird",
						"category": "NON_STANDARD_CUSTOM",
						"status": "APPROVED",
						"total_sent": 0,
						"total_delivered": 0,
						"total_read": 0,
						"rejection_reason": None,
					},
				]
			return []

		mock_get_list.side_effect = get_list_side_effect

		def sql_side_effect(query, params=None, **kwargs):
			q = str(query)
			if "tabChannel Message" in q and "in_current" in q:
				return [
					{"template_name": "tpl_weird", "pricing_category": "", "status": "sent", "in_current": 1, "count": 5},
				]
			return []

		mock_sql.side_effect = sql_side_effect

		res = get_dashboard_metrics(period="month")
		rollup_categories = [c["category"] for c in res["category_rollup"]]
		self.assertEqual(rollup_categories, ["Marketing", "Utility", "Authentication"])
		for cat in res["category_rollup"]:
			self.assertEqual(cat["sent"], 0)
			self.assertIsNone(cat["delivery_rate"])


class TestReplyRateDerivedQuery(unittest.TestCase):
	"""Tests for derived reply rate and conversations opened in analytics_query."""

	@patch("frappe.has_permission", return_value=False)
	def test_reply_rate_missing_permission(self, mock_perm):
		"""Missing permission returns 0s without throwing."""
		res = calculate_reply_rate()
		self.assertEqual(res["contacts_messaged"], 0)
		self.assertEqual(res["contacts_replied"], 0)
		self.assertEqual(res["reply_rate"], 0.0)
		self.assertEqual(res["conversations_opened"], 0)

	@patch("frappe.has_permission", return_value=True)
	@patch.object(frappe.db, "sql", return_value=[])
	def test_reply_rate_zero_sent(self, mock_sql, mock_perm):
		"""Zero contacts messaged returns 0.0 reply rate."""
		res = calculate_reply_rate(start_datetime="2026-11-01 00:00:00", end_datetime="2026-11-05 23:59:59")
		self.assertEqual(res["contacts_messaged"], 0)
		self.assertEqual(res["contacts_replied"], 0)
		self.assertEqual(res["reply_rate"], 0.0)

	@patch("frappe.has_permission", return_value=True)
	@patch.object(frappe.db, "sql")
	def test_reply_rate_edges_inbound_after_outbound(self, mock_sql, mock_perm):
		"""Contacts replying after an outbound are counted towards reply rate."""
		mock_sql.side_effect = [
			[
				{"contact_id": "contact_A", "first_out_time": "2026-11-02 10:00:00"},
				{"contact_id": "contact_B", "first_out_time": "2026-11-02 11:00:00"},
			],
			[{"replied_count": 1}],
		]

		res = calculate_reply_rate(start_datetime="2026-11-01 00:00:00", end_datetime="2026-11-05 23:59:59")
		self.assertEqual(res["contacts_messaged"], 2)
		self.assertEqual(res["contacts_replied"], 1)
		self.assertEqual(res["reply_rate"], 50.0)
		self.assertEqual(res["conversations_opened"], 1)
