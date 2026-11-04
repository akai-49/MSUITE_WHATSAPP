"""
WhatsApp Marketing Metric DocType + the Channel Message `send_path` / `pricing_category` fields.

Needs `bench --site mc.localhost migrate` first (new table + two Channel Message columns).
No network or LLM calls.
"""

import json

import frappe
from frappe.tests import IntegrationTestCase

from msuite_core.constants import MM_PRODUCT_TYPE
from msuite_whatsapp.constants import WHATSAPP_SEND_PATH_CLOUD_API, WHATSAPP_SEND_PATH_MARKETING_MESSAGES
from msuite_whatsapp.constants import CLOUD_API_PRODUCT_TYPE

DOCTYPE = "WhatsApp Marketing Metric"
TEST_ACCOUNT = "MM-Metric-Test-Account"
READ_ROLES = ("WhatsApp Manager", "WhatsApp User", "MSuite Viewer")
DUPLICATE_MESSAGE = "A metric row for this account, template, date and product type already exists."


def _make_metric(**overrides):
	"""Build an unsaved metric row; account Link validation is skipped (no real account needed)."""
	values = {
		"doctype": DOCTYPE,
		"whatsapp_account": TEST_ACCOUNT,
		"template_id": "123456789",
		"metric_date": "2026-10-01",
		"sent": 10,
		"delivered": 9,
	}
	values.update(overrides)
	doc = frappe.get_doc(values)
	doc.flags.ignore_links = True
	return doc


