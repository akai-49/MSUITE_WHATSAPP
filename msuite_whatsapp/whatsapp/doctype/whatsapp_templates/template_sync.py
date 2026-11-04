"""
Deprecated location — kept as a backward-compatible re-export.

The real implementation moved to
`msuite_whatsapp.services.templates.template_sync_service`, with its endpoint
in `msuite_whatsapp.api.v1.app.template_sync`, as part of the WhatsApp module refactor (see WHATSAPP_REFACTOR_PLAN.md §5). The
whitelisted endpoint at this dotted path keeps working unchanged since
`fetch` is the same function object, just re-exported under its
original name and location.
"""

from msuite_whatsapp.queries.template_repository import upsert_without_hooks as _upsert_doc_without_hooks
from msuite_whatsapp.services.templates.template_sync_service import (
	_apply_component,
	_sync_buttons,
	_sync_template,
)
from msuite_whatsapp.api.v1.app.template_sync import sync_all_accounts as fetch
