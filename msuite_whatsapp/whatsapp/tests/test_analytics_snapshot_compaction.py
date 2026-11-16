"""Tests for WhatsApp Analytics Snapshot compaction and upsert on snapshot_key (C1/C2).

All HTTP is mocked or avoided; no network or LLM calls.
"""

import json
from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days

from msuite_whatsapp.constants import MM_PRODUCT_TYPE
from msuite_whatsapp.utils.insight_keys import make_key
from msuite_whatsapp.constants import (
	MM_METRICS_RETENTION_DAYS,
	AnalyticsGranularity,
	MetricType,
)
from msuite_whatsapp.services.analytics import mm_sync, sync

DOCTYPE_SNAPSHOT = "WhatsApp Analytics Snapshot"
DOCTYPE_METRIC = "WhatsApp Marketing Metric"
ACCOUNT_1 = "Compaction-Test-Acc-1"
ACCOUNT_2 = "Compaction-Test-Acc-2"
TODAY = date(2026, 10, 20)


class TestAnalyticsSnapshotCompaction(IntegrationTestCase):
	"""Test suite for WhatsApp Analytics Snapshot compaction and upsert behaviour."""

	@classmethod
	def setUpClass(cls):
		"""Ensure test WhatsApp accounts exist."""
		super().setUpClass()
		for acc_name in (ACCOUNT_1, ACCOUNT_2):
			if not frappe.db.exists("WhatsApp Account", acc_name):
				doc = frappe.get_doc({
					"doctype": "WhatsApp Account",
					"account_name": acc_name,
					"waba_id": f"waba-{acc_name}",
					"status": "Active",
					"phone_number": "+1234567890",
					"display_phone_number": "+1234567890",
				})
				doc.flags.ignore_permissions = True
				doc.flags.ignore_links = True
				doc.insert()

	@classmethod
	def tearDownClass(cls):
		"""Clean up test WhatsApp accounts."""
		for acc_name in (ACCOUNT_1, ACCOUNT_2):
			if frappe.db.exists("WhatsApp Account", acc_name):
				frappe.delete_doc("WhatsApp Account", acc_name, force=True, ignore_permissions=True)
		super().tearDownClass()

	def setUp(self):
		"""Clean up test records before each test."""
		super().setUp()
		frappe.db.delete(DOCTYPE_SNAPSHOT, {"whatsapp_account": ("in", [ACCOUNT_1, ACCOUNT_2])})
		frappe.db.delete(DOCTYPE_METRIC, {"whatsapp_account": ("in", [ACCOUNT_1, ACCOUNT_2])})
		frappe.db.commit()

	def tearDown(self):
		"""Clean up test records after each test."""
		frappe.db.delete(DOCTYPE_SNAPSHOT, {"whatsapp_account": ("in", [ACCOUNT_1, ACCOUNT_2])})
		frappe.db.delete(DOCTYPE_METRIC, {"whatsapp_account": ("in", [ACCOUNT_1, ACCOUNT_2])})
		frappe.db.commit()
		super().tearDown()

	def test_sync_twice_leaves_one_snapshot_per_metric_type(self):
		"""Syncing twice for the same account, metric_type, and granularity leaves exactly 1 row."""
		data1 = {"messaging": {"sent": 10}}
		data2 = {"messaging": {"sent": 25}}

		sync._save_snapshot(
			ACCOUNT_1,
			MetricType.MESSAGING,
			"2026-10-01",
			"2026-10-07",
			AnalyticsGranularity.DAY,
			data1,
		)
		sync._save_snapshot(
			ACCOUNT_1,
			MetricType.MESSAGING,
			"2026-10-01",
			"2026-10-07",
			AnalyticsGranularity.DAY,
			data2,
		)

		count = frappe.db.count(
			DOCTYPE_SNAPSHOT,
			{"whatsapp_account": ACCOUNT_1, "metric_type": MetricType.MESSAGING},
		)
		self.assertEqual(count, 1)

	def test_second_sync_updates_raw_data_and_synced_at(self):
		"""A second sync updates raw_data and synced_at rather than inserting a duplicate."""
		data1 = {"conversations": [{"count": 5}]}
		data2 = {"conversations": [{"count": 12}]}

		sync._save_snapshot(
			ACCOUNT_1,
			MetricType.CONVERSATION,
			"2026-10-01",
			"2026-10-07",
			AnalyticsGranularity.DAY,
			data1,
		)

		row_before = frappe.db.get_value(
			DOCTYPE_SNAPSHOT,
			{"whatsapp_account": ACCOUNT_1, "metric_type": MetricType.CONVERSATION},
			["name", "raw_data", "synced_at"],
			as_dict=True,
		)
		self.assertEqual(json.loads(row_before.raw_data), data1)

		# Sync again with updated data and distinct timestamp
		sync._save_snapshot(
			ACCOUNT_1,
			MetricType.CONVERSATION,
			"2026-10-01",
			"2026-10-07",
			AnalyticsGranularity.DAY,
			data2,
		)

		row_after = frappe.db.get_value(
			DOCTYPE_SNAPSHOT,
			{"whatsapp_account": ACCOUNT_1, "metric_type": MetricType.CONVERSATION},
			["name", "raw_data", "synced_at"],
			as_dict=True,
		)
		# Same document was updated
		self.assertEqual(row_before.name, row_after.name)
		self.assertEqual(json.loads(row_after.raw_data), data2)
		self.assertGreaterEqual(row_after.synced_at, row_before.synced_at)

	def test_window_change_updates_period_columns_not_new_row(self):
		"""Rolling window shift overwrites period_start and period_end in place without adding a row."""
		data1 = {"pricing": {"cost": 1.5}}
		data2 = {"pricing": {"cost": 2.0}}

		sync._save_snapshot(
			ACCOUNT_1,
			MetricType.PRICING,
			"2026-10-01",
			"2026-10-07",
			AnalyticsGranularity.DAY,
			data1,
		)
		sync._save_snapshot(
			ACCOUNT_1,
			MetricType.PRICING,
			"2026-10-02",
			"2026-10-08",
			AnalyticsGranularity.DAY,
			data2,
		)

		count = frappe.db.count(
			DOCTYPE_SNAPSHOT,
			{"whatsapp_account": ACCOUNT_1, "metric_type": MetricType.PRICING},
		)
		self.assertEqual(count, 1)

		row = frappe.db.get_value(
			DOCTYPE_SNAPSHOT,
			{"whatsapp_account": ACCOUNT_1, "metric_type": MetricType.PRICING},
			["period_start", "period_end", "raw_data"],
			as_dict=True,
		)
		self.assertEqual(str(row.period_start), "2026-10-02")
		self.assertEqual(str(row.period_end), "2026-10-08")
		self.assertEqual(json.loads(row.raw_data), data2)

	def test_two_accounts_do_not_share_a_snapshot(self):
		"""Snapshots for different WhatsApp accounts have distinct keys and separate rows."""
		data1 = {"calls": 3}
		data2 = {"calls": 7}

		sync._save_snapshot(
			ACCOUNT_1,
			MetricType.CALL,
			"2026-10-01",
			"2026-10-07",
			AnalyticsGranularity.DAY,
			data1,
		)
		sync._save_snapshot(
			ACCOUNT_2,
			MetricType.CALL,
			"2026-10-01",
			"2026-10-07",
			AnalyticsGranularity.DAY,
			data2,
		)

		count_1 = frappe.db.count(
			DOCTYPE_SNAPSHOT,
			{"whatsapp_account": ACCOUNT_1, "metric_type": MetricType.CALL},
		)
		count_2 = frappe.db.count(
			DOCTYPE_SNAPSHOT,
			{"whatsapp_account": ACCOUNT_2, "metric_type": MetricType.CALL},
		)
		self.assertEqual(count_1, 1)
		self.assertEqual(count_2, 1)

		key_1 = frappe.db.get_value(
			DOCTYPE_SNAPSHOT,
			{"whatsapp_account": ACCOUNT_1, "metric_type": MetricType.CALL},
			"snapshot_key",
		)
		key_2 = frappe.db.get_value(
			DOCTYPE_SNAPSHOT,
			{"whatsapp_account": ACCOUNT_2, "metric_type": MetricType.CALL},
			"snapshot_key",
		)
		expected_1 = make_key(ACCOUNT_1, MetricType.CALL, AnalyticsGranularity.DAY)
		expected_2 = make_key(ACCOUNT_2, MetricType.CALL, AnalyticsGranularity.DAY)
		self.assertEqual(key_1, expected_1)
		self.assertEqual(key_2, expected_2)
		self.assertNotEqual(key_1, key_2)

	def test_concurrent_insert_falls_back_to_update(self):
		"""Simulate concurrent worker insert collision falling back to update."""
		data1 = {"templates": [{"name": "t1", "cost": 1.0}]}
		sync._save_snapshot(
			ACCOUNT_1,
			MetricType.TEMPLATE,
			"2026-10-01",
			"2026-10-07",
			AnalyticsGranularity.DAY,
			data1,
		)

		data2 = {"templates": [{"name": "t1", "cost": 3.5}]}
		real_get_value = frappe.db.get_value
		call_count = {"count": 0}

		def fake_get_value(doctype, filters, fieldname=None, **kwargs):
			if doctype == DOCTYPE_SNAPSHOT and isinstance(filters, dict) and "snapshot_key" in filters:
				call_count["count"] += 1
				if call_count["count"] == 1:
					return None
			return real_get_value(doctype, filters, fieldname=fieldname, **kwargs)

		with patch("frappe.db.get_value", side_effect=fake_get_value):
			sync._save_snapshot(
				ACCOUNT_1,
				MetricType.TEMPLATE,
				"2026-10-02",
				"2026-10-08",
				AnalyticsGranularity.DAY,
				data2,
			)

		self.assertEqual(
			frappe.db.count(
				DOCTYPE_SNAPSHOT,
				{"whatsapp_account": ACCOUNT_1, "metric_type": MetricType.TEMPLATE},
			),
			1,
		)
		row = frappe.db.get_value(
			DOCTYPE_SNAPSHOT,
			{"whatsapp_account": ACCOUNT_1, "metric_type": MetricType.TEMPLATE},
			["period_start", "period_end", "raw_data"],
			as_dict=True,
		)
		self.assertEqual(str(row.period_start), "2026-10-02")
		self.assertEqual(str(row.period_end), "2026-10-08")
		self.assertEqual(json.loads(row.raw_data), data2)

	def test_prune_removes_rows_older_than_retention(self):
		"""Verify prune_old_marketing_metrics deletes rows older than MM_METRICS_RETENTION_DAYS."""
		cutoff = add_days(TODAY, -MM_METRICS_RETENTION_DAYS)
		keep_date = cutoff
		drop_date = add_days(cutoff, -1)

		def _insert_metric(m_date):
			doc = frappe.get_doc({
				"doctype": DOCTYPE_METRIC,
				"whatsapp_account": ACCOUNT_1,
				"template_id": "test_tmpl_1",
				"metric_date": m_date,
				"product_type": MM_PRODUCT_TYPE,
				"sent": 10,
				"delivered": 10,
			})
			doc.flags.ignore_links = True
			doc.save(ignore_permissions=True)

		_insert_metric(keep_date)
		_insert_metric(drop_date)

		with patch("msuite_whatsapp.services.analytics.mm_sync._today", return_value=TODAY):
			removed = mm_sync.prune_old_marketing_metrics()

		self.assertGreaterEqual(removed, 1)
		self.assertTrue(
			frappe.db.exists(
				DOCTYPE_METRIC,
				{"whatsapp_account": ACCOUNT_1, "metric_date": keep_date},
			)
		)
		self.assertFalse(
			frappe.db.exists(
				DOCTYPE_METRIC,
				{"whatsapp_account": ACCOUNT_1, "metric_date": drop_date},
			)
		)

	def test_patch_dedupes_unkeyed_snapshots_and_backfills_snapshot_key(self):
		"""Patch backfills snapshot_key and retains the newest row among legacy duplicates."""
		from msuite_whatsapp.patches.whatsapp_compact_analytics_snapshots import execute as run_patch

		doc1 = frappe.get_doc({
			"doctype": DOCTYPE_SNAPSHOT,
			"whatsapp_account": ACCOUNT_1,
			"metric_type": MetricType.MESSAGING,
			"granularity": AnalyticsGranularity.DAY,
			"period_start": "2026-10-01",
			"period_end": "2026-10-07",
			"raw_data": json.dumps({"legacy": 1}),
			"synced_at": "2026-10-07 10:00:00",
		})
		doc1.flags.ignore_links = True
		doc1.insert(ignore_permissions=True)
		frappe.db.set_value(DOCTYPE_SNAPSHOT, doc1.name, "snapshot_key", None, update_modified=False)

		doc2 = frappe.get_doc({
			"doctype": DOCTYPE_SNAPSHOT,
			"whatsapp_account": ACCOUNT_1,
			"metric_type": MetricType.MESSAGING,
			"granularity": AnalyticsGranularity.DAY,
			"period_start": "2026-10-02",
			"period_end": "2026-10-08",
			"raw_data": json.dumps({"legacy": 2}),
			"synced_at": "2026-10-08 10:00:00",
		})
		doc2.flags.ignore_links = True
		doc2.insert(ignore_permissions=True)
		frappe.db.set_value(DOCTYPE_SNAPSHOT, doc2.name, "snapshot_key", None, update_modified=False)
		frappe.db.commit()

		run_patch()

		rows = frappe.get_all(
			DOCTYPE_SNAPSHOT,
			filters={"whatsapp_account": ACCOUNT_1, "metric_type": MetricType.MESSAGING},
			fields=["name", "snapshot_key", "raw_data"],
		)
		self.assertEqual(len(rows), 1)
		expected_key = make_key(ACCOUNT_1, MetricType.MESSAGING, AnalyticsGranularity.DAY)
		self.assertEqual(rows[0].snapshot_key, expected_key)
		self.assertEqual(rows[0].name, doc2.name)
		self.assertEqual(json.loads(rows[0].raw_data), {"legacy": 2})

	def test_before_save_populates_snapshot_key_if_empty(self):
		"""WhatsAppAnalyticsSnapshot document hook before_save fills snapshot_key if empty."""
		doc = frappe.get_doc({
			"doctype": DOCTYPE_SNAPSHOT,
			"whatsapp_account": ACCOUNT_1,
			"metric_type": MetricType.CALL,
			"granularity": AnalyticsGranularity.DAY,
			"period_start": "2026-10-01",
			"period_end": "2026-10-07",
			"raw_data": json.dumps({"test": 1}),
			"synced_at": "2026-10-07 10:00:00",
		})
		doc.flags.ignore_links = True
		doc.insert(ignore_permissions=True)

		expected_key = make_key(ACCOUNT_1, MetricType.CALL, AnalyticsGranularity.DAY)
		self.assertEqual(doc.snapshot_key, expected_key)

