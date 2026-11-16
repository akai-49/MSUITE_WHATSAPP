"""
Marketing Messages metrics query API (whatsapp/analytics/query.py) and the insights
`marketing_lite` totals. Real test-DB rows for WhatsApp Marketing Metric; permission and
account resolution are patched; no network or LLM calls.
"""

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from msuite_whatsapp.constants import MM_PRODUCT_TYPE
from msuite_whatsapp.constants import WHATSAPP_PRICING_CATEGORY_MARKETING_LITE
from msuite_whatsapp.constants import (
	CLOUD_API_PRODUCT_TYPE,
	MM_METRICS_RETENTION_DAYS,
	MM_TEMPLATE_ROWS_LIMIT,
)
from msuite_whatsapp.api.v1.app import analytics_query as query

DOCTYPE = "WhatsApp Marketing Metric"
ACCOUNT = "MM-Query-Test-Account"
OTHER_ACCOUNT = "MM-Query-Other-Account"
Q = "msuite_whatsapp.api.v1.app.analytics_query"


def _day(offset=0):
	"""ISO date `offset` days from today."""
	return str(add_days(today(), offset))


def _row(template_id="t1", metric_date=None, account=ACCOUNT, product_type=MM_PRODUCT_TYPE, **overrides):
	"""Insert one metric row (account link validation skipped); None values become unavailable."""
	values = {
		"doctype": DOCTYPE,
		"whatsapp_account": account,
		"product_type": product_type,
		"template_id": template_id,
		"metric_date": metric_date or _day(0),
		"sent": 10,
		"delivered": 8,
		"read": 4,
		"clicked": 2,
		"quick_reply_clicked": 1,
		"currency": "INR",
	}
	values.update(overrides)
	doc = frappe.get_doc(values)
	doc.flags.ignore_links = True
	return doc.insert(ignore_permissions=True)


class _Base(IntegrationTestCase):
	def setUp(self):
		"""Clean rows; patch permission check and account resolution."""
		for acc in (ACCOUNT, OTHER_ACCOUNT):
			frappe.db.delete(DOCTYPE, {"whatsapp_account": acc})
		self.perm = patch(f"{Q}._require_analytics_read").start()
		patch(f"{Q}._resolve_account_name", side_effect=lambda a=None, l=None: (a or ACCOUNT, [])).start()
		self.addCleanup(patch.stopall)

	def tearDown(self):
		"""Remove created rows."""
		for acc in (ACCOUNT, OTHER_ACCOUNT):
			frappe.db.delete(DOCTYPE, {"whatsapp_account": acc})


