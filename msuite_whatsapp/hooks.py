app_name = "msuite_whatsapp"
app_title = "MSuite WhatsApp"
app_publisher = "MSuite"
app_description = "WhatsApp Business for MSuite: numbers, templates, lists, broadcasts, flows, calling and analytics."
app_email = "dev@msuite.com"
app_license = "mit"

# Apps
# ------------------

required_apps = []

before_install = "msuite_whatsapp.install.before_install"

# WhatsApp, moved from msuite_workspace
# ------------------

_PE = "msuite_core.services.plans.plan_enforcer"
_CCE = "msuite_campaigns.campaign.doctype.campaign_calendar_event.campaign_calendar_event"

# This app's records in the global search. The key sets the order of the groups.
msuite_search_sources = {"50_whatsapp_accounts": "msuite_whatsapp.services.home.search.search"}

# This app's records in the Home page's recent list.
msuite_home_recent = {"40_whatsapp_broadcasts": "msuite_whatsapp.services.home.recent.recent_broadcasts"}

# This app's plan limits, read by msuite_core.services.plans.plan_enforcer.
msuite_plan_gates = ["msuite_whatsapp.services.plan_gates.GATES"]

doc_events = {
	"WhatsApp Templates": {"before_insert": f"{_PE}.enforce_gate", "before_save": f"{_PE}.enforce_gate"},
	"WhatsApp Flow": {"before_insert": f"{_PE}.enforce_gate"},
	"WhatsApp Call": {"before_insert": f"{_PE}.enforce_gate"},
	"Bulk WhatsApp Message": {
		"before_insert": f"{_PE}.check_bulk_messaging",
		"before_save": f"{_PE}.check_bulk_messaging",
		"before_submit": f"{_PE}.check_bulk_messaging",
		# Calendar sync
		"after_insert": f"{_CCE}.on_source_save",
		"on_update": f"{_CCE}.on_source_save",
		"on_trash": f"{_CCE}.on_source_delete",
	},
	"WhatsApp Recipient List": {
		"before_insert": f"{_PE}.check_recipient_list",
		"before_save": f"{_PE}.check_recipient_list",
	},
}

# Automation asks this channel for its sends through this hook.
msuite_automation_steps = {"WhatsApp": "msuite_whatsapp.services.channels.automation_channel"}

# Inbox finds this channel through this hook.
msuite_inbox_channels = {"WhatsApp": "msuite_whatsapp.services.channels.inbox_channel"}

campaign_channel_adapters = ["msuite_whatsapp.services.channels.campaign_adapter.ADAPTER"]

# CRM's WhatsApp tab (`WhatsAppArea.vue` + `WhatsAppBox.vue`) calls the
# methods below. The first two make CRM show the tab. Our overrides funnel every send through
# `inbox.services.outbound.send_to_phone` and every read off `Channel
# Message`, so the CRM frontend keeps working unchanged while the data
# layer is unified with the Inbox SPA.
override_whitelisted_methods = {
	"crm.api.whatsapp.is_whatsapp_enabled": "msuite_whatsapp.api.v1.crm.whatsapp.is_whatsapp_enabled",
	"crm.api.whatsapp.is_whatsapp_installed": "msuite_whatsapp.api.v1.crm.whatsapp.is_whatsapp_installed",
	"crm.api.whatsapp.create_whatsapp_message": "msuite_whatsapp.api.v1.crm.whatsapp.create_whatsapp_message",
	"crm.api.whatsapp.send_whatsapp_template": "msuite_whatsapp.api.v1.crm.whatsapp.send_whatsapp_template",
	"crm.api.whatsapp.react_on_whatsapp_message": "msuite_whatsapp.api.v1.crm.whatsapp.react_on_whatsapp_message",
	"crm.api.whatsapp.get_whatsapp_messages": "msuite_whatsapp.api.v1.crm.whatsapp.get_whatsapp_messages",
}

# Frappe CRM's /crm page, served with the msuite WhatsApp panel added to the Lead and Deal
# WhatsApp tab. The panel is built from `frontend/` (`cd frontend && npm run build`).
page_renderer = ["msuite_whatsapp.crm_tab.renderer.CRMPageWithWhatsApp"]

