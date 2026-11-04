"""
Marketing Messages metrics sync (mm_sync.py). All Meta HTTP is mocked; no network or LLM calls.

Needs the `WhatsApp Marketing Metric` table (migrate done on mc.localhost).
"""

import json
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import frappe
import requests
from frappe.tests import IntegrationTestCase

from msuite_core.constants import MM_PRODUCT_TYPE
from msuite_whatsapp.constants import (
	ANALYTICS_BACKFILL_DAYS,
	ANALYTICS_REFETCH_DAYS,
	CLOUD_API_PRODUCT_TYPE,
	META_READ_CLICK_RETENTION_DAYS,
	MM_METRICS_RETENTION_DAYS,
	MM_SYNC_PRODUCT_TYPES,
	MM_SYNC_SKIP_DISABLED,
	MM_SYNC_SKIP_NO_TEMPLATES,
	MM_SYNC_SKIP_NOT_AVAILABLE,
	MM_SYNC_SKIP_RATE_LIMITED,
	MM_SYNC_SKIP_REAUTH,
	MM_SYNC_SKIP_REQUEST_FAILED,
	MM_SYNC_SKIP_PERMISSION,
	TEMPLATE_ANALYTICS_BATCH_SIZE,
	TEMPLATE_ANALYTICS_MAX_LOOKBACK_DAYS,
	WABA_UTC_OFFSET_FIELD,
	WABA_UTC_OFFSET_SYNCED_FIELD,
)
from msuite_whatsapp.services.analytics import mm_sync, sync

MM = "msuite_whatsapp.services.analytics.mm_sync"
SYNC = "msuite_whatsapp.services.analytics.sync"
TOKEN = "EAAB-secret-token-xyz"
ACCOUNT = "MM-Sync-Test-Account"
WABA = "waba-1"
TODAY = date(2026, 10, 20)
DOCTYPE = "WhatsApp Marketing Metric"


def _resp(body, status=200):
	"""Fake requests.Response."""
	resp = MagicMock()
	resp.status_code = status
	if isinstance(body, Exception):
		resp.json.side_effect = body
	else:
		resp.json.return_value = body
	return resp


def _payload(template_id, day_ts=1790000000, **point):
	"""A template_analytics body with one data point."""
	return {"data": [{"granularity": "DAILY", "data_points": [{"template_id": template_id, "start": day_ts, "sent": 5, **point}]}]}


def _by_type(**per_type):
	"""requests.get side_effect answering by the request's product_type (MM / CLOUD keys); default empty data."""
	table = {MM_PRODUCT_TYPE: per_type.get("mm"), CLOUD_API_PRODUCT_TYPE: per_type.get("cloud")}

	def _respond(url, params=None, **kw):
		return table[params["product_type"]] or _resp({"data": []})

	return {"side_effect": _respond}


def _templates(n):
	"""n marketing templates as {meta_id: doc_name}."""
	return {str(1000 + i): f"tpl-{i}" for i in range(n)}


class _Env:
	"""Context manager patching everything mm_sync touches except Meta HTTP (patched per test)."""

	def __init__(self, templates=None, gate=True, first_run=False):
		self.templates = _templates(1) if templates is None else templates
		self.gate = gate
		self.first_run = first_run

	def __enter__(self):
		self.patches = [
			patch(f"{MM}._get_waba_id", return_value=WABA),
			patch(f"{MM}._is_enabled", return_value=self.gate),
			patch(f"{MM}._get_credentials", return_value=(WABA, TOKEN)),
			patch(f"{MM}._get_marketing_templates", return_value=self.templates),
			patch(f"{MM}._has_rows", return_value=not self.first_run),
			patch(f"{MM}._today", return_value=TODAY),
			patch(f"{MM}._upsert_metric_row", return_value="inserted"),
			patch(f"{MM}.frappe.db.commit"),
		]
		self.m = [p.start() for p in self.patches]
		self.upsert = self.m[6]
		self.commit = self.m[7]
		return self

	def __exit__(self, *exc):
		for p in self.patches:
			p.stop()


