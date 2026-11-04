"""Tolerant parser for the WhatsApp ``template_analytics`` response (pure, no DB, no HTTP).

Response shape relied on (official docs, fetched 2026-10-20):
https://developers.facebook.com/documentation/business-messaging/whatsapp/analytics
(``GET /<WABA_ID>/template_analytics``)::

    {"data": [{"granularity": "DAILY", "product_type": "...",
               "data_points": [{"template_id": "...", "start": <unix>, "end": <unix>,
                                "sent": int, "delivered": int, "read": int,
                                "clicked": [{"type": "quick_reply_button|unique_url_button|url_button",
                                             "button_content": "...", "count": int}],
                                "cost": [{"type": "amount_spent|cost_per_delivered|cost_per_url_button_click",
                                          "value": number}]}]}],
     "paging": {"cursors": {"before": "...", "after": "..."}}}

``clicked`` exists only for MARKETING/UTILITY templates with URL/Quick Reply buttons (absent
for EU/Japan). The view-metrics page
(.../whatsapp/marketing-messages/view-metrics) documents MM conversion metrics only for the
Marketing API Insights endpoint, not their ``template_analytics`` data-point field names or
units, so any unknown numeric key on a data point is kept under ``conversions`` (upper-cased)
and nothing else is assumed. Currency is not in the payload.

Unavailable values are ``None``, never 0. Duplicate (template_id, day) points are merged
field by field (first non-None value wins), so repeated pages never double count.
"""

import math
import re
from collections import Counter
from datetime import date, datetime, timezone

from msuite_core.constants import SECONDS_PER_MINUTE
from msuite_whatsapp.constants import (
	WABA_UTC_OFFSET_MAX_MINUTES,
	WABA_UTC_OFFSET_MIN_MINUTES,
	WABA_UTC_OFFSET_STEP_MINUTES,
)

SECONDS_PER_DAY = 86400
HALF_DAY_SECONDS = SECONDS_PER_DAY // 2
MAX_INT_COLUMN = 2**63 - 1  # signed BIGINT ceiling; larger values are treated as unavailable
_DAY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_STRUCTURAL_KEYS = frozenset({"template_id", "start", "end", "sent", "delivered", "read", "clicked", "cost"})
_COUNT_FIELDS = ("sent", "delivered", "read")
_CLICK_URL = "url_button"
_CLICK_UNIQUE_URL = "unique_url_button"
_CLICK_QUICK_REPLY = "quick_reply_button"
_COST_FIELDS = {
	"amount_spent": "amount_spent",
	"cost_per_delivered": "cost_per_delivered",
	"cost_per_url_button_click": "cost_per_click",
}
_VALUE_FIELDS = (*_COUNT_FIELDS, "clicked", "quick_reply_clicked", *_COST_FIELDS.values())


def _to_number(value):
	"""Return a finite, non-negative float for int/float/numeric-string input, else None."""
	if isinstance(value, bool) or not isinstance(value, (int, float, str)):
		return None
	try:
		number = float(value)
	except ValueError:
		return None
	return number if math.isfinite(number) and number >= 0 else None


def _to_count(value):
	"""Return a non-negative whole number within MAX_INT_COLUMN, else None."""
	if isinstance(value, int) and not isinstance(value, bool):
		return value if 0 <= value <= MAX_INT_COLUMN else None  # exact: float would round 2**63-1 up
	number = _to_number(value)
	if number is None or number != int(number) or number > MAX_INT_COLUMN:
		return None
	return int(number)