class TestSummary(_Base):
	def test_sums_rates_and_period(self):
		_row("t1", _day(0))
		_row("t2", _day(-1), sent=30, delivered=12, read=6, clicked=3, quick_reply_clicked=0)
		out = query.get_marketing_metrics_summary(ACCOUNT, 7)
		self.assertEqual(out["totals"], {"sent": 40, "delivered": 20, "read": 10, "clicked": 5, "quick_reply_clicked": 1})
		self.assertEqual(out["rates"], {"delivery_rate": 50.0, "read_rate": 50.0, "click_rate": 25.0})
		self.assertEqual(out["period"]["days"], 7)
		self.assertEqual(out["period"]["end"], _day(0))
		self.assertTrue(out["has_data"])

	def test_permission_checked_first(self):
		self.perm.side_effect = frappe.PermissionError("denied")
		with patch(f"{Q}.frappe.db.sql") as sql, self.assertRaises(frappe.PermissionError):
			query.get_marketing_metrics_summary(ACCOUNT)
		sql.assert_not_called()

	def test_no_rows_gives_none_not_zero(self):
		out = query.get_marketing_metrics_summary(ACCOUNT, 30)
		self.assertFalse(out["has_data"])
		self.assertTrue(all(v is None for v in out["totals"].values()))
		self.assertTrue(all(v is None for v in out["rates"].values()))
		self.assertEqual(out["cost"], [])

	def test_unavailable_fields_are_null_not_zero(self):
		_row(clicked=None, quick_reply_clicked=None)
		out = query.get_marketing_metrics_summary(ACCOUNT)
		self.assertIsNone(out["totals"]["clicked"])
		self.assertIsNone(out["totals"]["quick_reply_clicked"])
		self.assertIsNone(out["rates"]["click_rate"])
		self.assertEqual(out["totals"]["sent"], 10)

	def test_unavailable_on_one_day_sums_only_reported_days(self):
		_row("t1", _day(0), clicked=None)
		_row("t1", _day(-1), clicked=5)
		self.assertEqual(query.get_marketing_metrics_summary(ACCOUNT)["totals"]["clicked"], 5)

	def test_zero_denominators_give_none_rates(self):
		_row(sent=0, delivered=0, read=0, clicked=0, quick_reply_clicked=0)
		rates = query.get_marketing_metrics_summary(ACCOUNT)["rates"]
		self.assertEqual(rates, {"delivery_rate": None, "read_rate": None, "click_rate": None})
		self.assertEqual(query.get_marketing_metrics_summary(ACCOUNT)["totals"]["sent"], 0)

	def test_currencies_are_never_summed(self):
		_row("t1", amount_spent=10, currency="INR", delivered=5)
		_row("t2", amount_spent=3, currency="USD", delivered=3)
		_row("t3", _day(-1), amount_spent=2, currency="INR", delivered=1)
		cost = {c["currency"]: c for c in query.get_marketing_metrics_summary(ACCOUNT)["cost"]}
		self.assertEqual(set(cost), {"INR", "USD"})
		self.assertEqual(cost["INR"]["amount_spent"], 12)
		self.assertEqual(cost["USD"]["amount_spent"], 3)
		self.assertAlmostEqual(cost["INR"]["cost_per_delivered"], 2.0)
		self.assertAlmostEqual(cost["USD"]["cost_per_delivered"], 1.0)

	def test_unavailable_cost_is_none_and_zero_delivered_cost_per_none(self):
		_row("t1", amount_spent=None, currency="INR")
		_row("t2", amount_spent=5, delivered=0, currency="USD")
		cost = {c["currency"]: c for c in query.get_marketing_metrics_summary(ACCOUNT)["cost"]}
		self.assertIsNone(cost["INR"]["amount_spent"])
		self.assertIsNone(cost["INR"]["cost_per_delivered"])
		self.assertEqual(cost["USD"]["amount_spent"], 5)
		self.assertIsNone(cost["USD"]["cost_per_delivered"])

	def test_other_account_and_out_of_window_rows_excluded(self):
		_row("t1", _day(0))
		_row("t1", _day(-10), sent=1000)
		_row("t9", _day(0), account=OTHER_ACCOUNT, sent=1000)
		self.assertEqual(query.get_marketing_metrics_summary(ACCOUNT, 3)["totals"]["sent"], 10)

	def test_days_clamped(self):
		for raw, expected in ((0, 1), (-5, 1), (10**6, MM_METRICS_RETENTION_DAYS), ("abc", 30), (None, 30), ("7", 7), (3.9, 3)):
			with self.subTest(raw=raw):
				self.assertEqual(query.get_marketing_metrics_summary(ACCOUNT, raw)["period"]["days"], expected)

	def test_window_boundary_inclusive(self):
		_row("t1", _day(0))
		_row("t1", _day(-2), sent=5)  # days=3 -> today, -1, -2
		_row("t1", _day(-3), sent=100)
		self.assertEqual(query.get_marketing_metrics_summary(ACCOUNT, 3)["totals"]["sent"], 15)

	def test_conversions_summed_and_flags(self):
		_row("t1", _day(0), conversions_available=1, conversions=json.dumps({"WEBSITE_PURCHASES": 2}))
		_row("t2", _day(0), conversions_available=1, conversions=json.dumps({"WEBSITE_PURCHASES": 3, "APP_LEAD": 1}))
		out = query.get_marketing_metrics_summary(ACCOUNT)
		self.assertEqual(out["conversions"], {"WEBSITE_PURCHASES": 5, "APP_LEAD": 1})
		self.assertTrue(out["conversions_available"])

	def test_conversions_none_when_not_available_or_malformed(self):
		_row("t1", _day(0))
		out = query.get_marketing_metrics_summary(ACCOUNT)
		self.assertIsNone(out["conversions"])
		self.assertFalse(out["conversions_available"])
		_row("t2", _day(0), conversions_available=1, conversions="{not json")
		self.assertEqual(query.get_marketing_metrics_summary(ACCOUNT)["conversions"], {})

	def test_injection_account_is_a_plain_value(self):
		_row()
		out = query.get_marketing_metrics_summary("x' OR '1'='1", 7)
		self.assertFalse(out["has_data"])
		self.assertTrue(frappe.db.exists(DOCTYPE, {"whatsapp_account": ACCOUNT}))

	def test_no_account_resolved(self):
		with patch(f"{Q}._resolve_account_name", return_value=(None, [])):
			out = query.get_marketing_metrics_summary(None)
		self.assertFalse(out["has_data"])
		self.assertIsNone(out["account"])

	def test_unicode_template_id_and_clicks_supported_flag(self):
		_row("तmpl-😀", clicks_supported=1)
		self.assertTrue(query.get_marketing_metrics_summary(ACCOUNT)["clicks_supported"])


