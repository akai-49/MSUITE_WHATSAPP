"""
WhatsApp Analytics Snapshot — stores raw Meta API analytics responses.

One record per sync run per (account + metric_type + period + granularity).
Retention: last N snapshots per key (configurable via ANALYTICS_SNAPSHOT_RETENTION).
"""

from frappe.model.document import Document


class WhatsAppAnalyticsSnapshot(Document):
	pass
