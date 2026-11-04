"""This app's plan limits. Core's plan_enforcer reads them through the msuite_plan_gates hook."""

from __future__ import annotations

from msuite_core.constants import CallDirection
from msuite_core.services.plans.plan_enforcer import Gate

GATES = {
	"Channel Message": Gate(
		feature="messaging",
		product="WA",
		label="WhatsApp Messaging",
		count_doctype="Channel Message",
		period="month",
		filters={"direction": "Outbound", "channel_type": "WhatsApp"},
		# Inbound + non-WA channels never share the WhatsApp messaging quota.
		skip_if=lambda doc: (
			getattr(doc, "direction", "") != "Outbound" or getattr(doc, "channel_type", "") != "WhatsApp"
		),
	),
	"WhatsApp Templates": Gate(
		feature="templates",
		product="WA",
		label="WhatsApp Templates",
		count_doctype="WhatsApp Templates",
		period="total",
		# Edits of existing templates check the feature gate but
		# don't re-count (the row already exists, doesn't increment total).
		skip_if=lambda doc: bool(getattr(doc, "name", None) and not doc.is_new()),
		on_methods=("before_insert", "before_save"),
	),
	"WhatsApp Flow": Gate(
		feature="flows",
		product="WA",
		label="WhatsApp Flows",
		count_doctype="WhatsApp Flow",
		period="total",
	),
	"WhatsApp Call": Gate(
		feature="calling",
		product="WA",
		label="WhatsApp Calling",
		count_doctype="WhatsApp Call",
		period="month",
		filters={"direction": CallDirection.OUTBOUND},
		skip_if=lambda doc: getattr(doc, "direction", "") == CallDirection.INBOUND,
	),
}