class TestSyncFlow(unittest.TestCase):
	def _run(self, env, get_kwargs, **kw):
		with patch(f"{SYNC}.requests.get", **get_kwargs) as get, patch(f"{SYNC}.set_reauth_flag") as flag:
			out = mm_sync.sync_marketing_metrics(ACCOUNT, **kw)
		return out, get, flag

	def test_gate_off_makes_no_call(self):
		with _Env(gate=False) as env:
			out, get, _ = self._run(env, {"return_value": _resp({})})
		get.assert_not_called()
		self.assertEqual(out["skipped"], MM_SYNC_SKIP_DISABLED)
		self.assertEqual(out["rows"], 0)

	def test_no_templates_makes_no_call(self):
		with _Env(templates={}) as env:
			out, get, _ = self._run(env, {"return_value": _resp({})})
		get.assert_not_called()
		self.assertEqual(out["skipped"], MM_SYNC_SKIP_NO_TEMPLATES)

	def test_batching_boundaries(self):
		size = TEMPLATE_ANALYTICS_BATCH_SIZE
		cases = {0: [], 1: [1], size: [size], size + 1: [size, 1], 2 * size + 5: [size, size, 5]}
		for n, expected in cases.items():
			with self.subTest(n=n), _Env(templates=_templates(n)) as env:
				_, get, _ = self._run(env, {"return_value": _resp({"data": []})})
				sizes = [len(c.kwargs["params"]["template_ids"].strip("[]").split(",")) for c in get.call_args_list]
				self.assertEqual(sizes, expected * len(MM_SYNC_PRODUCT_TYPES))

	def test_exact_params_and_token_only_in_header(self):
		with _Env() as env:
			_, get, _ = self._run(env, {"return_value": _resp({"data": []})})
		kw = get.call_args_list[0].kwargs
		params = kw["params"]
		self.assertEqual(params["product_type"], MM_PRODUCT_TYPE)
		self.assertEqual(get.call_args_list[1].kwargs["params"]["product_type"], CLOUD_API_PRODUCT_TYPE)
		self.assertEqual(params["granularity"], "DAILY")
		self.assertEqual(params["metric_types"], "SENT,DELIVERED,READ,CLICKED,COST")
		self.assertEqual(params["template_ids"], "[1000]")
		self.assertEqual(params["use_waba_timezone"], "true")
		self.assertNotIn("access_token", params)
		self.assertEqual(kw["headers"]["Authorization"], f"Bearer {TOKEN}")
		self.assertNotIn(TOKEN, str(get.call_args_list[0].args) + str(params))
		self.assertTrue(get.call_args_list[0].args[0].endswith(f"/{WABA}/template_analytics"))

	def test_window_first_run_vs_daily_vs_clamped(self):
		cases = [(True, None, ANALYTICS_BACKFILL_DAYS), (False, None, ANALYTICS_REFETCH_DAYS),
			(False, 10**6, TEMPLATE_ANALYTICS_MAX_LOOKBACK_DAYS), (False, -5, 1), (False, 0, ANALYTICS_REFETCH_DAYS)]
		for first, days, expected in cases:
			with self.subTest(first=first, days=days), _Env(first_run=first) as env:
				_, get, _ = self._run(env, {"return_value": _resp({"data": []})}, days=days)
				p = get.call_args.kwargs["params"]
				span = (date.fromisoformat(p["end"]) - date.fromisoformat(p["start"])).days
				self.assertEqual(span, expected)
				self.assertEqual(p["end"], str(TODAY))

	def test_rows_upserted_and_committed_once(self):
		with _Env(templates=_templates(25)) as env:
			body = _payload("1000")
			out, get, _ = self._run(env, {"return_value": _resp(body)})
			self.assertEqual(get.call_count, 3 * len(MM_SYNC_PRODUCT_TYPES))
			self.assertEqual(env.commit.call_count, 1)
			self.assertEqual(out["rows"], 2)  # id 1000 is in batch 1 of each product type; other batches hold no row for it
			self.assertEqual(env.upsert.call_args.args[0]["template"], "tpl-0")

	def test_unknown_template_ids_in_response_ignored(self):
		with _Env() as env:
			out, _, _ = self._run(env, {"return_value": _resp(_payload("999999"))})
		self.assertEqual(out["rows"], 0)
		env.upsert.assert_not_called()

	def test_401_flags_reauth_and_writes_nothing(self):
		with _Env(templates=_templates(25)) as env:
			out, get, flag = self._run(env, {"return_value": _resp({"error": {"message": "bad", "code": 190}}, 401)})
		flag.assert_called_once()
		self.assertTrue(flag.call_args.kwargs["needs_reauth"])
		self.assertEqual(get.call_count, 1)
		env.upsert.assert_not_called()
		self.assertEqual(out["skipped"], MM_SYNC_SKIP_REAUTH)
		self.assertNotIn(TOKEN, str(out))

	def test_403_reports_scope_once_no_reauth_no_rows(self):
		with _Env(templates=_templates(25)) as env:
			out, get, flag = self._run(env, {"return_value": _resp({"error": {"message": "no scope", "code": 200}}, 403)})
		flag.assert_not_called()
		env.upsert.assert_not_called()
		self.assertEqual(get.call_count, 1)
		self.assertEqual(len(out["errors"]), 1)
		self.assertEqual(out["skipped"], MM_SYNC_SKIP_PERMISSION)

	def test_400_skips_as_mm_not_available(self):
		with _Env(templates=_templates(25)) as env:
			out, get, _ = self._run(env, {"return_value": _resp({"error": {"message": "bad product_type", "code": 100}}, 400)})
		self.assertEqual(out["skipped"], MM_SYNC_SKIP_NOT_AVAILABLE)
		self.assertEqual(get.call_count, len(MM_SYNC_PRODUCT_TYPES))  # each type tried once, then its series stops
		env.upsert.assert_not_called()

	def test_429_and_throttle_code_stop_without_retry(self):
		for resp in (_resp({}, 429), _resp({"error": {"message": "slow", "code": 80008}}, 400)):
			with self.subTest(resp=resp.status_code), _Env(templates=_templates(25)) as env:
				out, get, _ = self._run(env, {"return_value": resp})
				self.assertEqual(get.call_count, 1)
				self.assertEqual(out["skipped"], MM_SYNC_SKIP_RATE_LIMITED)

	def test_timeout_connection_and_non_json_skip_account_without_raising(self):
		cases = [{"side_effect": requests.Timeout(f"t {TOKEN}")}, {"side_effect": requests.ConnectionError("c")},
			{"return_value": _resp(ValueError("no json"))}]
		for kwargs in cases:
			with self.subTest(kwargs=str(kwargs)[:40]), _Env(templates=_templates(25)) as env:
				out, get, _ = self._run(env, kwargs)
				self.assertEqual(get.call_count, 1)
				self.assertEqual(out["skipped"], MM_SYNC_SKIP_REQUEST_FAILED)
				self.assertNotIn(TOKEN, str(out))

	def test_error_body_with_200_is_recorded_and_next_batch_continues(self):
		responses = [_resp({"error": {"message": "odd", "code": 1}}), _resp(_payload("1010"))]
		with _Env(templates=_templates(25)) as env:
			out, get, _ = self._run(env, {"side_effect": responses + [_resp({"data": []})] * 4})
		self.assertEqual(get.call_count, 3 * len(MM_SYNC_PRODUCT_TYPES))
		self.assertEqual(len(out["errors"]), 1)
		self.assertEqual(out["rows"], 1)

	def test_data_null_is_not_an_error(self):
		with _Env() as env:
			out, _, _ = self._run(env, {"return_value": _resp({"data": None})})
		self.assertEqual(out, {"rows": 0, "skipped": None, "errors": []})

	def test_partial_failure_keeps_good_rows(self):
		with _Env(templates=_templates(15)) as env:
			out, _, _ = self._run(env, {"side_effect": [_resp(_payload("1000")), _resp({"error": {"message": "x", "code": 1}}, 500)] + [_resp({"data": []})] * 2})
		self.assertEqual(out["rows"], 1)
		self.assertEqual(len(out["errors"]), 1)
		self.assertEqual(env.commit.call_count, 1)

	def test_rows_are_tagged_with_the_requesting_product_type(self):
		mm, cloud = _resp(_payload("1000", sent=3)), _resp(_payload("1000", sent=4))
		with _Env() as env:
			out, get, _ = self._run(env, _by_type(mm=mm, cloud=cloud))
		tagged = {c.args[0]["product_type"]: c.args[0]["sent"] for c in env.upsert.call_args_list}
		self.assertEqual(tagged, {MM_PRODUCT_TYPE: 3, CLOUD_API_PRODUCT_TYPE: 4})
		self.assertEqual(out, {"rows": 2, "skipped": None, "errors": []})

	def test_400_for_one_product_type_keeps_the_other(self):
		refused = _resp({"error": {"message": "bad product_type", "code": 100}}, 400)
		for refused_key, kept_key, kept_type in (("mm", "cloud", CLOUD_API_PRODUCT_TYPE), ("cloud", "mm", MM_PRODUCT_TYPE)):
			with self.subTest(refused=refused_key), _Env(templates=_templates(25)) as env:
				out, get, _ = self._run(env, _by_type(**{refused_key: refused, kept_key: _resp(_payload("1000"))}))
				self.assertIsNone(out["skipped"])
				self.assertEqual(out["rows"], 1)
				self.assertEqual(len(out["errors"]), 1)
				self.assertEqual(env.upsert.call_args.args[0]["product_type"], kept_type)
				self.assertEqual(get.call_count, 1 + 3)  # refused series stops after its first batch

	def test_one_product_type_empty_still_syncs_the_other(self):
		with _Env() as env:
			out, _, _ = self._run(env, _by_type(cloud=_resp(_payload("1000"))))
		self.assertEqual(out["rows"], 1)
		self.assertEqual(env.upsert.call_args.args[0]["product_type"], CLOUD_API_PRODUCT_TYPE)

	def test_401_on_first_type_stops_the_account_before_the_second_type(self):
		with _Env() as env:
			out, get, flag = self._run(env, {"return_value": _resp({"error": {"message": "bad", "code": 190}}, 401)})
		self.assertEqual(get.call_count, 1)
		self.assertEqual(out["skipped"], MM_SYNC_SKIP_REAUTH)
		env.upsert.assert_not_called()

	def test_401_on_second_type_keeps_first_type_rows_and_stops(self):
		with _Env() as env:
			out, get, _ = self._run(env, _by_type(mm=_resp(_payload("1000")), cloud=_resp({"error": {"message": "bad", "code": 190}}, 401)))
		self.assertEqual(out["rows"], 1)
		self.assertEqual(out["skipped"], MM_SYNC_SKIP_REAUTH)

	def test_400_on_first_type_then_throttle_on_second_reports_throttle(self):
		refused = _resp({"error": {"message": "x", "code": 100}}, 400)
		with _Env() as env:
			out, _, _ = self._run(env, _by_type(mm=refused, cloud=_resp({}, 429)))
		self.assertEqual(out["skipped"], MM_SYNC_SKIP_RATE_LIMITED)
		self.assertEqual(len(out["errors"]), 2)

	def test_product_type_constants(self):
		self.assertEqual(MM_SYNC_PRODUCT_TYPES, (MM_PRODUCT_TYPE, CLOUD_API_PRODUCT_TYPE))
		self.assertNotEqual(MM_PRODUCT_TYPE, CLOUD_API_PRODUCT_TYPE)


