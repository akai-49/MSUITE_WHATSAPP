"""msuite_whatsapp constants."""

from msuite_core.constants import (
	LOCAL_FILE_URL_PREFIXES,
	META_SYNC_INTER_ACCOUNT_DELAY,
	MM_PRODUCT_TYPE,
	REQUEST_TIMEOUT,
)

# Meta accepts stickers only as WebP (static <= 100 KB, animated <= 500 KB, 512x512).
# https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages#sticker-object
WHATSAPP_STICKER_MIME = "image/webp"

# Site-file URL paths that Meta cannot fetch (localhost / private) and must be uploaded instead.
LOCAL_FILE_PATH_PREFIXES = LOCAL_FILE_URL_PREFIXES
LOCAL_PRIVATE_FILE_PATH_PREFIX = LOCAL_FILE_URL_PREFIXES[1]
MEDIA_SEND_KINDS = ("image", "video", "audio", "document", "sticker")


# ── Social Accounts ──────────────────────────────────────────────────────

# Backfill this many days when a new account connects
ANALYTICS_BACKFILL_DAYS = 30

# ── WhatsApp Message ─────────────────────────────────────────────────────

class MessageType:
	INCOMING = "Incoming"
	OUTGOING = "Outgoing"


class MessageStatus:
	QUEUED = "queued"
	SENT = "sent"
	DELIVERED = "delivered"
	READ = "read"
	FAILED = "failed"

# ── WhatsApp Call ────────────────────────────────────────────────────────

class CallStatus:
	RINGING = "Ringing"
	CONNECTED = "Connected"
	COMPLETED = "Completed"
	REJECTED = "Rejected"
	MISSED = "Missed"
	FAILED = "Failed"


# Meta webhook status → our status
CALL_STATUS_MAP = {
	"RINGING": CallStatus.RINGING,
	"CONNECTED": CallStatus.CONNECTED,
	"COMPLETED": CallStatus.COMPLETED,
	"REJECTED": CallStatus.REJECTED,
	"MISSED": CallStatus.MISSED,
	"FAILED": CallStatus.FAILED,
	"BUSY": CallStatus.FAILED,
}

# Call statuses that are final — no further updates accepted
CALL_TERMINAL_STATES = (
	CallStatus.COMPLETED,
	CallStatus.REJECTED,
	CallStatus.MISSED,
	CallStatus.FAILED,
)

# ── Call Permission ──────────────────────────────────────────────────────

class PermissionStatus:
	GRANTED = "Granted"
	DECLINED = "Declined"
	PENDING = "Pending"
	REVOKED = "Revoked"


# Auto-revoke after this many consecutive missed calls
CALL_PERMISSION_AUTO_REVOKE_THRESHOLD = 4

# Minimum hours between permission requests (Meta enforces 24h)
CALL_PERMISSION_COOLDOWN_HOURS = 24

# ── WhatsApp Template ───────────────────────────────────────────────────

class TemplateStatus:
	DRAFT = "Draft"
	PENDING = "PENDING"
	APPROVED = "APPROVED"
	REJECTED = "REJECTED"
	PAUSED = "PAUSED"
	DISABLED = "DISABLED"


class ParameterFormat:
	POSITIONAL = "POSITIONAL"
	NAMED = "NAMED"


TEMPLATE_CATEGORIES = ["MARKETING", "UTILITY", "AUTHENTICATION"]
HEADER_FORMATS = ["TEXT", "IMAGE", "VIDEO", "DOCUMENT", "LOCATION", "PRODUCT"]

# Frappe select label → Meta API type
BUTTON_TYPE_TO_META = {
	"Quick Reply": "QUICK_REPLY",
	"Call Phone": "PHONE_NUMBER",
	"Visit Website": "URL",
	"Voice Call": "VOICE_CALL",
	"Flow": "FLOW",
	"OTP": "OTP",
	"Copy Offer Code": "COPY_CODE",
	"Catalog": "CATALOG",
	"MPM": "MPM",
	"SPM": "SPM",
	"Request Contact Info": "REQUEST_CONTACT_INFO",
	"REQUEST_CONTACT_INFO": "REQUEST_CONTACT_INFO",
}
# Meta API type → Frappe select label
META_TO_BUTTON_TYPE = {v: k for k, v in BUTTON_TYPE_TO_META.items()}
# OTP sub-types sent by Meta map back to "Copy Offer Code" / "OTP" in Frappe
META_TO_BUTTON_TYPE.update({
	"COPY_CODE": "Copy Offer Code",
	"ONE_TAP": "OTP",
	"ZERO_TAP": "OTP",
	"REQUEST_CONTACT_INFO": "Request Contact Info",
})


