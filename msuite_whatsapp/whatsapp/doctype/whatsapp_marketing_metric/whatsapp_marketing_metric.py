"""
WhatsApp Marketing Metric -- one row per (account, template, day, product type) of Meta
template_analytics. The product types are MARKETING_MESSAGES_LITE_API and CLOUD_API; they are
assumed disjoint (a send is counted under exactly one). UNVERIFIED: needs a live check with real sends.

Frappe numeric columns are NOT NULL (default 0), so a metric Meta did not report cannot be stored
as NULL. Callers pass None for it; `validate` records the name in `unavailable_fields` (JSON list)
and readers must treat those metrics as "not available", never as 0. Rows are written only
server-side by the sync job (ignore_permissions); roles only get read access.
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document

from msuite_core.constants import MM_PRODUCT_TYPE
from msuite_whatsapp.constants import MM_SYNC_PRODUCT_TYPES

# Int metrics that may be unavailable (None) but never negative.
COUNT_FIELDS = ("sent", "delivered", "read", "clicked", "quick_reply_clicked")
MONEY_FIELDS = ("amount_spent", "cost_per_delivered", "cost_per_click", "purchase_value")
UNIQUE_KEY_FIELDS = ("whatsapp_account", "template_id", "metric_date", "product_type")
UNIQUE_INDEX_NAME = "unique_account_template_day_product"
LEGACY_UNIQUE_INDEX_NAME = "unique_account_template_day"  # (account, template_id, metric_date) before product_type existed


class WhatsAppMarketingMetric(Document):
	"""Per-day Marketing Messages metrics for one template of one WhatsApp Account."""

	def load_from_db(self):
		"""Load document from DB and restore None for fields recorded in `unavailable_fields`."""
		super().load_from_db()
		self._restore_unavailable_nones()
		return self

	def _restore_unavailable_nones(self):
		"""Restore None for fields recorded in `unavailable_fields` (DB numeric columns cannot store NULL)."""
		try:
			unavail = json.loads(self.unavailable_fields or "[]")
		except (TypeError, ValueError):
			unavail = []
		metrics = COUNT_FIELDS + MONEY_FIELDS
		for f in unavail:
			if f in metrics:
				self.set(f, None)

	def validate(self):
		"""Default and check product_type, reject negative counts and duplicate keys; record unreported metrics.

		Side effects: a blank `product_type` becomes MM-Lite (rows written before the field existed);
		sets `unavailable_fields` to the JSON list of metrics passed as None.

		Raises:
		    frappe.ValidationError: unknown product type, negative count, or the key already
		    exists on another row.
		"""
		self.product_type = self.product_type or MM_PRODUCT_TYPE
		if self.product_type not in MM_SYNC_PRODUCT_TYPES:
			frappe.throw(_("Unknown product type {0}.").format(self.product_type))
		for fieldname in COUNT_FIELDS:
			value = self.get(fieldname)
			if value is not None and value < 0:
				frappe.throw(_("{0} cannot be negative.").format(self.meta.get_label(fieldname)))
		self._validate_unique_key()
		self._record_unavailable_fields()

	def _record_unavailable_fields(self):
		"""Set `unavailable_fields` from the metrics passed as None.

		A genuine 0 is a real reported value and must not be marked unavailable.
		Only fields whose value is strictly None are recorded as unavailable.
		"""
		metrics = COUNT_FIELDS + MONEY_FIELDS
		unavailable = [f for f in metrics if self.get(f) is None]
		self.unavailable_fields = json.dumps(unavailable)

	def _validate_unique_key(self):
		"""Throw if another row already holds this (account, template_id, metric_date, product_type).

		Raises:
		    frappe.DuplicateEntryError: duplicate key.
		"""
		existing = frappe.db.get_value(
			self.doctype,
			{**{k: self.get(k) for k in UNIQUE_KEY_FIELDS}, "name": ("!=", self.name)},
			"name",
		)
		if existing:
			frappe.throw(
				_("A metric row for this account, template, date and product type already exists."),
				frappe.DuplicateEntryError,
			)


def on_doctype_update():
	"""Create the DB-level unique key backing `validate` (guards concurrent writers).

	Adds the 4-column key first, then drops the legacy 3-column one (which would block a second
	product type's row for the same day). Safe to run repeatedly. Side effects: DDL on the table.
	"""
	table = "tabWhatsApp Marketing Metric"
	frappe.db.add_unique("WhatsApp Marketing Metric", list(UNIQUE_KEY_FIELDS), constraint_name=UNIQUE_INDEX_NAME)
	if frappe.db.has_index(table, LEGACY_UNIQUE_INDEX_NAME):
		frappe.db.sql_ddl(f"ALTER TABLE `{table}` DROP INDEX `{LEGACY_UNIQUE_INDEX_NAME}`")
