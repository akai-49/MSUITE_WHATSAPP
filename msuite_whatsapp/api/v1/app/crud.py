"""
Deprecated location — kept as a backward-compatible re-export layer.

This 624-line "everything" file has been split by domain into
`msuite_whatsapp/whatsapp/api/{accounts,templates,recipients,bulk_messages,flows}.py`
(see WHATSAPP_REFACTOR_PLAN.md §9). The Vue SPA calls every one of these
functions at this exact dotted path
(`msuite_whatsapp.api.v1.app.crud.*` — see
`frontend/src/stores/whatsapp.js`), so every name below is re-exported
unchanged. New code should import from the domain modules directly.
"""

from msuite_whatsapp.services.permissions.checks import check_create, check_delete, check_read, check_write
from msuite_whatsapp.api.v1.app.accounts import (
	get_country_dialing_codes,
	get_dashboard_metrics,
	get_languages_list,
	get_waba_accounts,
	get_waba_phone_numbers,
	verify_waba_connection,
)
from msuite_whatsapp.api.v1.app.bulk_messages import (
	bulk_delete_bulk_messages,
	delete_bulk_message,
	get_bulk_message,
	get_bulk_message_logs,
	get_bulk_metrics,
	insert_bulk_message,
	list_bulk_messages,
)
from msuite_whatsapp.api.v1.app.flow_responses import (
	bulk_delete_flow_responses,
	delete_flow_response,
	get_flow_response,
	get_flow_response_metrics,
	list_flow_responses,
)
from msuite_whatsapp.api.v1.app.flows import (
	bulk_delete_flows,
	create_flow_on_whatsapp,
	delete_flow,
	deprecate_flow_on_whatsapp,
	get_flow,
	get_flow_metrics,
	get_flow_preview_url,
	get_flow_status_from_whatsapp,
	list_flows,
	publish_flow_to_whatsapp,
	save_flow,
	send_test_flow,
	sync_flow_from_whatsapp,
)
from msuite_whatsapp.api.v1.app.recipients import (
	add_recipient,
	bulk_delete_recipient_lists,
	delete_recipient_list,
	delete_recipients,
	fetch_doctype_recipients,
	get_doctype_import_meta,
	get_recipient_list,
	get_recipient_metrics,
	insert_recipient_list,
	list_recipient_lists,
	list_recipients,
	preview_doctype_recipients,
	rename_recipient_list,
	search_importable_doctypes,
	update_recipient,
)
from msuite_whatsapp.api.v1.app.templates import (
	bulk_delete_templates,
	check_template_duplicate,
	delete_whatsapp_template,
	duplicate_template,
	get_template_metrics,
	get_template_send_requirements,
	get_whatsapp_template,
	get_whatsapp_template_limits,
	list_templates,
	save_whatsapp_template,
)