KOLKATA_STARTS = (1791916200, 1792002600, 1792089000)  # local midnights 2026-10-14..16 in UTC+5:30 (live capture)


def _starts_payload(template_id, starts):
	"""A template_analytics body with one point per unix `start`."""
	return {"data": [{"data_points": [{"template_id": template_id, "start": s, "sent": 1} for s in starts]}]}


class TestUtcOffsetFlow(unittest.TestCase):
	"""sync_marketing_metrics derives the WABA UTC offset from the `start` values and stores it."""

	def _sync(self, body, **kw):
		with _Env() as env, patch(f"{MM}._store_utc_offset") as store, patch(
			f"{SYNC}.requests.get", **_by_type(mm=_resp(body), cloud=kw.get("cloud"))
		):
			out = mm_sync.sync_marketing_metrics(ACCOUNT)
		return out, store

	def test_offset_derived_and_stored(self):
		_, store = self._sync(_starts_payload("1000", KOLKATA_STARTS))
		store.assert_called_once_with(ACCOUNT, 330)

	def test_garbage_payload_passes_none(self):
		_, store = self._sync(_starts_payload("1000", (7, 12345)))
		store.assert_called_once_with(ACCOUNT, None)

	def test_offset_read_across_product_types(self):
		_, store = self._sync(_starts_payload("1000", KOLKATA_STARTS[:1]), cloud=_resp(_starts_payload("1000", KOLKATA_STARTS[1:])))
		store.assert_called_once_with(ACCOUNT, 330)

	def test_failed_batch_contributes_nothing(self):
		with _Env() as env, patch(f"{MM}._store_utc_offset") as store, patch(
			f"{SYNC}.requests.get", **_by_type(mm=_resp({"error": {"code": 1}}, 500), cloud=_resp(_starts_payload("1000", KOLKATA_STARTS)))
		):
			mm_sync.sync_marketing_metrics(ACCOUNT)
		store.assert_called_once_with(ACCOUNT, 330)

	def test_disabled_account_never_stores(self):
		with _Env(gate=False), patch(f"{MM}._store_utc_offset") as store:
			mm_sync.sync_marketing_metrics(ACCOUNT)
		store.assert_not_called()


