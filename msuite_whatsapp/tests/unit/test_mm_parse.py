"""Tolerant template_analytics parser tests (pure, no DB, no HTTP).

DOCS_PAYLOAD is hand-built strictly from the documented response shape at
https://developers.facebook.com/documentation/business-messaging/whatsapp/analytics
(not a captured response; replace/add a real fixture once captured).
"""

import copy
import json
import os
import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from msuite_whatsapp.services.analytics.mm_parse import (
	MAX_INT_COLUMN,
	_to_day,
	derive_utc_offset_minutes,
	extract_day_starts,
	parse_template_analytics,
)

DAY_2028_02_29 = 1835395200  # 2028-02-29T00:00:00Z

DOCS_PAYLOAD = {
	"data": [
		{
			"granularity": "DAILY",
			"product_type": "marketing_messages_lite_api",
			"data_points": [
				{
					"template_id": "T1",
					"start": 1767225600,  # 2026-01-01T00:00:00Z
					"end": 1767312000,
					"sent": 10,
					"delivered": 8,
					"read": 0,
					"clicked": [
						{"type": "url_button", "button_content": "Shop 🛍️", "count": 3},
						{"type": "unique_url_button", "button_content": "Shop 🛍️", "count": 2},
						{"type": "quick_reply_button", "button_content": "Stop", "count": 1},
					],
					"cost": [
						{"type": "amount_spent", "value": 1.5},
						{"type": "cost_per_delivered", "value": 0.1875},
						{"type": "cost_per_url_button_click", "value": 0.5},
					],
				}
			],
		}
	],
	"paging": {"cursors": {"before": "a", "after": "b"}},
}


def _point(**kw):
	base = {"template_id": "T", "start": 1767225600}
	base.update(kw)
	return {"data": [{"data_points": [base]}]}


