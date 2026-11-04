"""
WhatsApp Flow JSON compiler — pure functions, no Frappe Document, no HTTP.

Extracted from the 960-line `whatsapp_flow.py` controller (the audit's
single largest fat-controller finding — see WHATSAPP_REFACTOR_PLAN.md §4,
§6, and the architecture audit §13/§9). Takes plain screen/field rows
(dicts or Frappe child-table rows — both support `.get`/attribute access)
and returns a Meta Flow JSON dict. No DB access, no doctype dependency —
callable from a unit test, a preview endpoint, or the doctype's
`before_save` hook with equal ease.

Generates a *client-only* flow (no endpoint required) — data is
collected and returned via the `nfm_reply` webhook when the flow
completes, rather than a server round-trip per screen.
"""

from __future__ import annotations

import json

_DISPLAY_FIELD_TYPES = (
	"TextHeading",
	"TextSubheading",
	"TextBody",
	"TextCaption",
	"Image",
	"EmbeddedLink",
	"Footer",
)


def compile_flow(screens, fields, data_api_version: str | None = None) -> dict:
	"""Compile WhatsApp Flow JSON from screen/field rows.

	Args:
	    screens: iterable of rows with screen_id, screen_title, terminal,
	             refresh_on_back.
	    fields:  iterable of rows with screen, field_name, field_type,
	             label, required, enabled, helper_text, init_value,
	             min_chars, max_chars, error_message, options.
	    data_api_version: Meta Flow JSON schema version (default "6.0").

	Returns:
	    dict ready for `json.dumps()` and upload as `flow.json`.
	"""
	flow = {
		"version": data_api_version or "6.0",
		"screens": [],
	}

	screen_incoming_data = _build_screen_data_map(screens, fields)

	for screen in screens:
		screen_data = _build_screen(screen, screens, fields, screen_incoming_data.get(screen.screen_id, {}))
		flow["screens"].append(screen_data)

	# Note: we intentionally do NOT include 'routing_model' or a server
	# 'data_api_version' — this keeps the flow client-only (no endpoint).
	return flow


def validate_screens(screens, fields=None) -> list[str]:
	"""Return a list of validation error messages (empty list = valid).

	Pure validation logic — the doctype validator calls this and raises
	via `frappe.throw` for each message; this function itself never
	raises so it stays testable without a Frappe request context.
	"""
	errors = []
	if not screens:
		errors.append("At least one screen is required")
		return errors

	screen_ids = []
	terminal_count = 0
	for screen in screens:
		if screen.screen_id in screen_ids:
			errors.append(f"Duplicate screen ID: {screen.screen_id}")
		screen_ids.append(screen.screen_id)
		if screen.terminal:
			terminal_count += 1

	if terminal_count == 0:
		errors.append("At least one screen must be marked as terminal")

	# Meta requires a non-empty `data-source` on Dropdown/RadioButtonsGroup/
	# CheckboxGroup — an empty one isn't rejected locally, it's rejected by
	# Meta's asset-upload validation with no field-level context, so this
	# catches it up front with a message that names the actual field.
	for field in fields or []:
		if not field.enabled:
			continue
		if field.field_type in ("Dropdown", "RadioButtonsGroup", "CheckboxGroup"):
			if not _parse_options(field.options):
				errors.append(
					f"Field '{field.field_name}' on screen '{field.screen}' is a "
					f"{field.field_type} and requires at least one option."
				)

	return errors


# ── Internal compiler steps ─────────────────────────────────────────────


def _build_screen_data_map(screens, fields) -> dict:
	"""Map of fields passed to each screen from previous screens.

	Returns:
	    dict: {screen_id: {field_name: {"type": "string", "__example__": ""}}}
	"""
	screen_data_map = {}
	accumulated_fields = {}

	for screen in screens:
		if accumulated_fields:
			screen_data_map[screen.screen_id] = accumulated_fields.copy()

		for field in fields:
			if field.screen != screen.screen_id or not field.enabled:
				continue
			if field.field_type not in _DISPLAY_FIELD_TYPES:
				accumulated_fields[field.field_name] = {"type": "string", "__example__": ""}

	return screen_data_map


def _build_screen(screen, all_screens, fields, incoming_data: dict | None = None) -> dict:
	"""Build a single screen definition."""
	screen_data = {
		"id": screen.screen_id,
		"title": screen.screen_title,
		"data": incoming_data or {},
		"layout": {"type": "SingleColumnLayout", "children": []},
	}

	if screen.terminal:
		screen_data["terminal"] = True
		screen_data["success"] = True

	if screen.refresh_on_back:
		screen_data["refresh_on_back"] = True

	screen_data["layout"]["children"] = _build_screen_fields(screen, all_screens, fields)
	return screen_data


def _build_screen_fields(screen, all_screens, fields) -> list[dict]:
	"""Build field components for a screen."""
	children = []
	has_footer = False

	for field in fields:
		if field.screen != screen.screen_id or not field.enabled:
			continue
		component = _build_field_component(field, screen, all_screens, fields)
		if component:
			children.append(component)
			if field.field_type == "Footer":
				has_footer = True

	if not has_footer:
		footer_action = _build_footer_action(screen, all_screens, fields)
		children.append(
			{
				"type": "Footer",
				"label": "Continue" if not screen.terminal else "Complete",
				"on-click-action": footer_action,
			}
		)

	return children


