"""
Per-broadcast / per-campaign metrics (roadmap 5.3, D2). No network or LLM calls; DB loaders are
patched, the SQL itself is covered by the targeted run against mc.localhost where noted.
"""

import json
from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from msuite_whatsapp.constants import MM_BROADCAST_ROWS_LIMIT
from msuite_whatsapp.services.analytics import broadcast_metrics as bm
from msuite_whatsapp.api.v1.app import bulk_messages as api

D1, D2 = date(2026, 10, 1), date(2026, 10, 2)
MOD = "msuite_whatsapp.services.analytics.broadcast_metrics"


def _metric(sent, clicked=3, clicks_supported=1, conversions_available=0, unavailable=(), **kw):
	return {
		"sent": sent, "delivered": sent, "read": 1, "clicked": clicked, "quick_reply_clicked": 0,
		"amount_spent": 5.0, "currency": "INR", "conversions": "{}",
		"unavailable_fields": json.dumps(list(unavailable)),
		"clicks_supported": clicks_supported, "conversions_available": conversions_available, **kw,
	}


def _rows(**counts):
	"""Grouped Channel Message rows: _rows(sent=2, read=1)."""
	return [{"status": s, "send_path": "", "pricing_category": "", "count": c} for s, c in counts.items()]


class TestAggregate(UnitTestCase):
	def test_empty_broadcast(self):
		agg = bm._aggregate_status_rows([])
		self.assertEqual(agg["totals"], {"queued": 0, "sent": 0, "delivered": 0, "read": 0, "failed": 0})
		self.assertIsNone(agg["last_status_at"])
		self.assertEqual(bm._rates(agg["totals"]), {"delivery": None, "read": None})

	def test_single_recipient_read_implies_delivered_and_sent(self):
		t = bm._aggregate_status_rows(_rows(read=1))["totals"]
		self.assertEqual((t["sent"], t["delivered"], t["read"], t["failed"]), (1, 1, 1, 0))

	def test_thousand_mixed(self):
		t = bm._aggregate_status_rows(_rows(queued=100, sent=200, delivered=300, read=300, failed=100))["totals"]
		self.assertEqual((t["queued"], t["sent"], t["delivered"], t["read"], t["failed"]), (100, 800, 600, 300, 100))
		self.assertEqual(bm._rates(t), {"delivery": 0.75, "read": 0.5})

	def test_only_failed_and_only_queued(self):
		failed = bm._aggregate_status_rows(_rows(failed=4))
		self.assertEqual(failed["totals"]["sent"], 0)
		self.assertEqual(failed["send_path_breakdown"], {})
		queued = bm._aggregate_status_rows(_rows(queued=4))["totals"]
		self.assertEqual((queued["queued"], queued["sent"]), (4, 0))

	def test_duplicate_status_rows_of_same_group_sum_once_per_row(self):
		t = bm._aggregate_status_rows(_rows(delivered=2) + _rows(delivered=3))["totals"]
		self.assertEqual(t["delivered"], 5)

	def test_status_case_and_none_tolerated(self):
		t = bm._aggregate_status_rows([{"status": "READ", "count": 2}, {"status": None, "count": 1}])["totals"]
		self.assertEqual(t["read"], 2)

	def test_breakdowns_blank_is_unknown_and_mixed_routes(self):
		rows = [
			{"status": "sent", "send_path": "", "pricing_category": "", "count": 2},
			{"status": "delivered", "send_path": "marketing_messages", "pricing_category": "marketing_lite", "count": 3},
			{"status": "read", "send_path": "cloud_api", "pricing_category": "marketing", "count": 4},
			{"status": "failed", "send_path": "cloud_api", "pricing_category": "", "count": 9},
		]
		agg = bm._aggregate_status_rows(rows)
		self.assertEqual(agg["send_path_breakdown"], {"unknown": 2, "marketing_messages": 3, "cloud_api": 4})
		self.assertEqual(agg["pricing_category_breakdown"], {"unknown": 2, "marketing_lite": 3, "marketing": 4})

	def test_last_status_at_is_latest_stamp(self):
		early, late = datetime(2026, 10, 1, 9), datetime(2026, 10, 2, 9)
		rows = [{"status": "sent", "count": 1, "sent_at": early}, {"status": "read", "count": 1, "read_at": late, "sent_at": None}]
		self.assertEqual(bm._aggregate_status_rows(rows)["last_status_at"], late)


