"""
WhatsApp Flow API — Vue SPA-facing CRUD.

Relocated from `api/v1/whatsapp/crud.py` (see WHATSAPP_REFACTOR_PLAN.md §9).
The dotted path `msuite_whatsapp.api.v1.app.crud.*` is preserved via
a re-export shim in that module since the SPA calls it by that exact path.
"""

from __future__ import annotations

import json
import re

import frappe
from frappe import _

from msuite_core.constants import WHATSAPP_FLOW_CTA_MAX
from msuite_core.services.permissions.checks import (
	check_create,
	check_delete,
	check_read,
	check_write,
	safe_doc_dict,
)

FLOW_DOCTYPE = "WhatsApp Flow"
_SAVABLE_FIELDS = ("flow_name", "whatsapp_account", "category", "description", "flow_cta", "data_api_version")

# Meta's allowed field types — kept in sync with the WhatsApp Flow Field
# doctype's Select options so the compiler never receives an unknown type.
_VALID_FIELD_TYPES = {
	"TextInput",
	"TextArea",
	"DatePicker",
	"RadioButtonsGroup",
	"CheckboxGroup",
	"Dropdown",
	"OptIn",
	"EmbeddedLink",
	"Image",
	"TextHeading",
	"TextSubheading",
	"TextBody",
	"TextCaption",
	"Footer",
}

# Field types that are purely presentational — they never collect data,
# so `required`, `helper_text`, `error_message` etc. don't apply.
_DISPLAY_FIELD_TYPES = {
	"TextHeading",
	"TextSubheading",
	"TextBody",
	"TextCaption",
	"Image",
	"EmbeddedLink",
	"Footer",
}

# Field types that need a non-empty `options` (data-source) array.
_CHOICE_FIELD_TYPES = {"Dropdown", "RadioButtonsGroup", "CheckboxGroup"}

# Meta limits.
_MAX_SCREENS = 10
_MAX_FIELDS_PER_SCREEN = 30
_MAX_SCREEN_TITLE_LENGTH = 80

# screen_id must be uppercase alphanumeric + underscores (Meta convention).
_SCREEN_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")


@frappe.whitelist()
def get_flow_metrics() -> dict:
	check_read(FLOW_DOCTYPE)

	total = frappe.db.count(FLOW_DOCTYPE)
	published = frappe.db.count(FLOW_DOCTYPE, {"status": "Published"})
	draft = frappe.db.count(FLOW_DOCTYPE, {"status": "Draft"})
	deprecated = frappe.db.count(FLOW_DOCTYPE, {"status": "Deprecated"})

	return {
		"total": total,
		"published": published,
		"draft": draft,
		"deprecated": deprecated,
	}


@frappe.whitelist()
def list_flows(filters: str = "[]", search: str = "", limit: int = 100) -> list:
	check_read(FLOW_DOCTYPE)

	parsed_filters = json.loads(filters or "[]")
	if search and search.strip():
		parsed_filters.append(["flow_name", "like", f"%{search.strip()}%"])

	return frappe.get_all(
		FLOW_DOCTYPE,
		fields=[
			"name",
			"flow_name",
			"status",
			"category",
			"description",
			"whatsapp_account",
			"flow_id",
			"owner",
			"modified",
		],
		filters=parsed_filters,
		order_by="modified desc",
		limit=limit,
	)


@frappe.whitelist()
def delete_flow(name: str):
	check_delete(FLOW_DOCTYPE, name)
	frappe.delete_doc(FLOW_DOCTYPE, name)
	frappe.db.commit()
	return {"status": "success"}


@frappe.whitelist()
def bulk_delete_flows(names: str | list) -> dict:
	"""Batch delete multiple WhatsApp flows."""
	name_list = json.loads(names) if isinstance(names, str) else (names or [])
	deleted, failed = [], []
	for name in name_list:
		if not frappe.has_permission(FLOW_DOCTYPE, "delete", doc=name):
			failed.append({"name": name, "reason": "No delete permission"})
			continue
		try:
			frappe.delete_doc(FLOW_DOCTYPE, name, force=True)
			deleted.append(name)
		except Exception as e:
			frappe.log_error(title="bulk_delete_flows", message=str(e))
			failed.append({"name": name, "reason": str(e)})
	frappe.db.commit()
	return {"deleted": deleted, "failed": failed}


@frappe.whitelist()
def get_flow(name: str) -> dict:
	check_read(FLOW_DOCTYPE, name)
	return frappe.get_doc(FLOW_DOCTYPE, name).as_dict()