def _build_field_component(field, screen, all_screens, fields) -> dict | None:
	"""Build a single field component."""
	field_type = field.field_type

	if field_type in ("TextHeading", "TextSubheading", "TextBody", "TextCaption"):
		return {"type": field_type, "text": field.label or ""}

	if field_type == "Image":
		component = {"type": "Image", "src": field.init_value or ""}
		if field.label:
			component["alt-text"] = field.label
		return component

	if field_type == "EmbeddedLink":
		return {
			"type": "EmbeddedLink",
			"text": field.label or "Link",
			"on-click-action": {
				"name": "navigate",
				"next": {"type": "screen", "name": field.init_value or ""},
			},
		}

	if field_type == "Footer":
		return {
			"type": "Footer",
			"label": field.label or "Submit",
			"on-click-action": _build_footer_action(screen, all_screens, fields),
		}

	component = {
		"type": field_type,
		"name": field.field_name,
		"label": field.label or field.field_name,
	}

	if field.required:
		component["required"] = True
	if field.helper_text:
		component["helper-text"] = field.helper_text
	if field.init_value:
		component["init-value"] = field.init_value

	if field_type in ("TextInput", "TextArea"):
		if field.min_chars:
			component["min-chars"] = field.min_chars
		if field.max_chars:
			component["max-chars"] = field.max_chars
		if field.error_message:
			component["error-message"] = field.error_message

	if field_type in ("Dropdown", "RadioButtonsGroup", "CheckboxGroup"):
		options = _parse_options(field.options)
		if options:
			component["data-source"] = options

	if field_type == "OptIn":
		component["label"] = field.label or "I agree"
		if field.required:
			component["required"] = True

	return component


def _build_footer_action(screen, all_screens, fields) -> dict:
	"""Build the action for a footer button."""
	if screen.terminal:
		return {"name": "complete", "payload": _build_payload(screen, all_screens, fields)}

	next_screen = _get_next_screen(screen, all_screens)
	if next_screen:
		return {
			"name": "navigate",
			"next": {"type": "screen", "name": next_screen.screen_id},
			"payload": _build_payload(screen, all_screens, fields),
		}
	return {"name": "complete", "payload": _build_payload(screen, all_screens, fields)}


def _build_payload(screen, all_screens, fields) -> dict:
	"""Build payload with all field values up to and including this screen."""
	payload = {}

	for s in all_screens:
		is_current = s.screen_id == screen.screen_id
		for field in fields:
			if field.screen != s.screen_id or not field.enabled:
				continue
			if field.field_type in _DISPLAY_FIELD_TYPES:
				continue
			if is_current:
				payload[field.field_name] = "${form." + field.field_name + "}"
			else:
				payload[field.field_name] = "${data." + field.field_name + "}"
		if is_current:
			break

	return payload


def _get_next_screen(current_screen, all_screens):
	"""Get the next screen in sequence."""
	found_current = False
	for screen in all_screens:
		if found_current:
			return screen
		if screen.screen_id == current_screen.screen_id:
			found_current = True
	return None


def _parse_options(options_json) -> list:
	"""Parse options JSON string to list."""
	if not options_json:
		return []
	try:
		options = json.loads(options_json)
		return options if isinstance(options, list) else []
	except json.JSONDecodeError:
		return []


def parse_flow_json_to_rows(flow_json: dict) -> tuple[list[dict], list[dict]]:
	"""Reverse of `compile_flow` — parse a Meta Flow JSON dict (e.g. fetched
	from an existing remote flow) into (screen_rows, field_rows) suitable
	for `doc.append("screens", row)` / `doc.append("fields", row)`.
	"""
	screen_rows = []
	field_rows = []

	for screen_data in flow_json.get("screens", []):
		screen_rows.append(
			{
				"screen_id": screen_data.get("id"),
				"screen_title": screen_data.get("title", ""),
				"terminal": 1 if screen_data.get("terminal") else 0,
				"refresh_on_back": 1 if screen_data.get("refresh_on_back") else 0,
			}
		)

		layout = screen_data.get("layout", {})
		for child in layout.get("children", []):
			field_type = child.get("type")
			if not field_type:
				continue

			field_data = {
				"screen": screen_data.get("id"),
				"field_type": field_type,
				"field_name": child.get("name", field_type.lower()),
				"label": child.get("label") or child.get("text", ""),
				"required": 1 if child.get("required") else 0,
				"enabled": 1,
				"helper_text": child.get("helper-text", ""),
				"init_value": child.get("init-value", ""),
				"min_chars": child.get("min-chars"),
				"max_chars": child.get("max-chars"),
				"error_message": child.get("error-message", ""),
			}

			if field_type in ("Dropdown", "RadioButtonsGroup", "CheckboxGroup"):
				data_source = child.get("data-source", [])
				if data_source:
					field_data["options"] = json.dumps(data_source)

			field_rows.append(field_data)

	return screen_rows, field_rows