# ── WhatsApp Marketing Messages (MM) API + template extras ───────────────
# Docs: developers.facebook.com/documentation/business-messaging/whatsapp/marketing-messages/
WHATSAPP_MM_ENDPOINT = "marketing_messages"  # POST /<phone_number_id>/marketing_messages
WHATSAPP_MM_SITE_CONFIG_KEY = "whatsapp_marketing_messages_enabled"  # site_config.json opt-in, default off
WHATSAPP_MM_PRODUCT_POLICY = "CLOUD_API_FALLBACK"  # Meta falls back to Cloud API if MM onboarding is incomplete
WHATSAPP_MM_SENDABLE_CATEGORY = "MARKETING"  # MM API only accepts marketing templates
WHATSAPP_MM_FALLBACK_ERROR_CODES = frozenset({131063})  # MM not onboarded: only error safe to re-send on /messages
WHATSAPP_MEDIA_HOST_SUFFIXES = ("fbsbx.com", "fbcdn.net", "facebook.com", "whatsapp.net")  # hosts allowed to receive the Bearer token
WHATSAPP_LTO_TEXT_MAX = 16  # limited_time_offer.text max chars
WHATSAPP_COUPON_CODE_MAX = 15  # coupon/copy-code max chars (components page says 20, LTO page says 15; stricter wins)
WHATSAPP_LTO_HEADER_FORMATS = ("IMAGE", "VIDEO")
WHATSAPP_LTO_CONFIG_KEY = "limited_time_offer"  # key inside WhatsApp Templates.button_configuration JSON
# ── Bulk WhatsApp Message ────────────────────────────────────────────────

class BulkMessageStatus:
	DRAFT = "Draft"
	SCHEDULED = "Scheduled"
	QUEUED = "Queued"
	IN_PROGRESS = "In Progress"
	COMPLETED = "Completed"
	PARTIALLY_FAILED = "Partially Failed"
	CANCELLED = "Cancelled"
	AWS_DISPATCH_FAILED = "AWS Dispatch Failed"

# ── WhatsApp Analytics ───────────────────────────────────────────────────

class MetricType:
	MESSAGING = "messaging"
	CONVERSATION = "conversation"
	PRICING = "pricing"
	TEMPLATE = "template"
	CALL = "call"
	ALL = [MESSAGING, CONVERSATION, PRICING, TEMPLATE, CALL]


class AnalyticsGranularity:
	HALF_HOUR = "HALF_HOUR"
	DAY = "DAY"
	MONTH = "MONTH"


# Max templates per Meta analytics request
TEMPLATE_ANALYTICS_BATCH_SIZE = 10

# Re-fetch this many days on every sync to catch retroactive updates
ANALYTICS_REFETCH_DAYS = 7

# Keep this many snapshots per unique key before cleanup
ANALYTICS_SNAPSHOT_RETENTION = 7

# Legacy alias retained for back-compat with Social Posts analytics
# callers; new code should import META_SYNC_INTER_ACCOUNT_DELAY.
ANALYTICS_INTER_ACCOUNT_DELAY = META_SYNC_INTER_ACCOUNT_DELAY


# WhatsApp template analytics: Meta rejects look-backs beyond 90 days.
TEMPLATE_ANALYTICS_MAX_LOOKBACK_DAYS = 90
TEMPLATE_ANALYTICS_MIN_DAYS = 1
TEMPLATE_ANALYTICS_DEFAULT_DAYS = ANALYTICS_BACKFILL_DAYS
META_ANALYTICS_HTTP_TIMEOUT = REQUEST_TIMEOUT

# HTTP statuses / Graph error codes the WhatsApp analytics sync reacts to.
HTTP_STATUS_BAD_REQUEST = 400
META_TOKEN_ERROR_CODES = (190, 102)  # invalid / expired token or session
META_PERMISSION_ERROR_CODES = (10,)  # permission denied
META_PERMISSION_ERROR_CODE_RANGE = range(200, 300)  # 200-299: API permission errors