class TestResolveAttribution(UnitTestCase):
	def test_exact_match(self):
		r = bm._resolve_attribution({D1: 10}, {D1: _metric(10, conversions_available=1, conversions='{"purchases": 2}')})
		self.assertEqual((r["clicks"], r["conversions"]), ("exact", "exact"))
		self.assertEqual(r["values"]["clicked"], 3)
		self.assertEqual(r["values"]["conversions"], {"purchases": 2})
		self.assertEqual(r["template_level"]["caption"], "all sends of this template")

	def test_off_by_one_is_template_level_not_scaled(self):
		r = bm._resolve_attribution({D1: 10}, {D1: _metric(11)})
		self.assertEqual(r["clicks"], "template_level")
		self.assertIsNone(r["values"])
		self.assertEqual(r["template_level"]["clicked"], 3)  # whole-template figure, unscaled

	def test_extra_sends_from_outside_the_app(self):
		self.assertEqual(bm._resolve_attribution({D1: 10}, {D1: _metric(500)})["clicks"], "template_level")

	def test_two_days_one_mismatch(self):
		r = bm._resolve_attribution({D1: 5, D2: 5}, {D1: _metric(5), D2: _metric(6)})
		self.assertEqual(r["clicks"], "template_level")
		self.assertEqual(r["template_level"]["clicked"], 6)
		self.assertEqual((r["template_level"]["from_date"], r["template_level"]["to_date"]), ("2026-10-01", "2026-10-02"))

	def test_day_with_sends_but_missing_metric_row(self):
		r = bm._resolve_attribution({D1: 5, D2: 5}, {D1: _metric(5)})
		self.assertEqual(r["clicks"], "template_level")
		self.assertFalse(r["template_level"]["complete"])
		self.assertEqual(r["template_level"]["missing_days"], ["2026-10-02"])

	def test_no_rows_is_unavailable(self):
		r = bm._resolve_attribution({D1: 5}, {})
		self.assertEqual((r["clicks"], r["conversions"]), ("unavailable", "unavailable"))
		self.assertIsNone(r["template_level"])

	def test_no_sends_is_unavailable(self):
		self.assertEqual(bm._resolve_attribution({}, {D1: _metric(5)})["clicks"], "unavailable")
		self.assertEqual(bm._resolve_attribution({D1: 0}, {D1: _metric(5)})["clicks"], "unavailable")

	def test_clicks_unsupported_is_unavailable_even_when_sent_matches(self):
		r = bm._resolve_attribution({D1: 5}, {D1: _metric(5, clicks_supported=0)})
		self.assertEqual(r["clicks"], "unavailable")

	def test_clicked_listed_unavailable(self):
		r = bm._resolve_attribution({D1: 5}, {D1: _metric(5, unavailable=["clicked"])})
		self.assertEqual(r["clicks"], "unavailable")
		self.assertIsNone(r["template_level"]["clicked"])

	def test_conversions_absent_is_unavailable_not_zero(self):
		r = bm._resolve_attribution({D1: 5}, {D1: _metric(5, conversions_available=0)})
		self.assertEqual(r["conversions"], "unavailable")
		self.assertIsNone(r["values"]["conversions"])

	def test_sent_unavailable_cannot_match(self):
		r = bm._resolve_attribution({D1: 0 + 5}, {D1: _metric(5, unavailable=["sent"])})
		self.assertEqual(r["clicks"], "template_level")

	def test_block_reason_forces_template_level(self):
		r = bm._resolve_attribution({D1: 5}, {D1: _metric(5)}, block_reason="tz unknown")
		self.assertEqual(r["clicks"], "template_level")
		self.assertEqual(r["reason"], "tz unknown")

	def test_mixed_currency_amount_is_none(self):
		r = bm._resolve_attribution({D1: 5, D2: 5}, {D1: _metric(5), D2: _metric(5, currency="USD")})
		self.assertIsNone(r["template_level"]["amount_spent"])
		self.assertIsNone(r["template_level"]["currency"])

	def test_stored_max_after_meta_reset_is_used_as_stored(self):
		# Sync keeps the max for Read/Click after Meta's 7-day reset; we only read the stored row.
		r = bm._resolve_attribution({D1: 5}, {D1: _metric(5, clicked=7)})
		self.assertEqual(r["values"]["clicked"], 7)

	def test_malformed_unavailable_json_tolerated(self):
		row = _metric(5)
		row["unavailable_fields"] = "{not json"
		self.assertEqual(bm._resolve_attribution({D1: 5}, {D1: row})["clicks"], "exact")


