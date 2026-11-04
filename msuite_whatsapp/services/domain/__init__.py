"""
Shared WhatsApp domain constants.

Thin re-export of the WhatsApp-relevant subset of `msuite_core.constants`
so code under `whatsapp/` can do `from msuite_whatsapp.services.domain import X`
instead of reaching into the app-wide constants module directly. The
app-wide module remains the single source of truth — nothing is
redefined here.
"""

from msuite_core.constants import (
	GRAPH_API_BASE,
	GRAPH_API_VERSION,
	LOGGER_NAME,
	REQUEST_TIMEOUT,
	CallDirection,
)
from msuite_whatsapp.constants import (
	ANALYTICS_INTER_ACCOUNT_DELAY,
	ANALYTICS_REFETCH_DAYS,
	ANALYTICS_SNAPSHOT_RETENTION,
	BUTTON_TYPE_TO_META,
	CALL_PERMISSION_AUTO_REVOKE_THRESHOLD,
	CALL_PERMISSION_COOLDOWN_HOURS,
	CALL_STATUS_MAP,
	CALL_TERMINAL_STATES,
	HEADER_FORMATS,
	META_TO_BUTTON_TYPE,
	TEMPLATE_ANALYTICS_BATCH_SIZE,
	TEMPLATE_CATEGORIES,
	WHATSAPP_MEDIA_CACHE_TTL_DAYS,
	AnalyticsGranularity,
	BulkMessageStatus,
	CallStatus,
	MessageStatus,
	MessageType,
	MetricType,
	ParameterFormat,
	PermissionStatus,
	TemplateStatus,
)

__all__ = [
	"ANALYTICS_INTER_ACCOUNT_DELAY",
	"ANALYTICS_REFETCH_DAYS",
	"ANALYTICS_SNAPSHOT_RETENTION",
	"BUTTON_TYPE_TO_META",
	"CALL_PERMISSION_AUTO_REVOKE_THRESHOLD",
	"CALL_PERMISSION_COOLDOWN_HOURS",
	"CALL_STATUS_MAP",
	"CALL_TERMINAL_STATES",
	"GRAPH_API_BASE",
	"GRAPH_API_VERSION",
	"HEADER_FORMATS",
	"LOGGER_NAME",
	"META_TO_BUTTON_TYPE",
	"REQUEST_TIMEOUT",
	"TEMPLATE_ANALYTICS_BATCH_SIZE",
	"TEMPLATE_CATEGORIES",
	"WHATSAPP_MEDIA_CACHE_TTL_DAYS",
	"AnalyticsGranularity",
	"BulkMessageStatus",
	"CallDirection",
	"CallStatus",
	"MessageStatus",
	"MessageType",
	"MetricType",
	"ParameterFormat",
	"PermissionStatus",
	"TemplateStatus",
]