class TestParseTemplateAnalytics(unittest.TestCase):
	def test_documented_shape(self):
		(row,) = parse_template_analytics(DOCS_PAYLOAD)
		self.assertEqual(row["template_id"], "T1")
		self.assertEqual(row["metric_date"], "2026-01-01")
		self.assertEqual((row["sent"], row["delivered"], row["read"]), (10, 8, 0))
		self.assertEqual((row["clicked"], row["quick_reply_clicked"]), (3, 1))
		self.assertEqual(row["amount_spent"], 1.5)
		self.assertEqual(row["cost_per_delivered"], 0.1875)
		self.assertEqual(row["cost_per_click"], 0.5)
		self.assertTrue(row["clicks_supported"])
		self.assertFalse(row["conversions_available"])
		self.assertEqual(row["conversions"], {})

	def test_unparseable_payloads_return_empty(self):
		for bad in (None, {}, [], "x", 5, {"data": []}, {"data": None}, {"data": "x"},
				{"data": ["a", 1, None]}, {"data": [{"data_points": "x"}]}, {"data": [{"data_points": ["a"]}]}):
			self.assertEqual(parse_template_analytics(bad), [], bad)

	def test_skips_points_without_template_or_date(self):
		for pt in ({"start": 1}, {"template_id": "", "start": 1}, {"template_id": "T"},
				{"template_id": "T", "start": "garbage"}, {"template_id": "T", "start": -5}):
			self.assertEqual(parse_template_analytics({"data": [{"data_points": [pt]}]}), [], pt)

	def test_missing_clicked_and_cost(self):
		(row,) = parse_template_analytics(_point(sent=1))
		self.assertFalse(row["clicks_supported"])
		for k in ("clicked", "quick_reply_clicked", "amount_spent", "cost_per_delivered", "cost_per_click", "delivered", "read"):
			self.assertIsNone(row[k], k)

	def test_clicked_wrong_type_or_empty(self):
		for c in ("x", None, 5):
			(row,) = parse_template_analytics(_point(clicked=c))
			self.assertFalse(row["clicks_supported"])
		(row,) = parse_template_analytics(_point(clicked=[]))
		self.assertTrue(row["clicks_supported"])
		self.assertIsNone(row["clicked"])

	def test_clicked_falls_back_to_unique_and_ignores_junk(self):
		clicked = ["junk", {"type": "UNIQUE_URL_BUTTON", "count": "4"}, {"type": "weird", "count": 9}, {"count": 1}]
		(row,) = parse_template_analytics(_point(clicked=clicked))
		self.assertEqual(row["clicked"], 4)

	def test_zero_distinct_from_none(self):
		(row,) = parse_template_analytics(_point(sent=0, delivered=None))
		self.assertEqual(row["sent"], 0)
		self.assertIsNone(row["delivered"])

	def test_numeric_coercion(self):
		(row,) = parse_template_analytics(_point(sent="12", delivered="12.0", read="N/A"))
		self.assertEqual((row["sent"], row["delivered"]), (12, 12))
		self.assertIsNone(row["read"])

	def test_invalid_numbers_become_none(self):
		for v in (-1, "-3", float("nan"), float("inf"), True, [], {}, "", "  ", 1.5, MAX_INT_COLUMN + 1):
			(row,) = parse_template_analytics(_point(sent=v))
			self.assertIsNone(row["sent"], v)

	def test_int_boundary(self):
		(row,) = parse_template_analytics(_point(sent=MAX_INT_COLUMN))
		self.assertEqual(row["sent"], MAX_INT_COLUMN)
		(row,) = parse_template_analytics(_point(sent=2**63))
		self.assertIsNone(row["sent"])

	def test_cost_variants(self):
		cost = [{"type": "AMOUNT_SPENT", "value": "2.50"}, {"type": "cost_per_delivered", "value": -1},
			"junk", {"type": "cost_per_url_button_click"}, {"type": "unknown", "value": 1}]
		(row,) = parse_template_analytics(_point(cost=cost))
		self.assertEqual(row["amount_spent"], 2.5)
		self.assertIsNone(row["cost_per_delivered"])
		self.assertIsNone(row["cost_per_click"])
		(row,) = parse_template_analytics(_point(cost="x"))
		self.assertIsNone(row["amount_spent"])

	def test_uppercase_keys(self):
		(row,) = parse_template_analytics(_point(SENT=5, Delivered=4))
		self.assertEqual((row["sent"], row["delivered"]), (5, 4))

	def test_unknown_numeric_keys_kept_as_conversions(self):
		(row,) = parse_template_analytics(_point(sent=1, website_purchases=7, WEBSITE_ADD_TO_CART="2",
			note="hi", nested={"a": 1}, flag=None, bad=-1))
		self.assertEqual(row["conversions"], {"WEBSITE_PURCHASES": 7, "WEBSITE_ADD_TO_CART": 2})
		self.assertTrue(row["conversions_available"])

	def test_structural_keys_not_conversions(self):
		(row,) = parse_template_analytics(_point(end=1767312000))
		self.assertEqual(row["conversions"], {})
		self.assertFalse(row["conversions_available"])

	def test_dates(self):
		cases = {DAY_2028_02_29: "2028-02-29", 1782777600: "2026-06-30", 1798675200: "2026-12-31",
			1798761600: "2027-01-01", 1767225600 + 35999: "2026-01-01", 1767225600 + 36000: "2026-01-02", "1767225600": "2026-01-01",
			"2026-03-05": "2026-03-05"}
		for start, want in cases.items():
			(row,) = parse_template_analytics(_point(start=start))
			self.assertEqual(row["metric_date"], want, start)

	def test_invalid_date_strings_skipped(self):
		for s in ("2027-02-29", "2026-13-01", "26-1-1", "2026-01-01T00:00"):
			self.assertEqual(parse_template_analytics(_point(start=s)), [], s)

	def test_duplicates_merged_idempotently(self):
		payload = copy.deepcopy(DOCS_PAYLOAD)
		payload["data"].append(copy.deepcopy(payload["data"][0]))
		(row,) = parse_template_analytics(payload)
		self.assertEqual((row["sent"], row["delivered"], row["clicked"]), (10, 8, 3))

	def test_duplicates_fill_gaps_not_overwrite_with_none(self):
		payload = {"data": [{"data_points": [
			{"template_id": "T", "start": 1767225600, "sent": 5, "x": 1},
			{"template_id": "T", "start": 1767225600, "delivered": 4, "y": 2}]}]}
		(row,) = parse_template_analytics(payload)
		self.assertEqual((row["sent"], row["delivered"]), (5, 4))
		self.assertEqual(row["conversions"], {"X": 1, "Y": 2})

	def test_distinct_days_and_templates_sorted(self):
		payload = {"data": [{"data_points": [
			{"template_id": "B", "start": 1767312000}, {"template_id": "A", "start": 1767312000},
			{"template_id": "A", "start": 1767225600}]}]}
		got = [(r["template_id"], r["metric_date"]) for r in parse_template_analytics(payload)]
		self.assertEqual(got, [("A", "2026-01-01"), ("A", "2026-01-02"), ("B", "2026-01-02")])

	def test_template_id_unicode_and_int(self):
		(row,) = parse_template_analytics(_point(template_id="प्रचार-🎉"))
		self.assertEqual(row["template_id"], "प्रचार-🎉")
		(row,) = parse_template_analytics(_point(template_id=123))
		self.assertEqual(row["template_id"], "123")

	def test_does_not_mutate_input(self):
		before = copy.deepcopy(DOCS_PAYLOAD)
		parse_template_analytics(DOCS_PAYLOAD)
		self.assertEqual(DOCS_PAYLOAD, before)

