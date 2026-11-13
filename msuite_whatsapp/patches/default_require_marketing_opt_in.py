"""Default WhatsApp Settings.require_marketing_opt_in to 1 on existing sites.

Frappe does not write a new Check field's default into tabSingles, and
get_single_value returns 0 for a missing row, which would switch the AUT-119
consent check off after migrate. Write 1 only when no row exists, so an admin's
explicit 0 is kept.
"""

import frappe

SETTINGS_DOCTYPE = "WhatsApp Settings"
FIELD = "require_marketing_opt_in"


def execute() -> None:
	"""Set the field to 1 when tabSingles has no row for it.

	Side Effects:
		One tabSingles write (no commit; the migrate runner commits).
	"""
	if frappe.db.sql("select value from `tabSingles` where doctype=%s and field=%s", (SETTINGS_DOCTYPE, FIELD)):
		return
	frappe.db.set_single_value(SETTINGS_DOCTYPE, FIELD, 1)
