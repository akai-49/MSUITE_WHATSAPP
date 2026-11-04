"""WhatsApp Flow validators — thin wrapper raising on the compiler's
pure validation results (see `providers.meta.flow_compiler.validate_screens`)."""

from __future__ import annotations

import frappe
from frappe import _

from msuite_whatsapp.integrations.meta import flow_compiler


def validate_screens(screens, fields=None) -> None:
	for message in flow_compiler.validate_screens(screens, fields):
		frappe.throw(_(message))