class TestStoreUtcOffset(unittest.TestCase):
	"""_store_utc_offset persists only a derived, changed value, and tolerates a non-migrated site."""

	def _store(self, offset, current=(None, None), has_column=True):
		with patch(f"{MM}.frappe.db.has_column", return_value=has_column) as col, patch(
			f"{MM}.frappe.db.get_value", return_value=current
		) as get, patch(f"{MM}.frappe.db.set_value") as setv:
			result = mm_sync._store_utc_offset(ACCOUNT, offset)
		return result, col, get, setv

	def test_none_does_nothing(self):
		result, col, get, setv = self._store(None)
		self.assertFalse(result)
		col.assert_not_called()
		setv.assert_not_called()

	def test_column_missing_is_tolerated(self):
		result, _, get, setv = self._store(330, has_column=False)
		self.assertFalse(result)
		get.assert_not_called()
		setv.assert_not_called()

	def test_first_value_is_written_with_timestamp(self):
		result, _, _, setv = self._store(330)
		self.assertTrue(result)
		(doctype, name, values), kwargs = setv.call_args
		self.assertEqual((doctype, name), ("WhatsApp Account", ACCOUNT))
		self.assertEqual(values[WABA_UTC_OFFSET_FIELD], 330)
		self.assertIn(WABA_UTC_OFFSET_SYNCED_FIELD, values)
		self.assertFalse(kwargs.get("update_modified", True))

	def test_utc_zero_is_written_when_never_derived(self):
		# A stored 0 without a synced stamp is the Int default, not a derived UTC reading.
		result, _, _, setv = self._store(0, current=(0, None))
		self.assertTrue(result)
		self.assertEqual(setv.call_args.args[2][WABA_UTC_OFFSET_FIELD], 0)

	def test_unchanged_value_is_not_rewritten(self):
		for offset in (330, 0, -210):
			with self.subTest(offset=offset):
				result, _, _, setv = self._store(offset, current=(offset, "2026-10-19 00:00:00"))
				self.assertFalse(result)
				setv.assert_not_called()

	def test_changed_value_is_rewritten(self):
		result, _, _, setv = self._store(345, current=(330, "2026-10-19 00:00:00"))
		self.assertTrue(result)
		self.assertEqual(setv.call_args.args[2][WABA_UTC_OFFSET_FIELD], 345)

	def test_missing_account_row_is_tolerated(self):
		result, _, _, setv = self._store(330, current=None)
		self.assertFalse(result)
		setv.assert_not_called()