# Meta's media_id lifetime isn't documented precisely. Treat cached
# entries older than this as stale and re-upload rather than risk
# sending a dead media_id.
WHATSAPP_MEDIA_CACHE_TTL_DAYS = 25


MM_METRIC_TYPES_CORE = ("SENT", "DELIVERED", "READ", "CLICKED", "COST")
META_READ_CLICK_RETENTION_DAYS = 7  # Meta keeps Read/Click counts this long after send, then resets to 0
MM_METRICS_RETENTION_DAYS = 90  # keep WhatsApp Marketing Metric rows as long as Meta's max look-back
MM_TEMPLATE_ROWS_LIMIT = 100  # max templates returned by the per-template metrics query
MM_BROADCAST_ROWS_LIMIT = 500  # max Bulk WhatsApp Messages summed into one campaign rollup
# ── WhatsApp Marketing Messages metrics sync (mm_sync.py) ────────────────
# Docs: https://developers.facebook.com/documentation/business-messaging/whatsapp/analytics
HTTP_STATUS_TOO_MANY_REQUESTS = 429
META_THROTTLE_ERROR_CODES = (4, 17, 32, 613, 80008)  # Graph app/user/page/custom/WABA rate limits (plan U1: confirm on a real WABA)
MM_SYNC_GRANULARITY = "DAILY"  # template_analytics only accepts DAILY
MM_SYNC_LIST_SEPARATOR = ","  # documented serialisation of metric_types and template_ids lists
MM_SYNC_SKIP_DISABLED = "disabled"
MM_SYNC_SKIP_NO_TEMPLATES = "no_templates"
MM_SYNC_SKIP_NOT_AVAILABLE = "mm_not_available"
MM_SYNC_SKIP_REQUEST_FAILED = "request_failed"
MM_SYNC_SKIP_RATE_LIMITED = "rate_limited"
MM_SYNC_SKIP_REAUTH = "needs_reauth"
MM_SYNC_SKIP_PERMISSION = "permission_denied"

# WhatsApp Marketing Messages metrics query API (roadmap 5.3, Task 6).
MM_METRICS_DEFAULT_DAYS = 30  # window used when the caller passes no/invalid `days`
MM_RATE_DECIMALS = 1  # decimals of delivery/read/click rates (percent)
MM_CONVERSION_ROWS_LIMIT = MM_TEMPLATE_ROWS_LIMIT * MM_METRICS_RETENTION_DAYS  # max metric rows read to sum the `conversions` JSON

# WhatsApp Marketing Metric product types (template_analytics `product_type`; mm_sync, query, broadcast_metrics).
# Docs: https://developers.facebook.com/documentation/business-messaging/whatsapp/analytics
# UNVERIFIED: the two product types are assumed disjoint (a send is counted under exactly one); needs a live check with real sends.
CLOUD_API_PRODUCT_TYPE = "CLOUD_API"  # template_analytics product_type for sends over the normal Cloud API
MM_SYNC_PRODUCT_TYPES = (MM_PRODUCT_TYPE, CLOUD_API_PRODUCT_TYPE)  # one request series per type, per account

# ── WhatsApp WABA UTC offset derived from template_analytics `start` values (whatsapp/analytics/) ──
# Meta returns each day's `start` as WABA-local midnight (unix time) with use_waba_timezone=true.
# A fixed offset is a documented approximation: it can mis-bucket sends near a daylight-saving change.
WABA_UTC_OFFSET_FIELD = "waba_utc_offset_minutes"  # WhatsApp Account Int field (0 is a valid offset)
WABA_UTC_OFFSET_SYNCED_FIELD = "waba_utc_offset_synced_at"  # Datetime; empty means no offset was derived yet
WABA_UTC_OFFSET_MIN_MINUTES = -12 * 60  # westernmost real zone (UTC-12:00)
WABA_UTC_OFFSET_MAX_MINUTES = 14 * 60  # easternmost real zone (UTC+14:00)
WABA_UTC_OFFSET_STEP_MINUTES = 15  # every real zone offset is a multiple of 15 minutes