class TestTrend(_Base):
	def test_one_entry_per_day_with_data_sorted_no_zero_fill(self):
		_row("t1", _day(-2))
		_row("t2", _day(-2), sent=5)
		_row("t1", _day(0), clicked=None)
		out = query.get_marketing_metrics_trend(ACCOUNT, 7)
		self.assertEqual([p["date"] for p in out], [_day(-2), _day(0)])
		self.assertEqual(out[0]["sent"], 15)
		self.assertIsNone(out[1]["clicked"])
		self.assertEqual(out[1]["delivered"], 8)

	def test_trend_cost_per_currency(self):
		_row("t1", amount_spent=4, currency="INR")
		_row("t2", amount_spent=1, currency="USD")
		cost = {c["currency"]: c["amount_spent"] for c in query.get_marketing_metrics_trend(ACCOUNT)[0]["cost"]}
		self.assertEqual(cost, {"INR": 4, "USD": 1})

	def test_trend_empty_permission_and_clamp(self):
		self.assertEqual(query.get_marketing_metrics_trend(ACCOUNT), [])
		self.perm.side_effect = frappe.PermissionError("denied")
		with self.assertRaises(frappe.PermissionError):
			query.get_marketing_metrics_trend(ACCOUNT)

	def test_trend_days_clamped(self):
		_row("t1", _day(-MM_METRICS_RETENTION_DAYS - 5))
		self.assertEqual(query.get_marketing_metrics_trend(ACCOUNT, 10**9), [])


class TestByTemplate(_Base):
	def test_groups_per_template_with_rates(self):
		_row("t1", _day(0))
		_row("t1", _day(-1))
		_row("t2", _day(0), sent=4, delivered=0, read=0, clicked=0)
		out = query.get_marketing_metrics_by_template(ACCOUNT)
		self.assertFalse(out["truncated"])
		rows = {r["template_id"]: r for r in out["templates"]}
		self.assertEqual(rows["t1"]["sent"], 20)
		self.assertEqual(rows["t1"]["delivery_rate"], 80.0)
		self.assertIsNone(rows["t2"]["read_rate"])
		self.assertEqual(out["templates"][0]["template_id"], "t1")  # ordered by sent desc

	def test_template_with_unavailable_clicks(self):
		_row("t1", clicked=None)
		row = query.get_marketing_metrics_by_template(ACCOUNT)["templates"][0]
		self.assertIsNone(row["clicked"])
		self.assertIsNone(row["click_rate"])

	def test_row_limit_and_truncated_flag(self):
		with patch(f"{Q}.MM_TEMPLATE_ROWS_LIMIT", 2):
			for i in range(3):
				_row(f"t{i}", sent=10 + i)
			out = query.get_marketing_metrics_by_template(ACCOUNT)
			self.assertEqual(len(out["templates"]), 2)
			self.assertTrue(out["truncated"])
			self.assertEqual([r["template_id"] for r in out["templates"]], ["t2", "t1"])
		self.assertGreater(MM_TEMPLATE_ROWS_LIMIT, 0)

	def test_exactly_at_limit_not_truncated(self):
		with patch(f"{Q}.MM_TEMPLATE_ROWS_LIMIT", 2):
			_row("a")
			_row("b")
			self.assertFalse(query.get_marketing_metrics_by_template(ACCOUNT)["truncated"])

	def test_currency_split_and_conversions_per_template(self):
		_row("t1", _day(0), amount_spent=2, currency="INR", conversions_available=1, conversions=json.dumps({"WEBSITE_PURCHASES": 1}))
		_row("t1", _day(-1), amount_spent=3, currency="USD", conversions_available=1, conversions=json.dumps({"WEBSITE_PURCHASES": 2}))
		row = query.get_marketing_metrics_by_template(ACCOUNT)["templates"][0]
		self.assertEqual({c["currency"]: c["amount_spent"] for c in row["cost"]}, {"INR": 2, "USD": 3})
		self.assertEqual(row["conversions"], {"WEBSITE_PURCHASES": 3})
		self.assertEqual(row["sent"], 20)

	def test_empty_and_permission(self):
		self.assertEqual(query.get_marketing_metrics_by_template(ACCOUNT), {"templates": [], "truncated": False})
		self.perm.side_effect = frappe.PermissionError("denied")
		with self.assertRaises(frappe.PermissionError):
			query.get_marketing_metrics_by_template(ACCOUNT)

	def test_constant_query_count(self):
		_row("t1")
		real = frappe.db.sql
		query.get_marketing_metrics_by_template(ACCOUNT)  # warm meta caches
		counts = []
		for n in (1, 40):
			for i in range(n):
				if not frappe.db.exists(DOCTYPE, {"whatsapp_account": ACCOUNT, "template_id": f"n{i}"}):
					_row(f"n{i}")
			calls = []
			with patch.object(frappe.db, "sql", side_effect=lambda *a, **k: (calls.append(1), real(*a, **k))[1]):
				with patch(f"{Q}.frappe.get_all", wraps=frappe.get_all) as ga:
					query.get_marketing_metrics_by_template(ACCOUNT)
			counts.append(len(calls) + ga.call_count)
		self.assertEqual(counts[0], counts[1])