class TestWabaLocalMidnight(unittest.TestCase):
	"""Regression: live Meta data with use_waba_timezone has `start` at WABA-local midnight."""

	def test_east_of_utc_local_midnight_maps_to_local_day(self):
		# 2026-10-13T18:30Z == 2026-10-14 00:00 in UTC+5:30 (value captured from a real response)
		(row,) = parse_template_analytics(_point(start=1791916200))
		self.assertEqual(row["metric_date"], "2026-10-14")

	def test_west_of_utc_local_midnight_keeps_utc_date(self):
		# 2026-10-14T05:00Z == 2026-10-14 00:00 in UTC-5
		(row,) = parse_template_analytics(_point(start=1791954000))
		self.assertEqual(row["metric_date"], "2026-10-14")

	def test_before_threshold_is_not_shifted(self):
		# 1 second before 10:00 UTC threshold (e.g. 09:59:59 UTC) is not shifted
		(row,) = parse_template_analytics(_point(start=1791936000 + 35999))
		self.assertEqual(row["metric_date"], "2026-10-14")

	def test_west_utc_12_with_offset_is_not_shifted(self):
		# In UTC-12 (Baker Island), midnight at 12:00 UTC is not shifted when offset is known
		(row,) = parse_template_analytics(_point(start=1791936000 + 43200), utc_offset_minutes=-720)
		self.assertEqual(row["metric_date"], "2026-10-14")



class TestRealMetaFixture(unittest.TestCase):
	"""Captured from a live GET template_analytics (read-only, IDs scrubbed), Graph v26.0, use_waba_timezone=true."""

	def test_real_response_parses_without_invented_values(self):
		import json
		import os

		path = os.path.join(os.path.dirname(__file__), "..", "fixtures", "mm_template_analytics.json")
		with open(path) as handle:
			rows = parse_template_analytics(json.load(handle))
		self.assertEqual([r["metric_date"] for r in rows], ["2026-10-14", "2026-10-15", "2026-10-16"])
		for row in rows:
			self.assertEqual((row["sent"], row["delivered"], row["read"]), (0, 0, 0))
			# cost entries carry no value when nothing was spent: unavailable, never 0
			self.assertIsNone(row["amount_spent"])
			self.assertIsNone(row["cost_per_delivered"])
			self.assertIsNone(row["clicked"])
			self.assertFalse(row["clicks_supported"])


