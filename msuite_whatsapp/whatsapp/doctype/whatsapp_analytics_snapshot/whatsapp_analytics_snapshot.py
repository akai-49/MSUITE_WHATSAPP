"""
WhatsApp Analytics Snapshot — stores raw Meta API analytics responses.

Compacted 1-row-per-key upsert model: exactly one snapshot row is maintained per
(whatsapp_account, metric_type, granularity) holding the latest window.
"""

from __future__ import annotations

from frappe.model.document import Document

from msuite_whatsapp.constants import AnalyticsGranularity
from msuite_core.utils.insight_keys import make_key


class WhatsAppAnalyticsSnapshot(Document):
	def before_save(self) -> None:
		"""Automatically generate snapshot_key deterministic hash if empty.

		Args:
			None.

		Returns:
			None.

		Raises:
			None.

		Side effects:
			Sets self.snapshot_key before database persistence.
		"""
		if not self.snapshot_key:
			self.snapshot_key = make_key(
				self.whatsapp_account,
				self.metric_type,
				self.granularity or AnalyticsGranularity.DAY,
			)