class TestMarketingLiteTotals(IntegrationTestCase):
	def _insights(self, counts):
		"""Run get_whatsapp_account_insights with all I/O patched and the pricing counts stubbed."""
		with (
			patch(f"{Q}._require_analytics_read"),
			patch(f"{Q}._resolve_account_name", return_value=("Acc", [])),
			patch(f"{Q}.frappe.get_doc", side_effect=frappe.DoesNotExistError),
			patch(f"{Q}.frappe.log_error"),
			patch(f"{Q}.frappe.db.count", return_value=0),
			patch(f"{Q}.frappe.db.sql", return_value=[]),
			patch(f"{Q}.get_template_performance", return_value=[]),
			patch(f"{Q}.get_error_breakdown", return_value=[]),
			patch(f"{Q}._get_pricing_category_counts", return_value=counts),
		):
			return query.get_whatsapp_account_insights("Acc", 7)["totals"]

	def test_none_when_no_message_carries_a_category(self):
		totals = self._insights(None)
		self.assertIsNone(totals["delivered_by_category"]["marketing_lite"])
		self.assertIsNone(totals["paid_messages"]["marketing_lite"])
		self.assertIsNone(totals["approximate_charges"]["marketing_lite"])

	def test_real_counts_when_messages_carry_category(self):
		lite = WHATSAPP_PRICING_CATEGORY_MARKETING_LITE
		totals = self._insights({"delivered": {lite: 7}, "paid": {lite: 9}})
		self.assertEqual(totals["delivered_by_category"]["marketing_lite"], 7)
		self.assertEqual(totals["paid_messages"]["marketing_lite"], 9)
		self.assertIsNone(totals["approximate_charges"]["marketing_lite"])

	def test_real_zero_when_other_categories_present_but_no_lite(self):
		totals = self._insights({"delivered": {"marketing": 3}, "paid": {"marketing": 3}})
		self.assertEqual(totals["delivered_by_category"]["marketing_lite"], 0)
		self.assertEqual(totals["paid_messages"]["marketing_lite"], 0)

	def test_counts_helper_groups_and_returns_none_for_empty(self):
		lite = WHATSAPP_PRICING_CATEGORY_MARKETING_LITE
		rows = [
			{"pricing_category": lite, "status": "read", "c": 2},
			{"pricing_category": lite, "status": "sent", "c": 1},
			{"pricing_category": lite, "status": "failed", "c": 4},
			{"pricing_category": "marketing", "status": "delivered", "c": 5},
		]
		with patch(f"{Q}.frappe.db.sql", return_value=rows) as sql:
			out = query._get_pricing_category_counts("Acc", "2026-01-01")
		self.assertEqual(out, {"delivered": {lite: 2, "marketing": 5}, "paid": {lite: 3, "marketing": 5}})
		self.assertEqual(sql.call_args[0][1], ("Acc", "2026-01-01"))
		with patch(f"{Q}.frappe.db.sql", return_value=[]):
			self.assertIsNone(query._get_pricing_category_counts("Acc", "2026-01-01"))

	def test_counts_helper_db_error_returns_none(self):
		with patch(f"{Q}.frappe.db.sql", side_effect=Exception("db down")), patch(f"{Q}.frappe.log_error"):
			self.assertIsNone(query._get_pricing_category_counts("Acc", "2026-01-01"))


