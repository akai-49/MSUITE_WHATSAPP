"""Compatibility layer for running msuite_whatsapp standalone without msuite_core, msuite_inbox, or msuite_campaigns."""

from __future__ import annotations
import sys
import types


def install():
	"""Register stubs in sys.modules if real packages are not present."""
	_safe_logger()
	_install_msuite_core()
	_install_msuite_inbox()
	_install_msuite_campaigns()


def _safe_logger():
	import logging
	try:
		import frappe
		orig_logger = frappe.logger
		def safe_logger(*args, **kwargs):
			try:
				return orig_logger(*args, **kwargs)
			except (FileNotFoundError, OSError):
				return logging.getLogger(args[0] if args else "frappe")
		frappe.logger = safe_logger
	except Exception:
		pass


def _install_msuite_core():
	if "msuite_core" in sys.modules:
		return
	try:
		import importlib.util
		if importlib.util.find_spec("msuite_core") is not None:
			return
	except Exception:
		pass

	from msuite_whatsapp import constants, central_config
	from msuite_whatsapp.utils import phone, files, insight_keys, import_guard
	from msuite_whatsapp.services.permissions import checks, roles
	from msuite_whatsapp.services.plans import plan_enforcer
	from msuite_whatsapp.services.validation import phone as phone_validation
	from msuite_whatsapp.integrations import provider_auth

	# Root package
	core = types.ModuleType("msuite_core")
	core.constants = constants
	core.central_config = central_config
	core.__file__ = constants.__file__
	core.__path__ = []

	sys.modules["msuite_core"] = core
	sys.modules["msuite_core.constants"] = constants
	sys.modules["msuite_core.central_config"] = central_config

	# Permissions
	services = types.ModuleType("msuite_core.services")
	services.__path__ = []
	perms = types.ModuleType("msuite_core.services.permissions")
	perms.__path__ = []
	perms.checks = checks
	perms.roles = roles
	services.permissions = perms
	services.permissions.checks = checks
	services.permissions.roles = roles
	sys.modules["msuite_core.services"] = services
	sys.modules["msuite_core.services.permissions"] = perms
	sys.modules["msuite_core.services.permissions.checks"] = checks
	sys.modules["msuite_core.services.permissions.roles"] = roles

	# Plans
	plans = types.ModuleType("msuite_core.services.plans")
	plans.__path__ = []
	plans.plan_enforcer = plan_enforcer
	services.plans = plans
	sys.modules["msuite_core.services.plans"] = plans
	sys.modules["msuite_core.services.plans.plan_enforcer"] = plan_enforcer

	# Validation
	validation = types.ModuleType("msuite_core.services.validation")
	validation.__path__ = []
	validation.phone = phone_validation
	services.validation = validation
	sys.modules["msuite_core.services.validation"] = validation
	sys.modules["msuite_core.services.validation.phone"] = phone_validation

	# Connections
	connections = types.ModuleType("msuite_core.services.connections")
	connections.__path__ = []
	profile = types.ModuleType("msuite_core.services.connections.profile")
	profile._enqueue_account_avatar = lambda *a, **k: None
	profile._refresh_whatsapp_account = lambda *a, **k: None
	connections.profile = profile
	services.connections = connections
	sys.modules["msuite_core.services.connections"] = connections
	sys.modules["msuite_core.services.connections.profile"] = profile

	# Notifications
	notifications = types.ModuleType("msuite_core.services.notifications")
	def _create_notif(*a, **k):
		return None
	notifications.create_notification_log = _create_notif
	services.notifications = notifications
	sys.modules["msuite_core.services.notifications"] = notifications

	# Utils
	utils = types.ModuleType("msuite_core.utils")
	utils.__path__ = []
	utils.phone = phone
	utils.files = files
	utils.insight_keys = insight_keys
	utils.import_guard = import_guard
	core.utils = utils
	sys.modules["msuite_core.utils"] = utils
	sys.modules["msuite_core.utils.phone"] = phone
	sys.modules["msuite_core.utils.files"] = files
	sys.modules["msuite_core.utils.insight_keys"] = insight_keys
	sys.modules["msuite_core.utils.import_guard"] = import_guard

	# Integrations
	integrations = types.ModuleType("msuite_core.integrations")
	integrations.__path__ = []
	integrations.provider_auth = provider_auth
	core.integrations = integrations
	sys.modules["msuite_core.integrations"] = integrations
	sys.modules["msuite_core.integrations.provider_auth"] = provider_auth