def _to_day(value, utc_offset_minutes: int | None = None):
	"""Convert a unix timestamp (int/numeric string) or YYYY-MM-DD string to 'YYYY-MM-DD', else None.

	With use_waba_timezone, Meta returns each day's `start` as the WABA's LOCAL midnight in unix time
	(observed live: 1791916200 = 2026-10-13T18:30Z = 2026-10-14 00:00 in UTC+5:30).

	When `utc_offset_minutes` is provided, `start + utc_offset_minutes * 60` maps precisely to UTC
	midnight of the local calendar day for any zone between UTC-12 and UTC+14 without ambiguity.

	When `utc_offset_minutes` is None, a threshold based on `WABA_UTC_OFFSET_MAX_MINUTES` (14 hours,
	so `threshold = 86400 - 50400 = 36000`, 10:00 UTC) shifts `start` by +1 day when
	`start % 86400 >= threshold`.
	Ambiguity window analysis:
	The interval [36000, 43200] (10:00 to 12:00 UTC) represents local midnight for:
	  - UTC+12..+14 (e.g. New Zealand, Tonga, Kiribati) on calendar day D-1 in UTC;
	  - UTC-10..-12 (e.g. Hawaii, American Samoa, Baker Island) on calendar day D in UTC.
	Without explicit or derived offset information, timestamps in this window are assumed to belong
	to the positive offset (east of UTC) because active WhatsApp Business markets are concentrated
	in populated zones (e.g. Pacific/Auckland, Pacific/Tongatapu). Negative offsets from UTC-1 to UTC-9
	have `start % 86400 < 36000` and are never shifted. To resolve UTC-10..-12 unambiguously, callers
	must pass `utc_offset_minutes` (derived via `derive_utc_offset_minutes` or loaded from
	`WhatsApp Account.waba_utc_offset_minutes`).
	"""
	if isinstance(value, str) and _DAY_RE.fullmatch(value):
		try:
			datetime.strptime(value, "%Y-%m-%d")
		except ValueError:
			return None
		return value  # WABA-timezone day strings are passed through unchanged
	seconds = _to_count(value)
	if seconds is None:
		return None
	if utc_offset_minutes is not None:
		seconds += utc_offset_minutes * SECONDS_PER_MINUTE
	else:
		threshold = SECONDS_PER_DAY - (WABA_UTC_OFFSET_MAX_MINUTES * SECONDS_PER_MINUTE)
		if seconds % SECONDS_PER_DAY >= threshold:
			seconds += SECONDS_PER_DAY
	try:
		return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y-%m-%d")
	except (OverflowError, OSError, ValueError):
		return None


def _entries(value):
	"""Yield dict entries of a list, ignoring anything else."""
	return [e for e in value if isinstance(e, dict)] if isinstance(value, list) else []


def _sum_clicks(entries, click_type):
	"""Sum counts of entries of one click type (case-insensitive); None when none are usable."""
	counts = [
		_to_count(e.get("count")) for e in entries if str(e.get("type", "")).lower() == click_type
	]
	counts = [c for c in counts if c is not None]
	return sum(counts) if counts else None


def _parse_point(point, utc_offset_minutes: int | None = None):
	"""Parse one data point into a row dict, or None if template id / day is unusable."""
	fields = {str(k).lower(): v for k, v in point.items()}
	template_id = fields.get("template_id")
	if isinstance(template_id, (int, str)) and not isinstance(template_id, bool):
		template_id = str(template_id).strip()
	else:
		template_id = ""
	day = _to_day(fields.get("start"), utc_offset_minutes=utc_offset_minutes)
	if not template_id or not day:
		return None

	row = {"template_id": template_id, "metric_date": day}
	for name in _COUNT_FIELDS:
		row[name] = _to_count(fields.get(name))

	clicked = fields.get("clicked")
	row["clicks_supported"] = isinstance(clicked, list)
	click_entries = _entries(clicked)
	url_clicks = _sum_clicks(click_entries, _CLICK_URL)
	row["clicked"] = url_clicks if url_clicks is not None else _sum_clicks(click_entries, _CLICK_UNIQUE_URL)
	row["quick_reply_clicked"] = _sum_clicks(click_entries, _CLICK_QUICK_REPLY)

	costs = {name: None for name in _COST_FIELDS.values()}
	for entry in _entries(fields.get("cost")):
		target = _COST_FIELDS.get(str(entry.get("type", "")).lower())
		if target:
			costs[target] = _to_number(entry.get("value"))
	row.update(costs)

	row["purchase_value"] = None  # no documented template_analytics field; never invented
	conversions = {}
	for key, value in fields.items():
		if key not in _STRUCTURAL_KEYS:
			number = _to_number(value)
			if number is not None:
				conversions[key.upper()] = int(number) if number == int(number) else number
	row["conversions"] = conversions
	row["conversions_available"] = bool(conversions)
	return row


def _merge(existing, new):
	"""Merge ``new`` into ``existing`` in place: keep existing values, fill only the gaps."""
	for name in _VALUE_FIELDS:
		if existing[name] is None:
			existing[name] = new[name]
	existing["clicks_supported"] = existing["clicks_supported"] or new["clicks_supported"]
	for key, value in new["conversions"].items():
		existing["conversions"].setdefault(key, value)
	existing["conversions_available"] = bool(existing["conversions"])


