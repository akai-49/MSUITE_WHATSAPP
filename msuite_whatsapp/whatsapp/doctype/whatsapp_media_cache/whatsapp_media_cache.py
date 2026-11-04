"""
WhatsApp Media Cache — maps (WhatsApp Account, file content hash) to a
previously-uploaded Meta media_id, so the same file isn't re-uploaded to
Meta on every send (e.g. one image attached to a 1,000-recipient broadcast).

Entries are pruned by age in upload_media() — Meta's own media_id lifetime
isn't documented precisely, so we treat anything past MEDIA_CACHE_TTL_DAYS
as stale and re-upload rather than risk sending a dead media_id.
"""

from frappe.model.document import Document


class WhatsAppMediaCache(Document):
	pass