class TestResolveAttributionBothProductTypes(UnitTestCase):
	"""Meta's counts are summed across product types per day (assumed disjoint: UNVERIFIED live)."""

	def test_sum_of_both_types_equal_to_ours_is_exact(self):
		r = bm._resolve_attribution({D1: 10}, {D1: [_metric(6, clicked=1), _metric(4, clicked=2)]})
		self.assertEqual(r["clicks"], "exact")
		self.assertEqual(r["values"]["clicked"], 3)
		self.assertEqual(r["template_level"]["sent"], 10)

	def test_zero_send_row_does_not_blank_clicks_or_conversions(self):
		active = _metric(10, clicked=2, clicks_supported=1, conversions_available=1, conversions='{"p": 1}')
		inactive = _metric(0, clicked=0, clicks_supported=0, conversions_available=0, unavailable=["clicked"])
		r = bm._resolve_attribution({D1: 10}, {D1: [active, inactive]})
		self.assertEqual(r["clicks"], "exact")
		self.assertEqual(r["conversions"], "exact")
		self.assertEqual(r["values"]["clicked"], 2)
		self.assertEqual(r["values"]["conversions"], {"p": 1})
		self.assertEqual(r["template_level"]["clicked"], 2)

	def test_cloud_api_only_day_is_exact(self):
		r = bm._resolve_attribution({D1: 10}, {D1: [_metric(10)]})
		self.assertEqual(r["clicks"], "exact")

	def test_sum_not_equal_is_template_level_even_if_one_type_equals_ours(self):
		r = bm._resolve_attribution({D1: 6}, {D1: [_metric(6), _metric(4)]})
		self.assertEqual(r["clicks"], "template_level")
		self.assertIsNone(r["values"])

	def test_one_type_only_on_one_day_other_type_on_the_other_day(self):
		r = bm._resolve_attribution({D1: 5, D2: 5}, {D1: [_metric(5)], D2: [_metric(2), _metric(3)]})
		self.assertEqual(r["clicks"], "exact")
		self.assertTrue(r["template_level"]["complete"])

	def test_day_with_no_rows_is_still_missing(self):
		r = bm._resolve_attribution({D1: 5, D2: 5}, {D1: [_metric(5)], D2: []})
		self.assertEqual(r["clicks"], "template_level")
		self.assertEqual(r["template_level"]["missing_days"], ["2026-10-02"])

	def test_clicked_unavailable_in_either_type_makes_clicks_unavailable(self):
		r = bm._resolve_attribution({D1: 10}, {D1: [_metric(6), _metric(4, unavailable=["clicked"])]})
		self.assertEqual(r["clicks"], "unavailable")
		self.assertIsNone(r["template_level"]["clicked"])

	def test_clicks_or_conversions_unsupported_in_either_type(self):
		r = bm._resolve_attribution({D1: 10}, {D1: [_metric(6, conversions_available=1), _metric(4, clicks_supported=0, conversions_available=1)]})
		self.assertEqual(r["clicks"], "unavailable")
		self.assertEqual(r["conversions"], "exact")
		r = bm._resolve_attribution({D1: 10}, {D1: [_metric(6, conversions_available=1), _metric(4, conversions_available=0)]})
		self.assertEqual((r["clicks"], r["conversions"]), ("exact", "unavailable"))

	def test_sent_unavailable_in_either_type_cannot_match(self):
		r = bm._resolve_attribution({D1: 10}, {D1: [_metric(10), _metric(0, unavailable=["sent"])]})
		self.assertEqual(r["clicks"], "template_level")
		self.assertIsNone(r["template_level"]["sent"])

	def test_mixed_currency_across_types(self):
		r = bm._resolve_attribution({D1: 10}, {D1: [_metric(6), _metric(4, currency="USD")]})
		self.assertEqual(r["clicks"], "exact")
		self.assertIsNone(r["template_level"]["amount_spent"])
		self.assertIsNone(r["template_level"]["currency"])

	def test_same_currency_across_types_sums_spend_and_conversions(self):
		a = _metric(6, conversions_available=1, conversions='{"p": 1}')
		b = _metric(4, conversions_available=1, conversions='{"p": 2}')
		r = bm._resolve_attribution({D1: 10}, {D1: [a, b]})
		self.assertEqual(r["template_level"]["amount_spent"], 10.0)
		self.assertEqual(r["template_level"]["currency"], "INR")
		self.assertEqual(r["values"]["conversions"], {"p": 3})

	def test_compute_groups_rows_of_both_types_per_day(self):
		rows = [{"whatsapp_account": "ACC", "template_id": "T1", "metric_date": D1, **_metric(n)} for n in (2, 1)]
		ps = _patched(statuses=_rows(sent=3), minutes=[{"minute": "2026-10-01 10:00", "count": 3}], metrics=rows)
		for p in ps:
			p.start()
			self.addCleanup(p.stop)
		out = bm.get_broadcast_metrics("BULK-1")
		self.assertEqual(out["attribution"]["clicks"], "exact")
		self.assertEqual(out["template_level"]["sent"], 3)