def _install_msuite_inbox():
	if "msuite_inbox" in sys.modules:
		return
	try:
		import importlib.util
		if importlib.util.find_spec("msuite_inbox") is not None:
			return
	except Exception:
		pass

	inbox_pkg = types.ModuleType("msuite_inbox")
	inbox_pkg.__path__ = []
	inbox_mod = types.ModuleType("msuite_inbox.inbox")
	inbox_mod.__path__ = []

	# Constants
	inbox_constants = types.ModuleType("msuite_inbox.inbox.constants")
	inbox_constants.LOGGER_NAME = "msuite_inbox"
	inbox_constants.STICKER_MIME = "image/webp"

	class ChannelType:
		WHATSAPP = "WhatsApp"
		EMAIL = "Email"
		SMS = "SMS"
		INSTAGRAM_DM = "Instagram DM"
		FACEBOOK_DM = "Facebook DM"
		ALL = ["WhatsApp", "Instagram DM", "Facebook DM"]

	class Direction:
		INBOUND = "Inbound"
		OUTBOUND = "Outbound"

	class MessageContentType:
		TEXT = "Text"
		IMAGE = "Image"
		VIDEO = "Video"
		AUDIO = "Audio"
		DOCUMENT = "Document"
		STICKER = "Sticker"
		LOCATION = "Location"
		CONTACTS = "Contacts"
		REACTION = "Reaction"
		INTERACTIVE = "Interactive"
		TEMPLATE = "Template"
		FLOW_RESPONSE = "Flow Response"
		ORDER = "Order"
		SYSTEM = "System"
		CALL = "Call"
		UNKNOWN = "Unknown"

	class MessageStatus:
		QUEUED = "Queued"
		SENT = "Sent"
		DELIVERED = "Delivered"
		READ = "Read"
		FAILED = "Failed"

	class SenderType:
		CUSTOMER = "Customer"
		USER = "User"
		AGENT = "Agent"
		BOT = "Bot"
		SYSTEM = "System"
		ALL = ["Customer", "Agent", "Bot", "System"]

	class SourceType:
		MANUAL = "Manual"
		AUTOMATION = "Automation"
		CAMPAIGN = "Campaign"

	inbox_constants.ChannelType = ChannelType
	inbox_constants.Direction = Direction
	inbox_constants.MessageContentType = MessageContentType
	inbox_constants.MessageStatus = MessageStatus
	inbox_constants.SenderType = SenderType
	inbox_constants.SourceType = SourceType

	# Services
	services = types.ModuleType("msuite_inbox.inbox.services")
	services.__path__ = []

	outbound = types.ModuleType("msuite_inbox.inbox.services.outbound")
	outbound.send_to_phone = lambda *a, **k: None
	outbound.send_message = lambda *a, **k: None
	outbound._upsert_handle = lambda *a, **k: None
	services.outbound = outbound

	dispatcher = types.ModuleType("msuite_inbox.inbox.services.dispatcher")
	dispatcher.handle = lambda *a, **k: None
	dispatcher.is_handle_opted_out = lambda *a, **k: False
	services.dispatcher = dispatcher

	ad_referral = types.ModuleType("msuite_inbox.inbox.services.ad_referral")
	ad_referral.handle = lambda *a, **k: None
	services.ad_referral = ad_referral

	from dataclasses import dataclass, field
	from datetime import datetime

	@dataclass
	class NormalizedAttachment:
		media_type: str = ""
		file_url: str = ""
		file_name: str = ""
		mime_type: str = ""
		caption: str = ""
		metadata: dict = field(default_factory=dict)

		def to_row(self) -> dict:
			return {
				"media_type": self.media_type,
				"file_url": self.file_url,
				"file_name": self.file_name,
				"mime_type": self.mime_type,
				"caption": self.caption,
				"metadata": self.metadata or None,
			}

	@dataclass
	class NormalizedEvent:
		channel_type: str
		inbox: str
		platform_handle: str
		display_name: str = ""
		profile_picture_url: str = ""
		direction: str = Direction.INBOUND
		content_type: str = MessageContentType.TEXT
		text_content: str = ""
		platform_message_id: str = ""
		reply_to_platform_id: str = ""
		platform_timestamp: datetime | None = None
		sender_type: str = SenderType.CUSTOMER
		sender_user: str = ""
		sender_name: str = ""
		sender_phone: str = ""
		sender_email: str = ""

	def parse_unix_timestamp(value):
		if not value:
			return None
		try:
			from frappe.utils import get_datetime
			return get_datetime(value)
		except Exception:
			return None

	def excerpt(text, limit=140):
		text = (text or "").strip().replace("\n", " ").replace("\r", " ")
		return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"

	normalizer = types.ModuleType("msuite_inbox.inbox.services.normalizer")
	normalizer.normalize = lambda *a, **k: {}
	normalizer.NormalizedAttachment = NormalizedAttachment
	normalizer.NormalizedEvent = NormalizedEvent
	normalizer.parse_unix_timestamp = parse_unix_timestamp
	normalizer.excerpt = excerpt
	services.normalizer = normalizer

	inbox_connector = types.ModuleType("msuite_inbox.inbox.services.inbox_connector")
	inbox_connector.per_account_whatsapp_inbox_name = lambda *a, **k: "WhatsApp Inbox"
	services.inbox_connector = inbox_connector

	# API
	api = types.ModuleType("msuite_inbox.inbox.api")
	api.__path__ = []
	api_v1 = types.ModuleType("msuite_inbox.inbox.api.v1")
	api_v1.__path__ = []
	conv = types.ModuleType("msuite_inbox.inbox.api.v1.conversation")
	conv.react_to_message = lambda *a, **k: None
	api_v1.conversation = conv

	webhook = types.ModuleType("msuite_inbox.inbox.api.v1.webhook")
	webhook._ensure_default_inbox_exists = lambda *a, **k: None
	webhook._STATUS_RANK = {}
	api_v1.webhook = webhook
	api.v1 = api_v1

	# Events
	events = types.ModuleType("msuite_inbox.inbox.events")
	events.emit = lambda *a, **k: None
	events.CONVERSATION_CREATED = "ConversationCreated"
	events.CONVERSATION_ASSIGNED = "ConversationAssigned"
	events.CONVERSATION_RESOLVED = "ConversationResolved"
	events.MESSAGE_RECEIVED = "MessageReceived"
	events.MESSAGE_SENT = "MessageSent"
	events.LABEL_ADDED = "LabelAdded"
	events.CALL_STARTED = "CallStarted"
	events.CALL_ENDED = "CallEnded"
	events.ALL_EVENTS = (
		events.CONVERSATION_CREATED,
		events.CONVERSATION_ASSIGNED,
		events.CONVERSATION_RESOLVED,
		events.MESSAGE_RECEIVED,
		events.MESSAGE_SENT,
		events.LABEL_ADDED,
		events.CALL_STARTED,
		events.CALL_ENDED,
	)
	inbox_mod.events = events

	sys.modules["msuite_inbox"] = inbox_pkg
	sys.modules["msuite_inbox.inbox"] = inbox_mod
	sys.modules["msuite_inbox.inbox.events"] = events
	sys.modules["msuite_inbox.inbox.constants"] = inbox_constants
	sys.modules["msuite_inbox.inbox.services"] = services
	sys.modules["msuite_inbox.inbox.services.outbound"] = outbound
	sys.modules["msuite_inbox.inbox.services.dispatcher"] = dispatcher
	sys.modules["msuite_inbox.inbox.services.ad_referral"] = ad_referral
	sys.modules["msuite_inbox.inbox.services.normalizer"] = normalizer
	sys.modules["msuite_inbox.inbox.services.inbox_connector"] = inbox_connector
	sys.modules["msuite_inbox.inbox.api"] = api
	sys.modules["msuite_inbox.inbox.api.v1"] = api_v1
	sys.modules["msuite_inbox.inbox.api.v1.conversation"] = conv
	sys.modules["msuite_inbox.inbox.api.v1.webhook"] = webhook