class TestOnlyMmLiteRowsAreShown(_Base):
	"""The Insights Marketing Messages panel keeps showing MM-Lite data only (Cloud API rows are for broadcast attribution)."""

	def test_summary_ignores_cloud_api_rows(self):
		_row("t1", _day(0))
		_row("t1", _day(0), product_type=CLOUD_API_PRODUCT_TYPE, sent=999, delivered=999, read=999, clicked=99)
		out = query.get_marketing_metrics_summary(ACCOUNT, 7)
		self.assertEqual(out["totals"]["sent"], 10)
		self.assertEqual(out["totals"]["clicked"], 2)

	def test_cloud_api_only_account_has_no_data(self):
		_row("t1", _day(0), product_type=CLOUD_API_PRODUCT_TYPE)
		self.assertFalse(query.get_marketing_metrics_summary(ACCOUNT, 7)["has_data"])
		self.assertEqual(query.get_marketing_metrics_trend(ACCOUNT, 7), [])
		self.assertEqual(query.get_marketing_metrics_by_template(ACCOUNT, 7)["templates"], [])

	def test_trend_and_by_template_ignore_cloud_api_rows(self):
		_row("t1", _day(0))
		_row("t1", _day(0), product_type=CLOUD_API_PRODUCT_TYPE, sent=500)
		self.assertEqual(query.get_marketing_metrics_trend(ACCOUNT, 7)[0]["sent"], 10)
		self.assertEqual(query.get_marketing_metrics_by_template(ACCOUNT, 7)["templates"][0]["sent"], 10)

	def test_conversions_ignore_cloud_api_rows(self):
		_row("t1", _day(0), conversions_available=1, conversions=json.dumps({"p": 1}))
		_row("t1", _day(0), product_type=CLOUD_API_PRODUCT_TYPE, conversions_available=1, conversions=json.dumps({"p": 50}))
		self.assertEqual(query.get_marketing_metrics_summary(ACCOUNT, 7)["conversions"], {"p": 1})


class TestProductTypeFilterIsInTheQueries(IntegrationTestCase):
	"""Pure checks (no product_type column needed): the queries are scoped to MM-Lite."""

	def test_group_query_binds_mm_product_type(self):
		with patch(f"{Q}.frappe.db.sql", return_value=[]) as sql:
			query._mm_group_rows(ACCOUNT, "2026-10-01", "2026-10-20", ["currency"])
		text, params = sql.call_args.args
		self.assertIn("product_type = %(product_type)s", text)
		self.assertEqual(params["product_type"], MM_PRODUCT_TYPE)

	def test_conversions_query_filters_mm_product_type(self):
		with patch(f"{Q}.frappe.get_all", return_value=[]) as get_all:
			query._mm_sum_conversions(ACCOUNT, "2026-10-01", "2026-10-20")
		self.assertEqual(get_all.call_args.kwargs["filters"]["product_type"], MM_PRODUCT_TYPE)


class TestAnalyticsReadPermissionResolution(IntegrationTestCase):
	"""Addressing an account by phone number or index must check permissions on the resolved account."""

	def test_phone_number_without_permission_on_resolved_account_raises_permission_error(self):
		phone = "+19998887777"
		resolved = "WA-SECRET-ACCOUNT"

		def mock_has_permission(doctype, ptype="read", doc=None, user=None):
			if doctype == "WhatsApp Analytics Snapshot":
				return True
			if doctype == "WhatsApp Account":
				if doc == resolved:
					return False  # user has no permission on this specific document
				if doc is None:
					return True  # user has doctype-level read permission
			return True

		with (
			patch(f"{Q}._resolve_account_name", return_value=(resolved, [{"name": resolved, "phone_number": phone}])),
			patch(f"{Q}.frappe.db.exists", side_effect=lambda dt, val: val == resolved),
			patch("msuite_core.services.permissions.checks.frappe.has_permission", side_effect=mock_has_permission),
		):
			with self.assertRaises(frappe.PermissionError):
				query._require_analytics_read(phone)

			with self.assertRaises(frappe.PermissionError):
				query.get_marketing_metrics_summary(phone)

			with self.assertRaises(frappe.PermissionError):
				query.get_marketing_metrics_trend(phone)

			with self.assertRaises(frappe.PermissionError):
				query.get_marketing_metrics_by_template(phone)

	def test_user_with_permission_on_resolved_account_succeeds(self):
		phone = "+19998887777"
		resolved = "WA-ALLOWED-ACCOUNT"

		with (
			patch(f"{Q}._resolve_account_name", return_value=(resolved, [{"name": resolved, "phone_number": phone}])),
			patch(f"{Q}.frappe.db.exists", return_value=True),
			patch("msuite_core.services.permissions.checks.frappe.has_permission", return_value=True),
		):
			# Should not raise
			query._require_analytics_read(phone)