# ── Channel message limits ───────────────────────────────────────────────

WHATSAPP_TEMPLATE_BUTTONS_MAX = 10  # WhatsApp template total buttons cap across all types

# ── Meta WhatsApp BSUID & Messaging constants ────────────────────────────
META_RECIPIENT_FIELD_PHONE = "to"
META_RECIPIENT_FIELD_BSUID = "recipient"
META_RECIPIENT_TYPE_INDIVIDUAL = "individual"
# Meta Graph API error code for unsupported BSUID messages
# Official doc: 131062 - Business-scoped User ID (BSUID) recipients are not supported for this message.
META_ERROR_BSUID_UNSUPPORTED = 131062
META_ERROR_BSUID_UNSUPPORTED_MSG = (
	"Business-scoped User ID (BSUID) recipients are not supported for this message (Meta error 131062)."
)
# Authentication templates not supported for BSUID recipients
# Meta doc: "BSUIDs can be used to send any type of message except for one-tap, zero-tap,
# and copy code authentication templates, which require user phone numbers."
UNSUPPORTED_BSUID_TEMPLATE_CATEGORIES = ("AUTHENTICATION", "OTP")
UNSUPPORTED_BSUID_TEMPLATE_TYPES = ("OTP",)
UNSUPPORTED_BSUID_BUTTON_TYPES = ("OTP", "COPY OFFER CODE", "COPY_OFFER_CODE", "COPY_CODE")
UNSUPPORTED_BSUID_OTP_BUTTON_TYPES = ("ONE_TAP", "ZERO_TAP", "COPY_CODE", "COPY_OFFER_CODE")
BSUID_AUTH_TEMPLATE_ERROR_MESSAGE = (
	"Business-scoped user IDs (BSUID) are not supported for authentication templates "
	"(one-tap, zero-tap, and copy code). A phone number is required."
)
# Contact request constants
META_INTERACTIVE_TYPE_REQUEST_CONTACT_INFO = "request_contact_info"
META_BUTTON_TYPE_REQUEST_CONTACT_INFO = "REQUEST_CONTACT_INFO"
DEFAULT_REQUEST_CONTACT_INFO_BODY = "Please share your contact info"
CONTACT_ORIGIN_CONTACT_REQUEST = "contact_request"
WHATSAPP_STATUS_PLAYED = "played"  # voice message played; stored as read + platform_payload.played_at
WHATSAPP_ACCOUNT_EVENT_AD_LINKED = "AD_ACCOUNT_LINKED"
WHATSAPP_ACCOUNT_EVENT_MM_TERMS = "MM_LITE_TERMS_SIGNED"
WHATSAPP_AD_ACCOUNT_DEFAULT_PREFIX = "whatsapp_ad_account_linked:"  # + waba_id, stored via frappe.db.set_default
WHATSAPP_PRICING_CATEGORY_MARKETING = "marketing"  # status webhook pricing.category on the Cloud API
CHANNEL_MESSAGE_PRICING_CATEGORY_MAX_LEN = 140  # Data-field length; longer webhook values are truncated

WHATSAPP_MM_TERMS_DEFAULT_PREFIX = "whatsapp_mm_terms_signed:"  # + waba_id
MM_METRIC_TYPES_CONVERSION = (  # MM-only conversion metrics; present only when Meta returns them
	"WEBSITE_ADD_TO_CART",
	"WEBSITE_CHECKOUT_INITIATED",
	"WEBSITE_PURCHASES",
	"WEBSITE_PURCHASES_CONVERSION_VALUE",
	"WEBSITE_LEAD",
	"WEBSITE_COMPLETE_REGISTRATION",
	"APP_ADD_TO_CART",
	"APP_PURCHASES",
	"APP_LEAD",
)  # ponytail: names unverified (plan U4); parser must tolerate unknown keys, confirm with a real fixture
WHATSAPP_SEND_PATH_CLOUD_API = "cloud_api"  # Channel Message.send_path: sent via /messages
WHATSAPP_SEND_PATH_MARKETING_MESSAGES = "marketing_messages"  # sent via /marketing_messages
WHATSAPP_PRICING_CATEGORY_MARKETING_LITE = "marketing_lite"  # pricing.category / origin.type for MM API sends