class TestDeriveUtcOffset(unittest.TestCase):
	"""derive_utc_offset_minutes: WABA UTC offset from the local-midnight `start` values."""

	EPOCH_2026_10_14 = 1791936000  # 2026-10-14T00:00:00Z

	def _starts(self, offset_minutes, days=3, first_day=0):
		"""Local-midnight unix starts of `days` consecutive days for a zone at `offset_minutes` east of UTC."""
		return {self.EPOCH_2026_10_14 + (first_day + i) * 86400 - offset_minutes * 60 for i in range(days)}

	def _derive(self, starts, window=(date(2026, 10, 14), date(2026, 10, 16))):
		return derive_utc_offset_minutes(starts, *window)

	def test_live_fixture_is_kolkata(self):
		path = os.path.join(os.path.dirname(__file__), "..", "fixtures", "mm_template_analytics.json")
		with open(path) as handle:
			starts = extract_day_starts(json.load(handle))
		self.assertEqual(sorted(starts), [1791916200, 1792002600, 1792089000])
		self.assertEqual(derive_utc_offset_minutes(starts, date(2026, 10, 14), date(2026, 10, 16)), 330)

	def test_offsets(self):
		for minutes in (330, -210, 765, 0, 840, -720, -300, 60, 345, 780):
			with self.subTest(minutes=minutes):
				self.assertEqual(self._derive(self._starts(minutes)), minutes)

	def test_utc_zero_is_a_value_not_missing(self):
		self.assertEqual(self._derive(self._starts(0)), 0)
		self.assertIsNotNone(self._derive(self._starts(0)))

	def test_single_start_is_enough(self):
		self.assertEqual(self._derive(self._starts(330, days=1)), 330)

	def test_ambiguous_without_window_is_none_but_unambiguous_is_not(self):
		self.assertIsNone(derive_utc_offset_minutes(self._starts(765)))  # +12:45 looks like -11:15 too
		self.assertEqual(derive_utc_offset_minutes(self._starts(330)), 330)

	def test_ambiguous_window_matches_both_candidates_is_none(self):
		wide = (date(2026, 10, 10), date(2026, 10, 20))
		self.assertIsNone(self._derive(self._starts(765), wide))

	def test_negative_ambiguous_zone_resolved_by_window(self):
		self.assertEqual(self._derive(self._starts(-660)), -660)  # Samoa vs +13:00

	def test_garbage_and_empty_give_none(self):
		for payload in (None, [], {}, {"data": None}, {"data": [{"data_points": [{"start": "x"}]}]}):
			with self.subTest(payload=payload):
				self.assertEqual(extract_day_starts(payload), set())
		for starts in (set(), {True}, {-5}, {1.5}, {"abc"}, {None}, {1791936000 + 7 * 60}, {10**30}):
			with self.subTest(starts=starts):
				self.assertIsNone(self._derive(starts))

	def test_extract_ignores_unusable_and_dedups(self):
		payload = {"data": [
			{"data_points": [{"start": 1791916200}, {"start": 1791916200}, {"start": True}, {"start": "bad"}, "x", {}]},
			"not-a-dict",
			{"data_points": [{"start": "1792002600"}]},
		]}
		self.assertEqual(extract_day_starts(payload), {1791916200, 1792002600})

	def test_garbage_among_valid_starts_is_ignored(self):
		starts = self._starts(330) | {12345, 1791936000 + 7 * 60}
		self.assertEqual(self._derive(starts), 330)

	def test_majority_wins_over_conflicting_reading(self):
		starts = self._starts(330, days=3) | self._starts(-210, days=1, first_day=1)
		self.assertEqual(self._derive(starts), 330)

	def test_tie_goes_to_most_recent_reading(self):
		old = self._starts(330, days=1, first_day=0)
		new = self._starts(345, days=1, first_day=2)
		self.assertEqual(self._derive(old | new), 345)

	def test_dst_zone_crossing_transition_uses_majority(self):
		# New York, DST ends 2026-11-01 02:00: local midnights Oct 30, 31, Nov 1 are EDT (-240), Nov 2, 3 are EST (-300).
		ny = ZoneInfo("America/New_York")

		def midnights(*days):
			return {int(datetime(2026, m, d, tzinfo=ny).timestamp()) for m, d in days}

		window = (date(2026, 10, 29), date(2026, 11, 5))
		self.assertEqual(derive_utc_offset_minutes(midnights((10, 30), (10, 31), (11, 1), (11, 2), (11, 3)), *window), -240)
		self.assertEqual(derive_utc_offset_minutes(midnights((11, 1), (11, 2), (11, 3)), *window), -300)


class TestOffsetsToDay(unittest.TestCase):
	EPOCH_2026_10_14 = 1791936000  # 2026-10-14T00:00:00Z

	def test_all_offsets_with_offset_parameter(self):
		"""Parametrised test for offsets -12..+14 (every hour plus fractional zones)."""
		offsets = [-12, -11, -10, -9, -8, -7, -6, -5, -4, -3.5, -3, -2, -1, 0, 1, 2, 3, 4, 5, 5.5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
		for h in offsets:
			minutes = int(h * 60)
			start = self.EPOCH_2026_10_14 - minutes * 60
			with self.subTest(offset_hours=h):
				self.assertEqual(_to_day(start, utc_offset_minutes=minutes), "2026-10-14")

	def test_utc_13_and_14_pure_threshold(self):
		"""Offsets +13 and +14 resolve to the correct day even without explicit offset."""
		for h in (13, 14):
			minutes = h * 60
			start = self.EPOCH_2026_10_14 - minutes * 60
			with self.subTest(offset_hours=h):
				self.assertEqual(_to_day(start), "2026-10-14")

	def test_negative_offsets_not_shifted_wrongly(self):
		"""Negative offsets (e.g. UTC-5) are not shifted to the next day."""
		for h in (-1, -3, -5, -8, -9):
			minutes = h * 60
			start = self.EPOCH_2026_10_14 - minutes * 60
			with self.subTest(offset_hours=h):
				self.assertEqual(_to_day(start), "2026-10-14")