class TestDayBucketing(UnitTestCase):
	UTC = ZoneInfo("UTC")

	def test_spans_midnight_in_waba_timezone(self):
		kolkata = ZoneInfo("Asia/Kolkata")  # +05:30: 20:00 UTC is already next day
		self.assertEqual(bm._to_waba_day("2026-10-01 18:29", self.UTC, kolkata), D1)
		self.assertEqual(bm._to_waba_day("2026-10-01 18:30", self.UTC, kolkata), D2)

	def test_dst_observing_zone(self):
		ny = ZoneInfo("America/New_York")
		# 2026-11-01 05:30 UTC is 01:30 EDT; 2026-11-01 04:30 UTC is 00:30 EDT; DST ends 06:00 UTC
		self.assertEqual(bm._to_waba_day("2026-11-01 03:59", self.UTC, ny), date(2026, 10, 31))
		self.assertEqual(bm._to_waba_day("2026-11-01 04:00", self.UTC, ny), date(2026, 11, 1))
		self.assertEqual(bm._to_waba_day("2026-11-02 04:59", self.UTC, ny), date(2026, 11, 1))
		self.assertEqual(bm._to_waba_day("2026-11-02 05:00", self.UTC, ny), date(2026, 11, 2))

	def test_fixed_offset_zone_buckets_days(self):
		for minutes, minute, expected in (
			(330, "2026-10-01 18:29", D1), (330, "2026-10-01 18:30", D2),
			(-210, "2026-10-02 03:29", D1), (-210, "2026-10-02 03:30", D2),
			(765, "2026-10-01 11:14", D1), (765, "2026-10-01 11:15", D2),
			(0, "2026-10-01 23:59", D1), (0, "2026-10-02 00:00", D2),
		):
			with self.subTest(minutes=minutes, minute=minute):
				zone, derived = bm._day_zone(None, minutes)
				self.assertTrue(derived)
				self.assertEqual(bm._to_waba_day(minute, self.UTC, zone), expected)

	def test_day_zone_precedence(self):
		kolkata, derived = bm._day_zone("Asia/Kolkata", 0)
		self.assertEqual((kolkata, derived), (ZoneInfo("Asia/Kolkata"), False))  # IANA name wins
		for name in (None, "", "3", "Not/AZone"):
			zone, derived = bm._day_zone(name, 330)
			self.assertTrue(derived, name)
			self.assertEqual(bm._to_waba_day("2026-10-01 18:30", self.UTC, zone), D2)
		self.assertEqual(bm._day_zone("", None), (None, False))
		self.assertEqual(bm._day_zone("3", None), (None, False))
		zone, derived = bm._day_zone("", 0)  # UTC is a real offset, not "missing"
		self.assertTrue(derived)
		self.assertEqual(bm._to_waba_day("2026-10-01 23:59", self.UTC, zone), D1)

	def test_format_offset(self):
		for minutes, text in ((330, "UTC+05:30"), (-210, "UTC-03:30"), (765, "UTC+12:45"), (0, "UTC+00:00")):
			self.assertEqual(bm._format_utc_offset(minutes), text)

	def test_zone_parsing(self):
		self.assertIsNotNone(bm._zone("Asia/Kolkata"))
		for bad in (None, "", "1", "Not/AZone", "../etc"):
			self.assertIsNone(bm._zone(bad), bad)