@frappe.whitelist()
def save_flow(doc: str) -> dict:
	"""Persist the Flow Builder's metadata + screens + fields.

	Accepts the full flow configuration from the SPA: metadata fields
	(flow_name, whatsapp_account, category, etc.) plus optional `screens`
	and `fields` arrays. When screens/fields are provided they replace
	all existing child rows atomically — this matches how the compiler
	re-generates flow_json from the full set on `before_save`.

	If no screens are provided (legacy / first-time create), the default
	two-screen structure is seeded so the doctype validates.

	Published flows reject screen/field modifications — the user must
	deprecate first or create a new flow.
	"""
	data = json.loads(doc or "{}")
	name = (data.get("name") or "").strip()

	# ── Validate flow_cta length (WhatsApp limit) ────────────
	flow_cta = data.get("flow_cta", "")
	if flow_cta and len(flow_cta) > WHATSAPP_FLOW_CTA_MAX:
		frappe.throw(_("Call to Action must be at most {0} characters").format(WHATSAPP_FLOW_CTA_MAX))

	has_screens_payload = "screens" in data

	if name:
		# ── Update existing flow ─────────────────────────────
		check_write(FLOW_DOCTYPE, name)
		flow = frappe.get_doc(FLOW_DOCTYPE, name)

		for field in _SAVABLE_FIELDS:
			if field in data:
				flow.set(field, data[field])

		if has_screens_payload:
			if flow.status == "Published":
				frappe.throw(
					_(
						"Cannot modify screens/fields of a Published flow. "
						"Deprecate it first or create a new flow."
					)
				)
			_apply_screens_and_fields(
				flow,
				data.get("screens", []),
				data.get("fields", []),
			)

		flow.save()
	else:
		# ── Create new flow ──────────────────────────────────
		check_create(FLOW_DOCTYPE)
		flow = frappe.get_doc(
			safe_doc_dict(
				{k: v for k, v in data.items() if k in _SAVABLE_FIELDS},
				FLOW_DOCTYPE,
			)
		)

		if has_screens_payload:
			_apply_screens_and_fields(
				flow,
				data.get("screens", []),
				data.get("fields", []),
			)
		elif not flow.get("screens"):
			_seed_default_screens(flow)

		flow.insert()

	frappe.db.commit()
	return flow.as_dict()


# ── Screen & field validation / application ──────────────────────────────


def _validate_screen_data(screens: list[dict]) -> None:
	"""Validate the screens array from the SPA payload.

	Raises `frappe.throw` on the first error found.
	"""
	if not screens:
		frappe.throw(_("At least one screen is required"))

	if len(screens) > _MAX_SCREENS:
		frappe.throw(_("Maximum {0} screens allowed per flow").format(_MAX_SCREENS))

	seen_ids: set[str] = set()
	terminal_count = 0

	for idx, screen in enumerate(screens, 1):
		sid = (screen.get("screen_id") or "").strip()
		title = (screen.get("screen_title") or "").strip()

		if not sid:
			frappe.throw(_("Screen {0}: Screen ID is required").format(idx))

		if not _SCREEN_ID_RE.match(sid):
			frappe.throw(
				_(
					"Screen {0}: Screen ID '{1}' must be uppercase alphanumeric "
					"with underscores (e.g. CUSTOMER_DETAILS)"
				).format(idx, sid)
			)

		if sid in seen_ids:
			frappe.throw(_("Screen {0}: Duplicate Screen ID '{1}'").format(idx, sid))
		seen_ids.add(sid)

		if not title:
			frappe.throw(_("Screen {0}: Screen Title is required").format(idx))

		if len(title) > _MAX_SCREEN_TITLE_LENGTH:
			frappe.throw(
				_("Screen {0}: Title must be at most {1} characters").format(idx, _MAX_SCREEN_TITLE_LENGTH)
			)

		if screen.get("terminal"):
			terminal_count += 1

	if terminal_count == 0:
		frappe.throw(_("At least one screen must be marked as the terminal (final) screen"))

	return seen_ids


