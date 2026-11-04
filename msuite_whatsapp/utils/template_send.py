"""
Deprecated location — kept as a backward-compatible re-export layer.

The real implementation moved to `providers/meta/message_provider.py`
(see WHATSAPP_REFACTOR_PLAN.md §7/§11 — no Meta payload-building outside
the provider layer). `inbox/services/channels/whatsapp.py` imports
`build_template_meta` from this exact dotted path, so it stays
re-exported here. New code should import from
`providers.meta.message_provider` directly.
"""

from msuite_whatsapp.integrations.meta.message_provider import build_template_meta