def _patched(statuses=None, minutes=None, tz="UTC", metrics=None, template_id="T1", account="ACC", recipients=3, offset=None):
	"""Patch every DB loader so _compute runs on fabricated data."""
	broadcast = {"name": "BULK-1", "title": "B", "template": "tpl", "whatsapp_account": account,
		"recipient_count": recipients, "campaign": None}
	patches = [
		patch(f"{MOD}._load_broadcasts", return_value=[broadcast]),
		patch(f"{MOD}._load_status_rows", return_value=[{"reference_name": "BULK-1", **r} for r in (statuses or [])]),
		patch(f"{MOD}._load_sent_minutes", return_value=[{"reference_name": "BULK-1", **m} for m in (minutes or [])]),
		patch(f"{MOD}._load_template_info", return_value={"tpl": {"id": template_id, "whatsapp_account": account}}),
		patch(f"{MOD}._load_waba_timezones", return_value={account: tz}),
		patch(f"{MOD}._load_waba_utc_offsets", return_value={} if offset is None else {account: offset}),
		patch(f"{MOD}._load_metric_rows", return_value=metrics or []),
		patch(f"{MOD}.get_system_timezone", return_value="UTC"),
	]
	return patches


class TestGetBroadcastMetrics(UnitTestCase):
	def _run(self, **kw):
		ps = _patched(**kw)
		for p in ps:
			p.start()
			self.addCleanup(p.stop)
		return bm.get_broadcast_metrics("BULK-1")

	def test_full_shape_and_exact(self):
		out = self._run(
			statuses=_rows(sent=1, delivered=2),
			minutes=[{"minute": "2026-10-01 10:00", "count": 3}],
			metrics=[{"whatsapp_account": "ACC", "template_id": "T1", "metric_date": D1, **_metric(3)}],
		)
		self.assertEqual(out["totals"], {"recipients": 3, "queued": 0, "sent": 3, "delivered": 2, "read": 0, "failed": 0})
		self.assertEqual(out["attribution"]["clicks"], "exact")
		self.assertNotIn("template_level", out["attribution"])
		self.assertEqual(out["template_level"]["sent"], 3)

	def test_two_broadcasts_same_template_same_day_template_level(self):
		# Meta counts both broadcasts' sends (3 + 4) so ours (3) does not match.
		out = self._run(
			statuses=_rows(sent=3),
			minutes=[{"minute": "2026-10-01 10:00", "count": 3}],
			metrics=[{"whatsapp_account": "ACC", "template_id": "T1", "metric_date": D1, **_metric(7)}],
		)
		self.assertEqual(out["attribution"]["clicks"], "template_level")

	def test_unstored_or_numeric_timezone_forces_template_level(self):
		for tz in ("", "3"):
			out = self._run(
				statuses=_rows(sent=3),
				minutes=[{"minute": "2026-10-01 10:00", "count": 3}],
				metrics=[{"whatsapp_account": "ACC", "template_id": "T1", "metric_date": D1, **_metric(3)}],
				tz=tz,
			)
			self.assertEqual(out["attribution"]["clicks"], "template_level", tz)

	def test_undated_sends_force_template_level(self):
		out = self._run(
			statuses=_rows(delivered=3),  # delivered_at null case: status wins, no timestamp needed for totals
			minutes=[{"minute": None, "count": 1}, {"minute": "2026-10-01 10:00", "count": 2}],
			metrics=[{"whatsapp_account": "ACC", "template_id": "T1", "metric_date": D1, **_metric(3)}],
		)
		self.assertEqual(out["totals"]["delivered"], 3)
		self.assertEqual(out["attribution"]["clicks"], "template_level")

	def test_template_without_meta_id(self):
		out = self._run(statuses=_rows(sent=1), minutes=[{"minute": "2026-10-01 10:00", "count": 1}], template_id=None)
		self.assertEqual(out["attribution"]["clicks"], "unavailable")
		self.assertEqual(out["attribution"]["reason"], "This template has no Meta template id.")
		self.assertIsNone(out["template_level"])

	def test_unknown_broadcast_raises(self):
		with patch(f"{MOD}._load_broadcasts", return_value=[]):
			with self.assertRaises(frappe.DoesNotExistError) as ctx:
				bm.get_broadcast_metrics("x' OR 1=1 --")
		self.assertIn("Bulk WhatsApp Message x' OR 1=1 -- not found", str(ctx.exception))