class TestShouldOverwrite(unittest.TestCase):
	OLD = str(date(2026, 10, 20).replace(day=20 - META_READ_CLICK_RETENTION_DAYS - 3))
	RECENT = "2026-10-18"

	def _check(self, day, field, existing, new):
		return mm_sync._should_overwrite({"metric_date": day, field: existing}, {field: new}, TODAY, field)

	def test_old_row_never_lowered_or_zeroed(self):
		for field in ("read", "clicked", "quick_reply_clicked"):
			with self.subTest(field=field):
				self.assertFalse(self._check(self.OLD, field, 50, 0))
				self.assertFalse(self._check(self.OLD, field, 50, 49))
				self.assertTrue(self._check(self.OLD, field, 50, 51))

	def test_recent_row_may_be_corrected_down(self):
		self.assertTrue(self._check(self.RECENT, "read", 50, 40))
		self.assertTrue(self._check(self.RECENT, "read", 50, 60))

	def test_boundary_day(self):
		on_edge = str(date.fromordinal(TODAY.toordinal() - META_READ_CLICK_RETENTION_DAYS))
		past_edge = str(date.fromordinal(TODAY.toordinal() - META_READ_CLICK_RETENTION_DAYS - 1))
		self.assertTrue(self._check(on_edge, "read", 50, 0))
		self.assertFalse(self._check(past_edge, "read", 50, 0))

	def test_sent_and_cost_always_update_when_reported(self):
		for field in ("sent", "delivered", "amount_spent"):
			self.assertTrue(self._check(self.OLD, field, 50, 0))

	def test_unreported_never_overwrites(self):
		self.assertFalse(self._check(self.RECENT, "read", 50, None))


