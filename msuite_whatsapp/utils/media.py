"""
Deprecated location — kept as a backward-compatible re-export layer.

The real implementation moved to `providers/meta/media_provider.py` (see
WHATSAPP_REFACTOR_PLAN.md §7/§11 — no Meta HTTP calls outside the
provider layer). New code should import from `providers.meta.media_provider`
directly.
"""

from msuite_whatsapp.integrations.meta.media_provider import get_media_header_param, upload_media