class TestDerivedOffsetAttribution(UnitTestCase):
	"""A stored fixed offset lets attribution be exact when the IANA name is blank."""

	def _run(self, **kw):
		for p in _patched(**kw):
			p.start()
			self.addCleanup(p.stop)
		return bm.get_broadcast_metrics("BULK-1")

	def test_blank_iana_with_offset_is_exact_and_says_fixed_offset(self):
		out = self._run(tz="", offset=330, statuses=_rows(sent=3),
			minutes=[{"minute": "2026-10-01 18:30", "count": 3}], metrics=[{"whatsapp_account": "ACC", "template_id": "T1", "metric_date": D2, **_metric(3)}])
		self.assertEqual(out["attribution"]["clicks"], "exact")
		self.assertIn("fixed UTC offset (UTC+05:30)", out["attribution"]["reason"])
		self.assertIn("daylight-saving", out["attribution"]["reason"])

	def test_broadcast_spanning_midnight_in_derived_offset(self):
		minutes = [{"minute": "2026-10-01 18:29", "count": 2}, {"minute": "2026-10-01 18:30", "count": 1}]
		metrics = [
			{"whatsapp_account": "ACC", "template_id": "T1", "metric_date": D1, **_metric(2)},
			{"whatsapp_account": "ACC", "template_id": "T1", "metric_date": D2, **_metric(1)},
		]
		out = self._run(tz="", offset=330, statuses=_rows(sent=3), minutes=minutes, metrics=metrics)
		self.assertEqual(out["attribution"]["clicks"], "exact")
		# Same sends bucketed in UTC (no offset) would be one day of 3: Meta's 2 + 1 split must not match.
		utc = self._run(tz="UTC", statuses=_rows(sent=3), minutes=minutes, metrics=metrics)
		self.assertEqual(utc["attribution"]["clicks"], "template_level")

	def test_negative_half_hour_offset(self):
		out = self._run(tz="", offset=-210, statuses=_rows(sent=1), minutes=[{"minute": "2026-10-02 03:30", "count": 1}],
			metrics=[{"whatsapp_account": "ACC", "template_id": "T1", "metric_date": D2, **_metric(1)}])
		self.assertEqual(out["attribution"]["clicks"], "exact")
		self.assertIn("UTC-03:30", out["attribution"]["reason"])

	def test_utc_offset_zero_is_used(self):
		out = self._run(tz="", offset=0, statuses=_rows(sent=1), minutes=[{"minute": "2026-10-01 10:00", "count": 1}],
			metrics=[{"whatsapp_account": "ACC", "template_id": "T1", "metric_date": D1, **_metric(1)}])
		self.assertEqual(out["attribution"]["clicks"], "exact")
		self.assertIn("UTC+00:00", out["attribution"]["reason"])

	def test_iana_name_wins_over_offset(self):
		out = self._run(tz="Asia/Kolkata", offset=0, statuses=_rows(sent=1),
			minutes=[{"minute": "2026-10-01 18:30", "count": 1}],
			metrics=[{"whatsapp_account": "ACC", "template_id": "T1", "metric_date": D2, **_metric(1)}])
		self.assertEqual(out["attribution"]["clicks"], "exact")
		self.assertNotIn("fixed UTC offset", out["attribution"]["reason"])

	def test_no_zone_and_no_offset_stays_template_level(self):
		out = self._run(tz="", statuses=_rows(sent=1), minutes=[{"minute": "2026-10-01 10:00", "count": 1}],
			metrics=[{"whatsapp_account": "ACC", "template_id": "T1", "metric_date": D1, **_metric(1)}])
		self.assertEqual(out["attribution"]["clicks"], "template_level")
		self.assertIn("time zone is not stored", out["attribution"]["reason"])

	def test_mismatch_with_derived_offset_still_mentions_fixed_offset(self):
		out = self._run(tz="", offset=330, statuses=_rows(sent=3), minutes=[{"minute": "2026-10-01 18:30", "count": 3}],
			metrics=[{"whatsapp_account": "ACC", "template_id": "T1", "metric_date": D2, **_metric(9)}])
		self.assertEqual(out["attribution"]["clicks"], "template_level")
		self.assertIn("fixed UTC offset (UTC+05:30)", out["attribution"]["reason"])

	def test_unavailable_results_carry_no_offset_note(self):
		out = self._run(tz="", offset=330, statuses=_rows(sent=1), minutes=[{"minute": "2026-10-01 18:30", "count": 1}])
		self.assertEqual(out["attribution"]["clicks"], "unavailable")
		self.assertNotIn("fixed UTC offset", out["attribution"]["reason"])


