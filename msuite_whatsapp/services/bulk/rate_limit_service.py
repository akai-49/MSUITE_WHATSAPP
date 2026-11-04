"""
WhatsApp send-rate governor.

Meta's messaging limit is the number of UNIQUE recipients a business portfolio
may message in a moving 24 hours, shared by every phone number in the
portfolio (Meta changelog, 8 Oct 2025). A large broadcast that ignores it gets
a wave of rejections and risks the numbers' quality rating, so bulk sends claim
a slot here first.

Schema-free: a Redis sorted set per portfolio (member = recipient, score = time
last messaged), claimed atomically in Lua. Tiers come from
`messaging_limit_service`:
  TIER_50, TIER_250, TIER_1K, TIER_2K, TIER_10K, TIER_100K, TIER_UNLIMITED
"""

from __future__ import annotations

import re
import time

import frappe

CACHE_KEY_PREFIX = "wa_send_rate"
WINDOW_SECONDS = 24 * 60 * 60  # Meta's messaging limits are a rolling 24h window
UNLIMITED_TIERS = {"TIER_UNLIMITED", "UNLIMITED", ""}


class RateLimitExceeded(Exception):
	"""Raised when a send would put the portfolio over its Meta-assigned
	unique-recipient limit. Callers should treat this as a
	retryable/deferrable condition, not a hard failure."""


def _tier_limit(messaging_limit_tier: str | None) -> int | None:
	"""Parse a Meta tier string into a numeric cap, or None if unlimited
	/ unrecognized (unrecognized tiers fail open — we never block sends
	on a parsing gap, only on a confirmed numeric cap)."""
	if not messaging_limit_tier or messaging_limit_tier.upper() in UNLIMITED_TIERS:
		return None
	match = re.match(r"TIER_(\d+)(K)?$", messaging_limit_tier.upper())
	if not match:
		return None
	value = int(match.group(1))
	if match.group(2):  # "K" suffix
		value *= 1000
	return value


def _cache_key(portfolio_id: str) -> str:
	return f"{CACHE_KEY_PREFIX}:{portfolio_id}"


# One atomic step: drop expired members, let a known recipient through (and
# refresh its time), otherwise claim a slot only while under the limit.
_CLAIM_LUA = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', tonumber(ARGV[1]) - tonumber(ARGV[2]))
local known = redis.call('ZSCORE', KEYS[1], ARGV[4])
if (not known) and redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[3]) then
  return 0
end
redis.call('ZADD', KEYS[1], ARGV[1], ARGV[4])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
return 1
"""


def check_and_claim(
	portfolio_id: str, recipient: str, messaging_limit_tier: str | None, *, now: float | None = None
) -> None:
	"""Count `recipient` against the business portfolio's rolling-24h limit of
	unique recipients (Meta shares one limit across every number in the
	portfolio). Raises `RateLimitExceeded` when `recipient` would be the one
	over the limit; a recipient already counted in the window is always free.

	Best-effort: if Redis is unreachable, fails open rather than blocking sends.
	"""
	limit = _tier_limit(messaging_limit_tier)
	if limit is None:
		return
	try:
		cache = frappe.cache()
		claimed = cache.eval(
			_CLAIM_LUA,
			1,
			cache.make_key(_cache_key(portfolio_id)),
			time.time() if now is None else now,
			WINDOW_SECONDS,
			limit,
			recipient,
		)
	except Exception:
		frappe.logger("msuite_workspace").warning(
			"WhatsApp rate-limit cache unavailable for portfolio %s - failing open", portfolio_id
		)
		return
	if not claimed:
		raise RateLimitExceeded(
			f"WhatsApp portfolio {portfolio_id!r} has reached its {messaging_limit_tier} limit "
			f"({limit} unique recipients / 24h). Send deferred."
		)


def unique_recipients(portfolio_id: str, *, now: float | None = None) -> int:
	"""Read-only: unique recipients counted in the current window."""
	try:
		cache = frappe.cache()
		key = cache.make_key(_cache_key(portfolio_id))
		cutoff = (time.time() if now is None else now) - WINDOW_SECONDS
		return int(cache.zcount(key, f"({cutoff}", "+inf"))
	except Exception:
		return 0


ACCOUNT_MEMO_ATTR = "wa_account_rate_limit_memo"


def reset_account_memo() -> None:
	"""Reset the per-job account/tier cache on frappe.local."""
	if hasattr(frappe, "local"):
		setattr(frappe.local, ACCOUNT_MEMO_ATTR, {})


def claim_for_account(account_name: str | None, recipient: str, *, fail_open: bool = True) -> bool:
	"""Claim a unique-recipient slot against the portfolio's messaging limit.
	Returns True if the send may proceed, False if rate-limited.
	When fail_open is True (default), unresolvable account or cache failure logs a
	warning and returns True (fails open).
	When fail_open is False, any exception other than RateLimitExceeded propagates
	to the caller (RateLimitExceeded still returns False).
	"""
	if not recipient:
		return True

	try:
		if not account_name:
			from msuite_inbox.inbox.services import outbound

			inbox_name = outbound._default_inbox_for_channel("WhatsApp")
			if inbox_name:
				account_name = frappe.db.get_value("Inbox", inbox_name, "whatsapp_account")

		memo = getattr(frappe.local, ACCOUNT_MEMO_ATTR, None) if hasattr(frappe, "local") else None
		if memo is None and hasattr(frappe, "local"):
			memo = {}
			setattr(frappe.local, ACCOUNT_MEMO_ATTR, memo)

		if memo is not None and account_name in memo:
			account, business_id, tier = memo[account_name]
		else:
			from msuite_whatsapp.queries import account_repository as accounts
			from msuite_whatsapp.services.accounts import messaging_limit_service

			account = accounts.get_account_doc(account_name)
			phone = accounts.get_default_phone(account, "outgoing")
			business_id = account.business_id
			tier = (business_id and messaging_limit_service.get_portfolio_tier(business_id)) or (
				phone.messaging_limit_tier if phone else None
			)
			if memo is not None:
				memo[account_name] = (account, business_id, tier)
				if account and getattr(account, "name", None):
					memo[account.name] = (account, business_id, tier)

		check_and_claim(business_id or account.name, recipient, tier)
		return True
	except RateLimitExceeded:
		return False
	except Exception as e:
		if not fail_open:
			raise
		frappe.logger("msuite_workspace").warning(
			"WhatsApp portfolio claim failed for account %s (%s) - failing open",
			account_name,
			type(e).__name__,
		)
		return True