class TestUpsertAndPrune(IntegrationTestCase):
	def setUp(self):
		frappe.db.delete(DOCTYPE, {"whatsapp_account": ACCOUNT})

	def tearDown(self):
		frappe.db.delete(DOCTYPE, {"whatsapp_account": ACCOUNT})

	def _row(self, **kw):
		row = {"whatsapp_account": ACCOUNT, "template_id": "t1", "template": None, "metric_date": "2026-10-18", "product_type": MM_PRODUCT_TYPE, "sent": 10,
			"delivered": 9, "read": 5, "clicked": None, "quick_reply_clicked": None, "amount_spent": None,
			"cost_per_delivered": None, "cost_per_click": None, "purchase_value": None, "conversions": {},
			"clicks_supported": False, "conversions_available": False}
		row.update(kw)
		return row

	def _get(self, day="2026-10-18", product_type=MM_PRODUCT_TYPE):
		return frappe.db.get_value(DOCTYPE, {"whatsapp_account": ACCOUNT, "template_id": "t1", "metric_date": day, "product_type": product_type},
			["sent", "read", "unavailable_fields"], as_dict=True)

	def test_insert_then_idempotent_update(self):
		with patch(f"{MM}._today", return_value=TODAY):
			self.assertEqual(mm_sync._upsert_metric_row(self._row()), "inserted")
			self.assertEqual(mm_sync._upsert_metric_row(self._row(sent=11)), "updated")
		self.assertEqual(frappe.db.count(DOCTYPE, {"whatsapp_account": ACCOUNT}), 1)
		self.assertEqual(self._get().sent, 11)
		self.assertIn("clicked", self._get().unavailable_fields)

	def test_same_key_other_product_type_is_a_separate_row(self):
		with patch(f"{MM}._today", return_value=TODAY):
			self.assertEqual(mm_sync._upsert_metric_row(self._row(sent=3)), "inserted")
			self.assertEqual(mm_sync._upsert_metric_row(self._row(sent=4, product_type=CLOUD_API_PRODUCT_TYPE)), "inserted")
			self.assertEqual(mm_sync._upsert_metric_row(self._row(sent=5, product_type=CLOUD_API_PRODUCT_TYPE)), "updated")
		self.assertEqual(frappe.db.count(DOCTYPE, {"whatsapp_account": ACCOUNT}), 2)
		self.assertEqual(self._get().sent, 3)
		self.assertEqual(self._get(product_type=CLOUD_API_PRODUCT_TYPE).sent, 5)

	def test_old_row_read_reset_by_meta_is_ignored(self):
		with patch(f"{MM}._today", return_value=TODAY):
			mm_sync._upsert_metric_row(self._row(metric_date="2026-10-01", read=50))
			mm_sync._upsert_metric_row(self._row(metric_date="2026-10-01", read=0, sent=12))
		got = self._get("2026-10-01")
		self.assertEqual((got.read, got.sent), (50, 12))

	def test_recent_row_updates_read(self):
		with patch(f"{MM}._today", return_value=TODAY):
			mm_sync._upsert_metric_row(self._row(read=50))
			mm_sync._upsert_metric_row(self._row(read=60))
		self.assertEqual(self._get().read, 60)

	def test_field_unavailable_first_later_real_zero_clears_it(self):
		with patch(f"{MM}._today", return_value=TODAY):
			mm_sync._upsert_metric_row(self._row(read=None))
			self.assertIn("read", json.loads(self._get().unavailable_fields))
			mm_sync._upsert_metric_row(self._row(read=0))
			self.assertNotIn("read", json.loads(self._get().unavailable_fields))

	def test_currency_written_on_insert_and_update_and_none_when_unknown(self):
		with patch(f"{MM}._today", return_value=TODAY):
			# Insert with currency
			mm_sync._upsert_metric_row(self._row(currency="EUR"))
			doc = frappe.db.get_value(DOCTYPE, {"whatsapp_account": ACCOUNT, "template_id": "t1"}, ["currency"], as_dict=True)
			self.assertEqual(doc.currency, "EUR")

			# Update with new currency
			mm_sync._upsert_metric_row(self._row(currency="USD"))
			doc = frappe.db.get_value(DOCTYPE, {"whatsapp_account": ACCOUNT, "template_id": "t1"}, ["currency"], as_dict=True)
			self.assertEqual(doc.currency, "USD")

		# Insert with genuinely unknown currency leaves it blank (not default like INR)
		frappe.db.delete(DOCTYPE, {"whatsapp_account": ACCOUNT})
		with patch(f"{MM}._today", return_value=TODAY):
			mm_sync._upsert_metric_row(self._row(currency=None))
			doc = frappe.db.get_value(DOCTYPE, {"whatsapp_account": ACCOUNT, "template_id": "t1"}, ["currency"], as_dict=True)
			self.assertIsNone(doc.currency)

	def test_conversions_only_change_triggers_update(self):
		with patch(f"{MM}._today", return_value=TODAY):
			self.assertEqual(mm_sync._upsert_metric_row(self._row(conversions={})), "inserted")
			# A conversion-only change should return 'updated'
			self.assertEqual(mm_sync._upsert_metric_row(self._row(conversions={"ADD_TO_CART": 2})), "updated")
			conv = frappe.db.get_value(DOCTYPE, {"whatsapp_account": ACCOUNT, "template_id": "t1"}, "conversions")
			self.assertEqual(json.loads(conv), {"ADD_TO_CART": 2})

			# Same conversions (order independent) returns 'unchanged'
			self.assertEqual(mm_sync._upsert_metric_row(self._row(conversions={"ADD_TO_CART": 2})), "unchanged")

	def test_concurrent_insert_duplicate_entry_re_fetches_and_updates(self):
		# Pre-create the row in DB to simulate another worker inserting concurrently
		with patch(f"{MM}._today", return_value=TODAY):
			self.assertEqual(mm_sync._upsert_metric_row(self._row(sent=10)), "inserted")

		# Now simulate a concurrent race: get_value returns None at first, but insert raises DuplicateEntryError
		real_get_value = frappe.db.get_value
		call_count = {"count": 0}

		def fake_get_value(doctype, filters, fieldname=None, **kwargs):
			if doctype == DOCTYPE and isinstance(filters, dict) and filters.get("whatsapp_account") == ACCOUNT:
				call_count["count"] += 1
				if call_count["count"] == 1:
					return None  # First call simulates row not found initially
			return real_get_value(doctype, filters, fieldname=fieldname, **kwargs)

		with patch(f"{MM}._today", return_value=TODAY), patch("frappe.db.get_value", side_effect=fake_get_value):
			# Should recover from DuplicateEntryError, re-fetch, apply update, and return 'updated'
			result = mm_sync._upsert_metric_row(self._row(sent=15))
			self.assertEqual(result, "updated")
			self.assertEqual(self._get().sent, 15)

	def test_prune_boundary(self):
		keep = str(date.fromordinal(TODAY.toordinal() - MM_METRICS_RETENTION_DAYS))
		drop = str(date.fromordinal(TODAY.toordinal() - MM_METRICS_RETENTION_DAYS - 1))
		with patch(f"{MM}._today", return_value=TODAY):
			mm_sync._upsert_metric_row(self._row(metric_date=keep))
			mm_sync._upsert_metric_row(self._row(metric_date=drop))
			mm_sync.prune_old_marketing_metrics()
		self.assertTrue(self._get(keep))
		self.assertFalse(self._get(drop))

	def test_prune_empty_is_noop(self):
		with patch(f"{MM}._today", return_value=TODAY):
			mm_sync.prune_old_marketing_metrics()