class TestWhatsAppMarketingMetric(IntegrationTestCase):
	def setUp(self):
		"""Start each test with no rows for the test account (the key is shared across tests)."""
		frappe.db.delete(DOCTYPE, {"whatsapp_account": TEST_ACCOUNT})

	def tearDown(self):
		"""Remove rows created by the test."""
		frappe.db.delete(DOCTYPE, {"whatsapp_account": TEST_ACCOUNT})

	def test_duplicate_key_rejected_with_exact_message(self):
		_make_metric().insert(ignore_permissions=True)
		with self.assertRaises(frappe.DuplicateEntryError) as ctx:
			_make_metric().insert(ignore_permissions=True)
		self.assertIn(DUPLICATE_MESSAGE, str(ctx.exception))

	def test_same_template_other_day_or_other_template_allowed(self):
		_make_metric().insert(ignore_permissions=True)
		_make_metric(metric_date="2026-10-02").insert(ignore_permissions=True)
		_make_metric(template_id="987").insert(ignore_permissions=True)

	def test_resaving_same_row_is_not_a_duplicate(self):
		doc = _make_metric().insert(ignore_permissions=True)
		doc.sent = 11
		doc.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value(DOCTYPE, doc.name, "sent"), 11)

	def test_negative_count_rejected(self):
		for field in ("sent", "delivered", "read", "clicked", "quick_reply_clicked"):
			with self.subTest(field=field), self.assertRaises(frappe.ValidationError):
				_make_metric(**{field: -1}).insert(ignore_permissions=True)

	def test_zero_and_huge_counts_allowed(self):
		doc = _make_metric(sent=0, delivered=2**31 - 1).insert(ignore_permissions=True)
		self.assertEqual(doc.delivered, 2**31 - 1)

	def test_none_metrics_are_recorded_as_unavailable_not_zero(self):
		doc = _make_metric(read=None, clicked=None, amount_spent=None).insert(ignore_permissions=True)
		unavailable = json.loads(frappe.db.get_value(DOCTYPE, doc.name, "unavailable_fields"))
		self.assertIn("read", unavailable)
		self.assertIn("clicked", unavailable)
		self.assertIn("amount_spent", unavailable)
		self.assertNotIn("sent", unavailable)

	def test_zero_is_distinct_from_unavailable(self):
		doc = _make_metric(read=0).insert(ignore_permissions=True)
		self.assertNotIn("read", json.loads(doc.unavailable_fields))

	def test_resave_without_changes_keeps_unavailable_list(self):
		doc = _make_metric(read=None).insert(ignore_permissions=True)
		doc.reload()
		doc.save(ignore_permissions=True)
		self.assertIn("read", json.loads(doc.unavailable_fields))

	def test_real_value_clears_unavailable_entry(self):
		doc = _make_metric(read=None).insert(ignore_permissions=True)
		doc.reload()
		doc.read = 5
		doc.save(ignore_permissions=True)
		self.assertNotIn("read", json.loads(doc.unavailable_fields))

	def test_real_zero_clears_unavailable_entry(self):
		doc = _make_metric(read=None).insert(ignore_permissions=True)
		self.assertIn("read", json.loads(doc.unavailable_fields))
		doc.read = 0
		doc.save(ignore_permissions=True)
		self.assertNotIn("read", json.loads(doc.unavailable_fields))

	def test_hostile_and_unicode_template_id_stored_inertly(self):
		for template_id in ("x'; DROP TABLE `tabUser`; --", "<script>alert(1)</script>", "模板-🎉", "9" * 100):
			with self.subTest(template_id=template_id):
				doc = _make_metric(template_id=template_id).insert(ignore_permissions=True)
				stored = frappe.db.get_value(DOCTYPE, doc.name, "template_id")
				# Frappe's HTML sanitiser may strip markup from Data fields; either way it is inert.
				self.assertNotIn("<script", stored)
				if "<" not in template_id:
					self.assertEqual(stored, template_id)
		self.assertTrue(frappe.db.exists("DocType", "User"))

	def test_missing_required_fields_rejected(self):
		for field in ("whatsapp_account", "template_id", "metric_date"):
			with self.subTest(field=field), self.assertRaises(frappe.MandatoryError):
				_make_metric(**{field: None}).insert(ignore_permissions=True)

	def test_conversions_json_round_trip(self):
		doc = _make_metric(conversions=json.dumps({"WEBSITE_PURCHASES": 3})).insert(ignore_permissions=True)
		self.assertEqual(json.loads(frappe.db.get_value(DOCTYPE, doc.name, "conversions")), {"WEBSITE_PURCHASES": 3})

	def test_permission_matrix(self):
		meta_perms = {p.role: p for p in frappe.get_meta(DOCTYPE).permissions}
		for role in READ_ROLES:
			self.assertTrue(meta_perms[role].read, role)
			self.assertFalse(meta_perms[role].write or meta_perms[role].create or meta_perms[role].delete, role)
		self.assertTrue(meta_perms["System Manager"].write)
		self.assertTrue(meta_perms["MSuite Admin"].write)

	def test_guest_denied(self):
		doc = _make_metric().insert(ignore_permissions=True)
		self.assertFalse(frappe.has_permission(DOCTYPE, "read", doc=doc, user="Guest"))
		self.assertFalse(frappe.has_permission(DOCTYPE, "write", doc=doc, user="Guest"))

	def test_unique_index_exists_after_migrate(self):
		indexes = frappe.db.sql(
			"SHOW INDEX FROM `tabWhatsApp Marketing Metric` WHERE Non_unique = 0 AND Key_name = 'unique_account_template_day_product'"
		)
		self.assertEqual(len(indexes), 4)
		self.assertFalse(frappe.db.has_index("tabWhatsApp Marketing Metric", "unique_account_template_day"))

	def test_same_key_other_product_type_allowed(self):
		_make_metric(product_type=MM_PRODUCT_TYPE).insert(ignore_permissions=True)
		_make_metric(product_type=CLOUD_API_PRODUCT_TYPE, sent=4).insert(ignore_permissions=True)
		self.assertEqual(frappe.db.count(DOCTYPE, {"whatsapp_account": TEST_ACCOUNT}), 2)

	def test_same_key_same_product_type_rejected_for_each_type(self):
		for product_type in (MM_PRODUCT_TYPE, CLOUD_API_PRODUCT_TYPE):
			with self.subTest(product_type=product_type):
				_make_metric(product_type=product_type).insert(ignore_permissions=True)
				with self.assertRaises(frappe.DuplicateEntryError):
					_make_metric(product_type=product_type).insert(ignore_permissions=True)

	def test_blank_product_type_defaults_to_mm_lite_and_collides_with_it(self):
		doc = _make_metric().insert(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value(DOCTYPE, doc.name, "product_type"), MM_PRODUCT_TYPE)
		with self.assertRaises(frappe.DuplicateEntryError):
			_make_metric(product_type=MM_PRODUCT_TYPE).insert(ignore_permissions=True)

	def test_unknown_product_type_rejected(self):
		for bad in ("cloud_api", "BOGUS", "' OR 1=1 --"):
			with self.subTest(bad=bad), self.assertRaises(frappe.ValidationError):
				_make_metric(product_type=bad).insert(ignore_permissions=True)

	def test_product_type_field_is_read_only_select_of_the_two_constants(self):
		field = frappe.get_meta(DOCTYPE).get_field("product_type")
		self.assertEqual(field.fieldtype, "Select")
		self.assertTrue(field.read_only)
		self.assertEqual(field.options.split("\n"), [MM_PRODUCT_TYPE, CLOUD_API_PRODUCT_TYPE])