class TestLoadWabaUtcOffsets(UnitTestCase):
	"""Loader tolerates a non-migrated site and ignores accounts with no derived offset."""

	def test_column_missing_returns_empty(self):
		with patch(f"{MOD}.frappe.db.has_column", return_value=False), patch(f"{MOD}.frappe.get_all") as get_all:
			self.assertEqual(bm._load_waba_utc_offsets(["A"]), {})
		get_all.assert_not_called()

	def test_only_synced_accounts_and_zero_kept(self):
		rows = [
			frappe._dict(name="A", waba_utc_offset_minutes=330, waba_utc_offset_synced_at="2026-10-19 00:00:00"),
			frappe._dict(name="B", waba_utc_offset_minutes=0, waba_utc_offset_synced_at="2026-10-19 00:00:00"),
			frappe._dict(name="C", waba_utc_offset_minutes=0, waba_utc_offset_synced_at=None),  # Int default, never derived
			frappe._dict(name="D", waba_utc_offset_minutes=None, waba_utc_offset_synced_at="2026-10-19 00:00:00"),
		]
		with patch(f"{MOD}.frappe.db.has_column", return_value=True), patch(f"{MOD}.frappe.get_all", return_value=rows):
			self.assertEqual(bm._load_waba_utc_offsets(["A", "B", "C", "D"]), {"A": 330, "B": 0})


class TestGetCampaignMetrics(UnitTestCase):
	def _campaign(self, count, per_broadcast=None):
		rows = [frappe._dict(name=f"B{i}") for i in range(count)]
		per = per_broadcast or [_fake(f"B{i}") for i in range(min(count, MM_BROADCAST_ROWS_LIMIT))]
		with patch(f"{MOD}.frappe.get_list", return_value=rows) as gl, patch(f"{MOD}._load_broadcasts", return_value=[]), patch(
			f"{MOD}._compute", return_value=per
		):
			return bm.get_campaign_metrics("C1"), gl

	def test_zero_broadcasts(self):
		out, _ = self._campaign(0)
		self.assertEqual(out["broadcast_count"], 0)
		self.assertEqual(out["attribution"]["clicks"], "unavailable")
		self.assertEqual(out["rates"], {"delivery": None, "read": None})
		self.assertFalse(out["truncated"])

	def test_one_broadcast_sums_and_rates(self):
		out, _ = self._campaign(1)
		self.assertEqual(out["totals"]["sent"], 10)
		self.assertEqual(out["rates"]["delivery"], 0.5)
		self.assertEqual(out["send_path_breakdown"], {"cloud_api": 10})

	def test_limit_and_limit_plus_one(self):
		out, gl = self._campaign(MM_BROADCAST_ROWS_LIMIT)
		self.assertFalse(out["truncated"])
		self.assertEqual(gl.call_args.kwargs["limit"], MM_BROADCAST_ROWS_LIMIT + 1)
		out, _ = self._campaign(MM_BROADCAST_ROWS_LIMIT + 1)
		self.assertTrue(out["truncated"])

	def test_weakest_label_wins(self):
		per = [_fake("A", clicks="exact"), _fake("B", clicks="template_level"), _fake("C", clicks="exact")]
		out, _ = self._campaign(3, per)
		self.assertEqual(out["attribution"]["clicks"], "template_level")
		per = [_fake("A", clicks="template_level"), _fake("B", clicks="unavailable")]
		out, _ = self._campaign(2, per)
		self.assertEqual(out["attribution"]["clicks"], "unavailable")
		out, _ = self._campaign(2, [_fake("A"), _fake("B")])
		self.assertEqual(out["attribution"]["clicks"], "exact")