class TestWiring(unittest.TestCase):
	def test_not_whitelisted(self):
		for fn in (mm_sync.sync_marketing_metrics, mm_sync.prune_old_marketing_metrics):
			self.assertNotIn(fn, frappe.whitelisted)

	def test_daily_tasks_call_mm_sync_and_prune_continues_after_failure(self):
		accounts = [frappe._dict(name="A"), frappe._dict(name="B")]
		with patch(f"{SYNC}.is_feature_enabled", return_value=True), patch(f"{SYNC}._get_active_accounts", return_value=accounts), \
			patch(f"{SYNC}.sync_template_analytics"), patch(f"{SYNC}.cleanup_old_snapshots"), \
			patch(f"{SYNC}.time.sleep") as sleep, patch(f"{MM}.sync_marketing_metrics", side_effect=[RuntimeError("x"), {}]) as run, \
			patch(f"{MM}.prune_old_marketing_metrics") as prune:
			sync.sync_daily_tasks()
		self.assertEqual([c.args[0] for c in run.call_args_list], ["A", "B"])
		sleep.assert_called_once()
		prune.assert_called_once()

	def test_manual_refresh_checks_permissions_first_and_syncs_mm(self):
		with patch(f"{SYNC}.check_read", side_effect=frappe.PermissionError("no")), patch(f"{MM}.sync_marketing_metrics") as run:
			with self.assertRaises(frappe.PermissionError):
				sync.refresh_account_analytics(ACCOUNT)
		run.assert_not_called()
		with patch(f"{SYNC}.check_read"), patch(f"{SYNC}.check_feature_or_throw"), patch(f"{SYNC}.sync_all"), \
			patch(f"{SYNC}.sync_template_analytics"), patch(f"{MM}.sync_marketing_metrics") as run:
			out = sync.refresh_account_analytics(ACCOUNT)
		run.assert_called_once_with(ACCOUNT)
		self.assertEqual(out["status"], "success")