def _validate_field_data(fields: list[dict], screen_ids: set[str]) -> None:
	"""Validate the fields array from the SPA payload.

	Raises `frappe.throw` on the first error found.
	"""
	# Track field names per screen to enforce uniqueness.
	screen_field_counts: dict[str, int] = {}
	screen_field_names: dict[str, set[str]] = {}

	for idx, field in enumerate(fields, 1):
		screen = (field.get("screen") or "").strip()
		field_name = (field.get("field_name") or "").strip()
		field_type = (field.get("field_type") or "").strip()

		if not screen:
			frappe.throw(_("Field {0}: Screen ID is required").format(idx))

		if screen not in screen_ids:
			frappe.throw(_("Field {0}: Screen ID '{1}' does not match any screen").format(idx, screen))

		if not field_name:
			frappe.throw(_("Field {0}: Field Name is required").format(idx))

		if not field_type:
			frappe.throw(_("Field {0}: Field Type is required").format(idx))

		if field_type not in _VALID_FIELD_TYPES:
			frappe.throw(_("Field {0}: Invalid field type '{1}'").format(idx, field_type))

		# Uniqueness within a screen.
		if screen not in screen_field_names:
			screen_field_names[screen] = set()
			screen_field_counts[screen] = 0

		if field_name in screen_field_names[screen]:
			frappe.throw(
				_("Field {0}: Duplicate field name '{1}' on screen '{2}'").format(idx, field_name, screen)
			)
		screen_field_names[screen].add(field_name)
		screen_field_counts[screen] += 1

		if screen_field_counts[screen] > _MAX_FIELDS_PER_SCREEN:
			frappe.throw(
				_("Screen '{0}': Maximum {1} fields allowed per screen").format(
					screen, _MAX_FIELDS_PER_SCREEN
				)
			)

		# Input fields need a label.
		if field_type not in _DISPLAY_FIELD_TYPES:
			label = (field.get("label") or "").strip()
			if not label:
				frappe.throw(
					_("Field {0} ('{1}'): Label is required for input fields").format(idx, field_name)
				)

		# Choice fields need at least one option.
		if field_type in _CHOICE_FIELD_TYPES:
			options = field.get("options")
			if isinstance(options, str):
				try:
					options = json.loads(options)
				except (ValueError, TypeError):
					options = []
			if not options or not isinstance(options, list) or len(options) == 0:
				frappe.throw(
					_("Field {0} ('{1}'): {2} requires at least one option").format(
						idx, field_name, field_type
					)
				)
			for opt_idx, opt in enumerate(options, 1):
				if not isinstance(opt, dict):
					frappe.throw(
						_("Field {0} ('{1}'): Option {2} must be an object with 'id' and 'title'").format(
							idx, field_name, opt_idx
						)
					)
				if not opt.get("id") or not opt.get("title"):
					frappe.throw(
						_("Field {0} ('{1}'): Option {2} must have both 'id' and 'title'").format(
							idx, field_name, opt_idx
						)
					)


def _apply_screens_and_fields(
	flow_doc,
	screens: list[dict],
	fields: list[dict],
) -> None:
	"""Validate and apply screens + fields to the flow document.

	Clears existing child rows and re-appends from the validated payload.
	Options arrays are serialized to JSON strings for storage.
	"""
	screen_ids = _validate_screen_data(screens)
	_validate_field_data(fields, screen_ids)

	# Clear existing child rows.
	flow_doc.screens = []
	flow_doc.fields = []

	# Append screens.
	for screen in screens:
		flow_doc.append(
			"screens",
			{
				"screen_id": screen["screen_id"].strip(),
				"screen_title": screen["screen_title"].strip(),
				"terminal": 1 if screen.get("terminal") else 0,
				"refresh_on_back": 1 if screen.get("refresh_on_back") else 0,
				"success_message": (screen.get("success_message") or "").strip(),
			},
		)

	# Append fields.
	for field in fields:
		row = {
			"screen": field["screen"].strip(),
			"field_name": field["field_name"].strip(),
			"field_type": field["field_type"].strip(),
			"label": (field.get("label") or "").strip(),
			"required": 1 if field.get("required") else 0,
			"enabled": 1,
			"init_value": (field.get("init_value") or "").strip(),
			"helper_text": (field.get("helper_text") or "").strip(),
			"error_message": (field.get("error_message") or "").strip(),
		}

		# min_chars / max_chars — only meaningful for text fields.
		if field["field_type"] in ("TextInput", "TextArea"):
			if field.get("min_chars"):
				row["min_chars"] = int(field["min_chars"])
			if field.get("max_chars"):
				row["max_chars"] = int(field["max_chars"])

		# Serialize options array to JSON string for storage.
		if field["field_type"] in _CHOICE_FIELD_TYPES:
			options = field.get("options", [])
			if isinstance(options, list):
				row["options"] = json.dumps(options)
			elif isinstance(options, str):
				row["options"] = options  # already JSON string
			else:
				row["options"] = "[]"

		flow_doc.append("fields", row)


