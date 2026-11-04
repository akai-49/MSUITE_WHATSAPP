"""Portfolio-wide unique-recipient messaging limit (Meta's rolling-24h model).
Uses the dev Redis with throwaway keys; no Graph calls."""

import uuid
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from msuite_whatsapp.services.bulk import rate_limit_service as rl

DAY = 24 * 60 * 60


class TestUniqueRecipientLimit(IntegrationTestCase):
	def setUp(self):
		self.portfolio = f"zz-test-portfolio-{uuid.uuid4().hex[:8]}"

	def tearDown(self):
		cache = frappe.cache()
		cache.delete(cache.make_key(rl._cache_key(self.portfolio)))
		cache.delete(cache.make_key(rl._cache_key(self.portfolio + "-b")))

	def _fill(self, n, tier="TIER_50", now=1_000_000.0, prefix="u"):
		for i in range(n):
			rl.check_and_claim(self.portfolio, f"{prefix}{i}", tier, now=now)

	def test_same_recipient_counts_once(self):
		for _ in range(5):
			rl.check_and_claim(self.portfolio, "919800000001", "TIER_50", now=1_000_000.0)
		self.assertEqual(rl.unique_recipients(self.portfolio, now=1_000_000.0), 1)

	def test_next_new_recipient_is_refused_at_the_limit_but_known_ones_pass(self):
		self._fill(50)
		with self.assertRaises(rl.RateLimitExceeded):
			rl.check_and_claim(self.portfolio, "brand-new", "TIER_50", now=1_000_000.0)
		rl.check_and_claim(self.portfolio, "u7", "TIER_50", now=1_000_000.0)  # already counted
		self.assertEqual(rl.unique_recipients(self.portfolio, now=1_000_000.0), 50)

	def test_window_edge(self):
		self._fill(50, now=1_000_000.0)
		with self.assertRaises(rl.RateLimitExceeded):  # 23h59m later: still counted
			rl.check_and_claim(self.portfolio, "new", "TIER_50", now=1_000_000.0 + DAY - 60)
		rl.check_and_claim(self.portfolio, "new", "TIER_50", now=1_000_000.0 + DAY + 60)  # 24h01m: free
		self.assertEqual(rl.unique_recipients(self.portfolio, now=1_000_000.0 + DAY + 60), 1)

	def test_a_resend_refreshes_the_recipients_window(self):
		rl.check_and_claim(self.portfolio, "keep", "TIER_50", now=1_000_000.0)
		rl.check_and_claim(self.portfolio, "keep", "TIER_50", now=1_000_000.0 + DAY - 10)
		self.assertEqual(rl.unique_recipients(self.portfolio, now=1_000_000.0 + DAY + 100), 1)

	def test_portfolios_are_independent(self):
		self._fill(50)
		rl.check_and_claim(self.portfolio + "-b", "other", "TIER_50", now=1_000_000.0)

	def test_unlimited_and_unknown_tiers_are_not_tracked(self):
		for tier in ("TIER_UNLIMITED", "", None, "TIER_WEIRD"):
			rl.check_and_claim(self.portfolio, "x", tier, now=1_000_000.0)
		self.assertEqual(rl.unique_recipients(self.portfolio, now=1_000_000.0), 0)

	def test_tier_2k_parses(self):
		self.assertEqual(rl._tier_limit("TIER_2K"), 2000)
		self.assertEqual(rl._tier_limit("TIER_100K"), 100_000)

	def test_redis_outage_fails_open(self):
		with patch.object(rl.frappe, "cache", side_effect=ConnectionError("down")):
			rl.check_and_claim(self.portfolio, "x", "TIER_50", now=1_000_000.0)


# ── Portfolio tier source ───────────────────────────────────────────────

from unittest.mock import MagicMock  # noqa: E402

import requests  # noqa: E402

from msuite_whatsapp.services.accounts import messaging_limit_service as ml  # noqa: E402


def _resp(body, ok=True):
	r = MagicMock()
	r.ok = ok
	r.status_code = 200 if ok else 400
	r.json.return_value = body
	return r


def _account(name, business_id, phone_id, tier="TIER_250"):
	from frappe.utils.password import set_encrypted_password

	doc = frappe.get_doc(
		{
			"doctype": "WhatsApp Account",
			"account_name": name,
			"status": "Active",
			"business_id": business_id,
			"phones": [
				{"phone_number_id": phone_id, "status": "Active", "is_default_outgoing": 1, "messaging_limit_tier": tier}
			],
		}
	)
	doc.insert(ignore_permissions=True)
	set_encrypted_password("WhatsApp Account", doc.name, "tok", "token")
	return doc