def _fake(name, clicks="exact"):
	return {
		"name": name,
		"totals": {"recipients": 10, "queued": 0, "sent": 10, "delivered": 5, "read": 2, "failed": 1},
		"send_path_breakdown": {"cloud_api": 10},
		"pricing_category_breakdown": {},
		"last_status_at": None,
		"attribution": {"clicks": clicks, "conversions": "unavailable", "reason": "r", "values": None},
	}


class TestEndpoints(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_guest_denied_before_anything_else(self):
		frappe.set_user("Guest")
		with patch("frappe.has_permission", return_value=False), patch.object(api, "check_feature_or_throw") as feature, patch.object(api.broadcast_metrics, "get_broadcast_metrics") as get:
			with self.assertRaises(frappe.PermissionError):
				api.get_broadcast_metrics("anything")
			with self.assertRaises(frappe.PermissionError):
				api.get_campaign_metrics("anything")
		feature.assert_not_called()
		get.assert_not_called()

	def test_permission_checked_first_then_feature_then_compute(self):
		order = []
		with patch.object(api, "check_read", side_effect=lambda *a: order.append(("read", a))), patch.object(
			api, "check_feature_or_throw", side_effect=lambda *a, **k: order.append(("feature", a))
		), patch.object(api.broadcast_metrics, "get_broadcast_metrics", side_effect=lambda n: order.append(("calc", n)) or {}):
			api.get_broadcast_metrics("B1")
		self.assertEqual([o[0] for o in order], ["read", "feature", "calc"])
		self.assertEqual(order[0][1], ("Bulk WhatsApp Message", "B1"))

	def test_campaign_permission_on_campaign_doctype(self):
		with patch.object(api, "check_read") as read, patch.object(api, "check_feature_or_throw"), patch.object(
			api.broadcast_metrics, "get_campaign_metrics", return_value={}
		):
			api.get_campaign_metrics("C1")
		read.assert_called_once_with("Marketing Campaign", "C1")

	def test_feature_off_denies_and_does_not_compute(self):
		with patch.object(api, "check_read"), patch.object(
			api, "check_feature_or_throw", side_effect=frappe.ValidationError("Analytics is not available on your plan")
		), patch.object(api.broadcast_metrics, "get_broadcast_metrics") as get:
			with self.assertRaises(frappe.ValidationError):
				api.get_broadcast_metrics("B1")
		get.assert_not_called()

	def test_sql_injection_name_is_plain_unknown_name(self):
		evil = "x'; DROP TABLE `tabChannel Message`; --"
		with self.assertRaises(frappe.DoesNotExistError):
			api.get_broadcast_metrics(evil)
		self.assertTrue(frappe.db.table_exists("Channel Message"))

	def test_grouped_queries_execute_on_real_db(self):
		"""Regression: DATE_FORMAT's % must be escaped for the driver; both SQL loaders run."""
		self.assertEqual(bm._load_sent_minutes(["no-such-broadcast"]), [])
		self.assertEqual(bm._load_status_rows(["no-such-broadcast"]), [])

	def test_empty_names_list_returns_empty_without_sql_error(self):
		self.assertEqual(bm._load_sent_minutes([]), [])
		self.assertEqual(bm._load_status_rows([]), [])
		self.assertEqual(bm._compute([]), [])