def parse_template_analytics(payload, utc_offset_minutes: int | None = None):
	"""Parse a ``template_analytics`` response into one row per (template_id, metric_date).

	Args:
		payload: decoded JSON response; any other type yields ``[]``.
		utc_offset_minutes: optional WABA UTC offset in minutes east of UTC to resolve local dates
			unambiguously (especially for UTC-10..-12 and UTC+12..+14).

	Returns:
		list[dict] sorted by (template_id, metric_date) with keys template_id, metric_date,
		sent, delivered, read, clicked, quick_reply_clicked, amount_spent, cost_per_delivered,
		cost_per_click, purchase_value, conversions, clicks_supported, conversions_available.
		Unavailable values are None. Never raises on malformed input; has no side effects.
	"""
	if not isinstance(payload, dict):
		return []
	rows = {}
	for item in _entries(payload.get("data")):
		for point in _entries(item.get("data_points")):
			row = _parse_point(point, utc_offset_minutes=utc_offset_minutes)
			if row is None:
				continue
			key = (row["template_id"], row["metric_date"])
			if key in rows:
				_merge(rows[key], row)
			else:
				rows[key] = row
	return [rows[k] for k in sorted(rows)]


def extract_day_starts(payload):
	"""Return the set of distinct usable unix ``start`` values (whole, non-negative) in a payload.

	Anything malformed is skipped. Pure; never raises.
	"""
	if not isinstance(payload, dict):
		return set()
	starts = set()
	for item in _entries(payload.get("data")):
		for point in _entries(item.get("data_points")):
			start = _to_count({str(k).lower(): v for k, v in point.items()}.get("start"))
			if start is not None:
				starts.add(start)
	return starts


def _offset_candidates(start):
	"""Return the plausible UTC offsets (minutes) for a unix `start` that is local midnight.

	Midnight at `r` seconds past UTC midnight is either `-r` (west) or `86400 - r` (east); only
	whole multiples of WABA_UTC_OFFSET_STEP_MINUTES within the real zone range qualify, so a
	value like +12:45 also yields -11:15 (resolved by the caller's window).
	"""
	past_midnight = start % SECONDS_PER_DAY
	step = WABA_UTC_OFFSET_STEP_MINUTES * SECONDS_PER_MINUTE
	seconds = {-past_midnight, SECONDS_PER_DAY - past_midnight} if past_midnight else {0}
	return sorted(
		s // SECONDS_PER_MINUTE
		for s in seconds
		if s % step == 0 and WABA_UTC_OFFSET_MIN_MINUTES <= s // SECONDS_PER_MINUTE <= WABA_UTC_OFFSET_MAX_MINUTES
	)


def _fits_window(start, offset_minutes, window_start, window_end):
	"""True when the local calendar day of `start` at `offset_minutes` lies inside the inclusive window."""
	try:
		local = datetime.fromtimestamp(start + offset_minutes * SECONDS_PER_MINUTE, tz=timezone.utc).date()
	except (OverflowError, OSError, ValueError):
		return False
	return window_start <= local <= window_end


def derive_utc_offset_minutes(starts, window_start: date | None = None, window_end: date | None = None):
	"""Derive the WABA's UTC offset in minutes from local-midnight unix `starts`; None when unknowable.

	Args:
	    starts: iterable of unix `start` values (see `extract_day_starts`); unusable values are ignored.
	    window_start, window_end: the requested day range (inclusive). A start that fits two offsets
	        (e.g. +12:45 vs -11:15) is resolved by which one keeps its local day inside the window;
	        without a window, or when both or neither fit, that start is ignored.

	Returns:
	    int minutes east of UTC (0 is a valid offset) from the most common reading, ties going to the
	    most recent start; None when no start gives a usable reading. Pure; never raises.
	"""
	readings = []
	for start in sorted(s for s in set(starts) if isinstance(s, int) and not isinstance(s, bool) and s >= 0):
		candidates = _offset_candidates(start)
		if len(candidates) > 1 and window_start and window_end:
			candidates = [c for c in candidates if _fits_window(start, c, window_start, window_end)]
		if len(candidates) == 1:
			readings.append(candidates[0])
	if not readings:
		return None
	counts = Counter(readings)
	last_seen = {offset: index for index, offset in enumerate(readings)}
	return max(counts, key=lambda offset: (counts[offset], last_seen[offset]))
