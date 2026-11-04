"""
Deprecated location — kept as a backward-compatible re-export layer.

The real implementation moved to `providers/meta/client.py` (see
WHATSAPP_REFACTOR_PLAN.md §7/§11 — no Meta HTTP calls outside the
provider layer). `inbox/services/channels/whatsapp.py` imports
`MetaAPIError, download_media, fetch_media_url, post_to_meta` from this
exact dotted path, so all four names stay re-exported here. New code
should import from `providers.meta.client` directly.
"""

from msuite_whatsapp.integrations.meta.client import (
	MetaAPIError,
	download_media,
	fetch_media_url,
	post_to_meta,
	send_to_meta,
	verify_token,
)