scheduler_events = {
	"cron": {
		"*/5 * * * *": [
			"msuite_whatsapp.tasks.jobs.schedule_bulk_messages",
			# Call janitor — marks Ringing rows >2 min and Connected
			# rows >2 h as Failed so a tab close / JS crash / lost
			# webhook can't strand an agent in the busy gate forever.
			"msuite_whatsapp.tasks.jobs.sweep_stale_calls",
		],
		# Analytics sync — messaging, conversation, pricing, call — every 6 hours
		"0 */6 * * *": [
			"msuite_whatsapp.tasks.jobs.sync_all_accounts",
		],
		"0 * * * *": [
			# Meta raises a portfolio's messaging limit on its own schedule; keep the
			# tier the bulk-send governor enforces current.
			"msuite_whatsapp.tasks.jobs.refresh_all",
		],
		"0 3 * * *": [
			"msuite_whatsapp.tasks.jobs.sync_daily_tasks",
		],
	},
}

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "msuite_whatsapp",
# 		"logo": "/assets/msuite_whatsapp/logo.png",
# 		"title": "MSuite WhatsApp",
# 		"route": "/msuite_whatsapp",
# 		"has_permission": "msuite_whatsapp.api.permission.has_app_permission",
# 	}
# ]

# The dock, the rail down the left of the desk, is a document rather than a hook. Author it in
# Manage Dock on a developer-mode site and press Export to App, and it is written to
# `msuite_whatsapp/dock/msuite_whatsapp/msuite_whatsapp.json` for git to carry. An app that ships none has no
# rail: its sidebar gets a switcher in the header instead.
#
# A companion app, one that extends a host app rather than standing on its own, says so with
# `mount_on` on that same record, and its entries are appended to the host's rail. Mounting keeps
# the companion off the apps screen, so it takes precedence over any add_to_apps_screen above.

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/msuite_whatsapp/css/msuite_whatsapp.css"
# app_include_js = "/assets/msuite_whatsapp/js/msuite_whatsapp.js"

# include js, css files in header of web template
# web_include_css = "/assets/msuite_whatsapp/css/msuite_whatsapp.css"
# web_include_js = "/assets/msuite_whatsapp/js/msuite_whatsapp.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "msuite_whatsapp/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_kanban_js = {"doctype" : "public/js/doctype_kanban.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "msuite_whatsapp/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "msuite_whatsapp.utils.jinja_methods",
# 	"filters": "msuite_whatsapp.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "msuite_whatsapp.install.before_install"
# after_install = "msuite_whatsapp.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "msuite_whatsapp.uninstall.before_uninstall"
# after_uninstall = "msuite_whatsapp.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "msuite_whatsapp.utils.before_app_install"
# after_app_install = "msuite_whatsapp.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "msuite_whatsapp.utils.before_app_uninstall"
# after_app_uninstall = "msuite_whatsapp.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "msuite_whatsapp.build.after_build"

# To hook into the build process of other apps
# The list of apps being built is passed as an argument

# after_app_build = "msuite_whatsapp.build.after_app_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "msuite_whatsapp.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["msuite_whatsapp.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"msuite_whatsapp.tasks.all"
# 	],
# 	"daily": [
# 		"msuite_whatsapp.tasks.daily"
# 	],
# 	"hourly": [
# 		"msuite_whatsapp.tasks.hourly"
# 	],
# 	"weekly": [
# 		"msuite_whatsapp.tasks.weekly"
# 	],
# 	"monthly": [
# 		"msuite_whatsapp.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "msuite_whatsapp.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "msuite_whatsapp.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "msuite_whatsapp.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "msuite_whatsapp.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["msuite_whatsapp.utils.before_request"]
# after_request = ["msuite_whatsapp.utils.after_request"]

# Job Events
# ----------
# before_job = ["msuite_whatsapp.utils.before_job"]
# after_job = ["msuite_whatsapp.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"msuite_whatsapp.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

_CONNECT = "msuite_whatsapp.services.accounts.connect"
msuite_credential_handlers = {
	"WhatsApp": f"{_CONNECT}._handle_whatsapp_credentials",
	"whatsapp": f"{_CONNECT}._handle_whatsapp_credentials",
}
msuite_connected_accounts = {"whatsapp": f"{_CONNECT}.connected_accounts"}
msuite_analytics_agent_accounts = {"whatsapp_accounts": f"{_CONNECT}.analytics_agent_accounts"}