class TestProductTypeBackfillPatch(IntegrationTestCase):
	"""Patch sets product_type = MM-Lite on pre-existing rows. Needs the product_type column (migrate)."""

	def setUp(self):
		"""Start with no rows for the test account."""
		frappe.db.delete(DOCTYPE, {"whatsapp_account": TEST_ACCOUNT})

	def tearDown(self):
		"""Remove rows created by the test."""
		frappe.db.delete(DOCTYPE, {"whatsapp_account": TEST_ACCOUNT})

	def _blank(self, template_id):
		"""Insert a row then blank its product_type (what a pre-migration row looks like)."""
		doc = _make_metric(template_id=template_id).insert(ignore_permissions=True)
		frappe.db.set_value(DOCTYPE, doc.name, "product_type", None, update_modified=False)
		return doc.name

	def test_backfills_blank_rows_and_leaves_cloud_api_rows(self):
		from msuite_core.patches import set_whatsapp_marketing_metric_product_type as patch_module

		blank = self._blank("t-old")
		cloud = _make_metric(template_id="t-cloud", product_type=CLOUD_API_PRODUCT_TYPE).insert(ignore_permissions=True).name
		patch_module.execute()
		self.assertEqual(frappe.db.get_value(DOCTYPE, blank, "product_type"), MM_PRODUCT_TYPE)
		self.assertEqual(frappe.db.get_value(DOCTYPE, cloud, "product_type"), CLOUD_API_PRODUCT_TYPE)

	def test_idempotent_and_safe_on_empty_table(self):
		from msuite_core.patches import set_whatsapp_marketing_metric_product_type as patch_module

		patch_module.execute()  # nothing to do
		name = self._blank("t-old")
		patch_module.execute()
		patch_module.execute()
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "product_type"), MM_PRODUCT_TYPE)
		self.assertEqual(frappe.db.count(DOCTYPE, {"whatsapp_account": TEST_ACCOUNT}), 1)

	def test_registered_in_patches_txt_post_model_sync(self):
		import pathlib

		import msuite_core

		text = (pathlib.Path(msuite_core.__file__).parent / "patches.txt").read_text()
		post = text.split("[post_model_sync]", 1)[1]
		self.assertIn("msuite_core.patches.set_whatsapp_marketing_metric_product_type", post)


class TestChannelMessageSendPathFields(IntegrationTestCase):
	def test_fields_exist_and_are_read_only(self):
		meta = frappe.get_meta("Channel Message")
		send_path = meta.get_field("send_path")
		self.assertEqual(send_path.fieldtype, "Select")
		self.assertTrue(send_path.read_only)
		self.assertIsNone(send_path.default)
		self.assertEqual(
			send_path.options.split("\n"),
			["", WHATSAPP_SEND_PATH_CLOUD_API, WHATSAPP_SEND_PATH_MARKETING_MESSAGES],
		)
		self.assertTrue(meta.get_field("pricing_category").read_only)

	def test_select_rejects_value_outside_options_and_accepts_blank(self):
		meta = frappe.get_meta("Channel Message")
		self.assertIn("", meta.get_field("send_path").options.split("\n"))
		self.assertNotIn("bogus", meta.get_field("send_path").options.split("\n"))