class TestPortfolioTier(IntegrationTestCase):
	def setUp(self):
		self.biz = f"zz-biz-{uuid.uuid4().hex[:8]}"

	def tearDown(self):
		frappe.cache().delete_value(ml._cache_key(self.biz))

	def test_new_field_is_preferred_over_the_deprecated_one(self):
		body = {"whatsapp_business_manager_messaging_limit": "TIER_2K", "messaging_limit_tier": "TIER_250"}
		with patch.object(ml.requests, "get", return_value=_resp(body)):
			self.assertEqual(ml.fetch_portfolio_tier("p1", "tok"), "TIER_2K")

	def test_falls_back_to_the_deprecated_field(self):
		with patch.object(ml.requests, "get", return_value=_resp({"messaging_limit_tier": "TIER_10K"})):
			self.assertEqual(ml.fetch_portfolio_tier("p1", "tok"), "TIER_10K")

	def test_graph_failure_returns_none(self):
		with patch.object(ml.requests, "get", return_value=_resp({"error": {"message": "bad"}}, ok=False)):
			self.assertIsNone(ml.fetch_portfolio_tier("p1", "tok"))
		with patch.object(ml.requests, "get", side_effect=requests.ConnectionError("down")):
			self.assertIsNone(ml.fetch_portfolio_tier("p1", "tok"))

	def test_refresh_updates_every_phone_in_the_portfolio_and_caches(self):
		a = _account("zz ml A", self.biz, f"{self.biz}-1")
		b = _account("zz ml B", self.biz, f"{self.biz}-2")
		with patch.object(ml, "fetch_portfolio_tier", return_value="TIER_10K"):
			ml.refresh_portfolio(self.biz)
		for acc in (a, b):
			self.assertEqual(frappe.db.get_value("WhatsApp Phone Number", {"parent": acc.name}, "messaging_limit_tier"), "TIER_10K")
		with patch.object(ml, "fetch_portfolio_tier", side_effect=AssertionError("must use cache")):
			self.assertEqual(ml.get_portfolio_tier(self.biz), "TIER_10K")

	def test_without_cache_the_stored_tier_is_used(self):
		_account("zz ml C", self.biz, f"{self.biz}-3", tier="TIER_1K")
		self.assertEqual(ml.get_portfolio_tier(self.biz), "TIER_1K")

	def test_failed_refresh_keeps_the_last_known_tier(self):
		_account("zz ml D", self.biz, f"{self.biz}-4", tier="TIER_1K")
		with patch.object(ml, "fetch_portfolio_tier", return_value=None):
			ml.refresh_portfolio(self.biz)
		self.assertEqual(ml.get_portfolio_tier(self.biz), "TIER_1K")

	def test_refresh_all_survives_one_failing_portfolio(self):
		_account("zz ml E", self.biz, f"{self.biz}-5")
		other = f"{self.biz}-other"
		_account("zz ml F", other, f"{other}-6")
		seen = []

		def fake(business_id):
			seen.append(business_id)
			if business_id == self.biz:
				raise RuntimeError("boom")

		with patch.object(ml, "refresh_portfolio", side_effect=fake):
			ml.refresh_all()
		self.assertIn(self.biz, seen)
		self.assertIn(other, seen)


# ── Bulk send wiring ────────────────────────────────────────────────────

from msuite_whatsapp.services.bulk import bulk_send_service as bulk  # noqa: E402


class TestBulkSendUsesThePortfolioLimit(IntegrationTestCase):
	def setUp(self):
		self.biz = f"zz-biz-{uuid.uuid4().hex[:8]}"

	def tearDown(self):
		cache = frappe.cache()
		cache.delete(cache.make_key(rl._cache_key(self.biz)))
		cache.delete_value(ml._cache_key(self.biz))

	def test_two_accounts_in_one_portfolio_share_the_limit(self):
		a = _account("zz bs A", self.biz, f"{self.biz}-1", tier="TIER_50")
		b = _account("zz bs B", self.biz, f"{self.biz}-2", tier="TIER_50")
		for i in range(50):
			self.assertFalse(bulk._is_rate_limited(frappe._dict(whatsapp_account=a.name), f"91980000{i:04d}"))
		# a new recipient is refused on EITHER account - they are one portfolio
		self.assertTrue(bulk._is_rate_limited(frappe._dict(whatsapp_account=a.name), "919999999999"))
		self.assertTrue(bulk._is_rate_limited(frappe._dict(whatsapp_account=b.name), "919999999999"))
		# a recipient already messaged is still fine from the other account
		self.assertFalse(bulk._is_rate_limited(frappe._dict(whatsapp_account=b.name), "919800000003"))

	def test_fresh_portfolio_tier_beats_a_stale_stored_one(self):
		a = _account("zz bs C", self.biz, f"{self.biz}-3", tier="TIER_50")
		frappe.cache().set_value(ml._cache_key(self.biz), "TIER_UNLIMITED", expires_in_sec=60)
		for i in range(60):  # past the stale 50, but Meta has since raised the portfolio
			self.assertFalse(bulk._is_rate_limited(frappe._dict(whatsapp_account=a.name), f"91970000{i:04d}"))

	def test_account_without_a_business_id_is_its_own_portfolio(self):
		a = _account("zz bs D", "", f"{self.biz}-4", tier="TIER_50")
		self.addCleanup(lambda: frappe.cache().delete(frappe.cache().make_key(rl._cache_key(a.name))))
		self.assertFalse(bulk._is_rate_limited(frappe._dict(whatsapp_account=a.name), "919700000001"))
		self.assertEqual(rl.unique_recipients(a.name), 1)

	def test_no_account_or_no_recipient_is_never_limited(self):
		self.assertFalse(bulk._is_rate_limited(frappe._dict(whatsapp_account=None), "919800000001"))
		a = _account("zz bs E", self.biz, f"{self.biz}-5", tier="TIER_50")
		self.assertFalse(bulk._is_rate_limited(frappe._dict(whatsapp_account=a.name), ""))