def _install_msuite_campaigns():
	if "msuite_campaigns" in sys.modules:
		return
	try:
		import importlib.util
		if importlib.util.find_spec("msuite_campaigns") is not None:
			return
	except Exception:
		pass

	camp_pkg = types.ModuleType("msuite_campaigns")
	camp_pkg.__path__ = []

	# Campaign services relationships
	campaign = types.ModuleType("msuite_campaigns.campaign")
	campaign.__path__ = []
	camp_services = types.ModuleType("msuite_campaigns.campaign.services")
	camp_services.__path__ = []
	rel = types.ModuleType("msuite_campaigns.campaign.services.relationships")
	rel.register_with_campaign = lambda *a, **k: None
	camp_services.relationships = rel
	campaign.services = camp_services

	# Campaign calendar event
	doctype = types.ModuleType("msuite_campaigns.campaign.doctype")
	doctype.__path__ = []
	cce_dir = types.ModuleType("msuite_campaigns.campaign.doctype.campaign_calendar_event")
	cce_dir.__path__ = []
	cce_mod = types.ModuleType("msuite_campaigns.campaign.doctype.campaign_calendar_event.campaign_calendar_event")
	cce_mod.on_source_save = lambda *a, **k: None
	cce_mod.on_source_delete = lambda *a, **k: None
	cce_dir.campaign_calendar_event = cce_mod
	doctype.campaign_calendar_event = cce_dir
	campaign.doctype = doctype

	# AWS pipeline
	aws = types.ModuleType("msuite_campaigns.aws_pipeline")
	aws.__path__ = []
	aws_dispatch = types.ModuleType("msuite_campaigns.aws_pipeline.dispatch")
	aws_dispatch.is_ready = lambda *a, **k: False
	aws_dispatch.export_and_enqueue = lambda *a, **k: None
	aws_dispatch.should_use_aws = lambda *a, **k: False
	aws_client = types.ModuleType("msuite_campaigns.aws_pipeline.client")
	aws_client.sync_channel_secret = lambda *a, **k: None
	aws.dispatch = aws_dispatch
	aws.client = aws_client

	manifest = types.ModuleType("msuite_campaigns.aws_pipeline.manifest")
	manifest._dynamo_campaign_id = lambda doc, channel: f"{getattr(doc, 'campaign', None) or getattr(doc, 'name', '')}:{channel}"
	aws.manifest = manifest
	sys.modules["msuite_campaigns.aws_pipeline.manifest"] = manifest

	# Dispatch
	dispatch = types.ModuleType("msuite_campaigns.dispatch")
	dispatch.__path__ = []
	dispatch_channel = types.ModuleType("msuite_campaigns.dispatch.channel")
	dispatch.channel = dispatch_channel

	# Audience
	audience = types.ModuleType("msuite_campaigns.audience")
	audience.__path__ = []
	aud_services = types.ModuleType("msuite_campaigns.audience.services")
	aud_services.__path__ = []
	contact_sync = types.ModuleType("msuite_campaigns.audience.services.contact_sync_service")
	contact_sync.record_channel_opt_in = lambda *a, **k: True
	contact_sync.record_channel_opt_out = lambda *a, **k: True
	aud_services.contact_sync_service = contact_sync
	audience.services = aud_services

	sys.modules["msuite_campaigns"] = camp_pkg
	sys.modules["msuite_campaigns.campaign"] = campaign
	sys.modules["msuite_campaigns.campaign.services"] = camp_services
	sys.modules["msuite_campaigns.campaign.services.relationships"] = rel
	sys.modules["msuite_campaigns.campaign.doctype"] = doctype
	sys.modules["msuite_campaigns.campaign.doctype.campaign_calendar_event"] = cce_dir
	sys.modules["msuite_campaigns.campaign.doctype.campaign_calendar_event.campaign_calendar_event"] = cce_mod
	sys.modules["msuite_campaigns.aws_pipeline"] = aws
	sys.modules["msuite_campaigns.aws_pipeline.dispatch"] = aws_dispatch
	sys.modules["msuite_campaigns.aws_pipeline.client"] = aws_client
	sys.modules["msuite_campaigns.dispatch"] = dispatch
	sys.modules["msuite_campaigns.dispatch.channel"] = dispatch_channel
	sys.modules["msuite_campaigns.audience"] = audience
	sys.modules["msuite_campaigns.audience.services"] = aud_services
	sys.modules["msuite_campaigns.audience.services.contact_sync_service"] = contact_sync