def _seed_default_screens(flow) -> None:
	"""Append the starter screens/fields shown on the builder canvas:
	Screen 1 collects name / email / account type, Screen 2 is the
	terminal thank-you screen."""
	flow.append(
		"screens",
		{
			"screen_id": "CUSTOMER_DETAILS",
			"screen_title": "Customer Details",
			"terminal": 0,
		},
	)
	flow.append(
		"screens",
		{
			"screen_id": "THANK_YOU",
			"screen_title": "Thank You",
			"terminal": 1,
		},
	)

	flow.append(
		"fields",
		{
			"screen": "CUSTOMER_DETAILS",
			"field_type": "TextInput",
			"field_name": "name",
			"label": "Name",
			"required": 1,
			"enabled": 1,
		},
	)
	flow.append(
		"fields",
		{
			"screen": "CUSTOMER_DETAILS",
			"field_type": "TextInput",
			"field_name": "email",
			"label": "Email",
			"enabled": 1,
		},
	)
	flow.append(
		"fields",
		{
			"screen": "CUSTOMER_DETAILS",
			"field_type": "Dropdown",
			"field_name": "account_type",
			"label": "Account Type",
			"enabled": 1,
			"options": json.dumps(
				[
					{"id": "personal", "title": "Personal"},
					{"id": "business", "title": "Business"},
				]
			),
		},
	)
	flow.append(
		"fields",
		{
			"screen": "THANK_YOU",
			"field_type": "TextHeading",
			"field_name": "thank_you_heading",
			"label": "Thank you!",
			"enabled": 1,
		},
	)
	flow.append(
		"fields",
		{
			"screen": "THANK_YOU",
			"field_type": "TextBody",
			"field_name": "thank_you_body",
			"label": "We've received your details and will be in touch soon.",
			"enabled": 1,
		},
	)


@frappe.whitelist()
def create_flow_on_whatsapp(name: str) -> dict:
	"""Create the Meta flow shell + upload the compiled flow.json.
	Thin wrapper around the doc's own `create_on_whatsapp()` — all the
	actual Meta API orchestration already lives there and in
	`services/flow_service.py`; this just exposes it to the SPA the
	same way every other module-level CRUD function in this file does.
	"""
	check_write(FLOW_DOCTYPE, name)
	flow = frappe.get_doc(FLOW_DOCTYPE, name)
	flow.create_on_whatsapp()
	frappe.db.commit()
	return flow.as_dict()


@frappe.whitelist()
def publish_flow_to_whatsapp(name: str) -> dict:
	"""Publish an already-created Meta flow. See `create_flow_on_whatsapp`."""
	check_write(FLOW_DOCTYPE, name)
	flow = frappe.get_doc(FLOW_DOCTYPE, name)
	flow.publish_flow()
	frappe.db.commit()
	return flow.as_dict()


@frappe.whitelist()
def deprecate_flow_on_whatsapp(name: str) -> dict:
	"""Deprecate a Published flow. Deprecating (not deleting) is the only
	way to retire a flow once it's live — Meta doesn't allow deleting a
	Published flow. Previously only reachable from Desk; the builder had
	no way to retire a flow once published."""
	check_write(FLOW_DOCTYPE, name)
	flow = frappe.get_doc(FLOW_DOCTYPE, name)
	flow.deprecate_flow()
	frappe.db.commit()
	return flow.as_dict()


@frappe.whitelist()
def get_flow_status_from_whatsapp(name: str) -> dict:
	"""Pull live status + validation_errors from Meta and persist status
	locally. Surfaces exactly why a flow won't publish (bad component,
	unresolved data-source, etc.) instead of a bare 'publish failed'."""
	check_write(FLOW_DOCTYPE, name)
	flow = frappe.get_doc(FLOW_DOCTYPE, name)
	data = flow.get_flow_status()
	frappe.db.commit()
	return data


@frappe.whitelist()
def sync_flow_from_whatsapp(name: str) -> dict:
	"""Pull status/category/flow_json back from Meta into the local doc —
	e.g. after editing screens directly in WhatsApp Manager, or to
	reconcile after a webhook-reported status change."""
	check_write(FLOW_DOCTYPE, name)
	flow = frappe.get_doc(FLOW_DOCTYPE, name)
	flow.sync_from_whatsapp()
	frappe.db.commit()
	return flow.as_dict()


@frappe.whitelist()
def get_flow_preview_url(name: str) -> dict:
	"""Fetch (and cache) the Meta-hosted preview link for a created flow."""
	check_read(FLOW_DOCTYPE, name)
	flow = frappe.get_doc(FLOW_DOCTYPE, name)
	url = flow.get_flow_preview()
	frappe.db.commit()
	return {"preview_url": url}


@frappe.whitelist()
def send_test_flow(name: str, phone_number: str, message: str | None = None) -> dict:
	"""Send a live test of this flow to a phone number via the inbox
	outbound pipeline — lets a user verify a flow actually renders/
	submits correctly before using it in a real broadcast/template."""
	check_write(FLOW_DOCTYPE, name)
	flow = frappe.get_doc(FLOW_DOCTYPE, name)
	flow.send_test(phone_number, message)
	return {"status": "sent"}
