"""
WhatsApp Templates validators — pure functions, no DB writes, no HTTP.

Given template data, raise `frappe.ValidationError` (via `frappe.throw`)
or return cleanly. Unit-testable without instantiating a Document.
"""

from __future__ import annotations

import json
import re

import frappe
from frappe import _

from msuite_whatsapp.constants import (
	WHATSAPP_COUPON_CODE_MAX,
	WHATSAPP_LTO_CONFIG_KEY,
	WHATSAPP_LTO_HEADER_FORMATS,
	WHATSAPP_LTO_TEXT_MAX,
	WHATSAPP_TEMPLATE_BUTTONS_MAX,
)
from msuite_whatsapp.services.domain import ParameterFormat
from msuite_whatsapp.queries import template_repository


def clean_template_name(name: str) -> str:
	"""Lowercase, underscore-only template name, matching Meta's naming rules."""
	if not name:
		return ""
	name = name.lower()
	name = re.sub(r"[\s-]", "_", name)
	name = re.sub(r"[^a-z0-9_]", "", name)
	name = re.sub(r"_+", "_", name)
	return name.strip("_")


def validate_template_name(name: str) -> str:
	"""Clean and validate the template name, throwing if empty after cleaning."""
	if not name:
		frappe.throw(_("Template Name is required."))
	cleaned = clean_template_name(name)
	if not cleaned:
		frappe.throw(
			_(
				"Template Name is invalid or empty after formatting. It must contain "
				"only lowercase letters, numbers, and underscores."
			)
		)
	return cleaned


def validate_unique_name_per_language(template_name: str, language: str, exclude_name: str | None) -> None:
	"""Template names must be unique per language, but the same name may
	recur across languages since Meta templates are namespaced that way."""
	if not (template_name and language):
		return
	if template_repository.exists_for_language(template_name, language, exclude_name):
		frappe.throw(
			_("A template named {0} already exists for language {1}.").format(
				frappe.bold(template_name), frappe.bold(language)
			)
		)


def validate_media_sample(header_type: str, media_sample: str | None) -> None:
	if header_type not in ("IMAGE", "VIDEO", "DOCUMENT") or not media_sample:
		return
	ext = media_sample.lower().split(".")[-1]
	if header_type == "IMAGE" and ext not in ("jpg", "jpeg", "png", "webp"):
		frappe.throw(_("Image header only accepts jpg, png, jpeg, or webp format."))
	elif header_type == "VIDEO" and ext not in ("mp4", "mov"):
		frappe.throw(_("Video header only accepts mp4 or mov format."))
	elif header_type == "DOCUMENT" and ext != "pdf":
		# Meta's template-sample upload only accepts application/pdf —
		# accepting doc/docx here just deferred the failure to push time.
		frappe.throw(_("Document header only accepts pdf format."))


def validate_carousel_cards(is_carousel: bool, carousel_cards) -> None:
	"""Validate a Product- or Media-Card Carousel template's cards.

	Meta rejects the whole template unless every card has the same components
	(error_subcode 2388212)."""
	if not is_carousel:
		return
	cards = carousel_cards or []

	is_media = any(c.header_format in ("IMAGE", "VIDEO") for c in cards)
	if is_media:
		_validate_media_carousel_cards(cards)
		return

	# Product Card Carousel — exactly 2 cards, same single button type.
	if len(cards) != 2:
		frappe.throw(_("A Product Carousel template must define exactly 2 cards."))
	if len({card.button_type for card in cards}) > 1:
		frappe.throw(
			_(
				"All Product Carousel cards must use the same button type. "
				"Meta doesn't support mixing SPM and URL buttons across cards."
			)
		)
	for card in cards:
		if card.button_type == "URL" and len(card.website_url or "") > 2000:
			frappe.throw(_("Carousel card Website URL cannot exceed 2000 characters."))


def _validate_media_carousel_cards(cards) -> None:
	"""Media Card Carousel: 2-10 cards, each with an image/video, same
	components across every card (button combo + card-body presence)."""
	if not (2 <= len(cards) <= 10):
		frappe.throw(_("A Media Card Carousel template must define 2 to 10 cards."))

	button_combos = set()
	body_flags = set()
	for card in cards:
		if card.header_format not in ("IMAGE", "VIDEO"):
			frappe.throw(_("Every Media Carousel card must use an IMAGE or VIDEO header."))
		if not card.media_sample:
			frappe.throw(_("Every Media Carousel card needs a header image or video."))
		if card.card_body and len(card.card_body) > 160:
			frappe.throw(_("Carousel card body text cannot exceed 160 characters."))
		if card.button_type == "URL" and len(card.website_url or "") > 2000:
			frappe.throw(_("Carousel card Website URL cannot exceed 2000 characters."))
		# Meta requires identical components on every card.
		button_combos.add((card.button_type or "", card.get("button2_type") or ""))
		body_flags.add(bool(card.card_body))

	if len(button_combos) > 1:
		frappe.throw(_("All Media Carousel cards must have the same button combination."))
	if len(body_flags) > 1:
		frappe.throw(_("If any Media Carousel card has body text, all cards must have body text."))


def validate_catalog_template(template_type: str | None, category: str | None) -> None:
	"""Catalog templates must be MARKETING — Meta rejects any other category."""
	if template_type == "CATALOGUE" and category != "MARKETING":
		frappe.throw(_("Catalog templates must use the MARKETING category."))


def validate_commerce_template(
	template_type: str | None, header_type: str | None, category: str | None, body: str | None
) -> None:
	"""Single-Product (PRODUCT header) and Multi-Product (MPM) templates are
	MARKETING-only, and an SPM body is capped at 160 chars — Meta rejects
	otherwise."""
	is_spm = header_type == "PRODUCT"
	is_mpm = template_type == "MPM"
	if (is_spm or is_mpm) and category != "MARKETING":
		frappe.throw(_("Single-Product and Multi-Product templates must use the MARKETING category."))
	if is_spm and len((body or "").strip()) > 160:
		frappe.throw(_("Single-Product Message body cannot exceed 160 characters."))


def parse_limited_time_offer(button_configuration) -> dict | None:
	"""Return the raw limited-time-offer dict stored in `button_configuration`
	(JSON text or dict), or None when absent/unparseable. Never raises."""
	if isinstance(button_configuration, str):
		try:
			button_configuration = json.loads(button_configuration) if button_configuration.strip() else None
		except ValueError:
			return None
	if not isinstance(button_configuration, dict):
		return None
	lto = button_configuration.get(WHATSAPP_LTO_CONFIG_KEY)
	return lto if isinstance(lto, dict) else None


def get_send_requirements(template) -> dict:
	"""Return what a send of `template` (doc or dict) must/may supply at send time.

	Keys: `needs_expiry` (LTO with has_expiration), `needs_coupon` (has a Copy
	Offer Code button; optional when `coupon_prefill` is set), `coupon_prefill`
	(stored `offer_code` or None), `coupon_max`, `lto_text`, `lto_text_max`,
	`supports_tap_target` (has a Visit Website button; Meta opens the first URL
	button). Pure: no DB access, never raises on malformed `button_configuration`.
	"""
	lto = parse_limited_time_offer(template.get("button_configuration"))
	button_types = {b.get("button_type") for b in (template.get("buttons") or [])}
	lto_text = lto.get("text") if lto else None
	return {
		"needs_expiry": bool(lto and lto.get("has_expiration")),
		"needs_coupon": "Copy Offer Code" in button_types,
		"coupon_prefill": str(template.get("offer_code") or "").strip() or None,
		"coupon_max": WHATSAPP_COUPON_CODE_MAX,
		"lto_text": lto_text if isinstance(lto_text, str) and lto_text.strip() else None,
		"lto_text_max": WHATSAPP_LTO_TEXT_MAX,
		"supports_tap_target": "Visit Website" in button_types,
	}


def validate_limited_time_offer(button_configuration, category, header_type, footer) -> dict | None:
	"""Validate a Limited-Time-Offer template config and return it normalised
	(`{"text", "has_expiration"}`), or None when the template has none.

	Meta rules (limited-time-offer-templates doc): MARKETING category only,
	IMAGE/VIDEO header, no footer, `text` <= 16 chars, `has_expiration` boolean.
	"""
	if isinstance(button_configuration, str) and button_configuration.strip():
		try:
			parsed = json.loads(button_configuration)
		except ValueError:
			frappe.throw(_("Button Configuration must be valid JSON."))
		if not isinstance(parsed, dict):
			frappe.throw(_("Button Configuration must be a JSON object."))
	lto = parse_limited_time_offer(button_configuration)
	if not lto:
		return None

	text = lto.get("text")
	if not isinstance(text, str) or not text.strip():
		frappe.throw(_("Limited-time offer text is required."))
	text = text.strip()
	if len(text) > WHATSAPP_LTO_TEXT_MAX:
		frappe.throw(_("Limited-time offer text cannot exceed {0} characters.").format(WHATSAPP_LTO_TEXT_MAX))
	has_expiration = lto.get("has_expiration", False)
	if not isinstance(has_expiration, bool):
		frappe.throw(_("Limited-time offer 'has_expiration' must be true or false."))
	if category != "MARKETING":
		frappe.throw(_("Limited-time offer templates must use the MARKETING category."))
	if header_type not in WHATSAPP_LTO_HEADER_FORMATS:
		frappe.throw(_("Limited-time offer templates require an IMAGE or VIDEO header."))
	if footer:
		frappe.throw(_("Limited-time offer templates do not support a footer."))
	return {"text": text, "has_expiration": has_expiration}


def validate_buttons(buttons, category: str | None, offer_code: str | None) -> None:
	"""Validate button count/type rules against Meta's WhatsApp Business Management API constraints.

	Constraints:
	- Max 10 buttons total across all types.
	- Max 2 Visit Website (URL) buttons.
	- Max 1 Call Phone Number (PHONE_NUMBER) button.
	- Max 1 Call on WhatsApp (VOICE_CALL) button.
	- Max 1 Flow (FLOW) button.
	- Max 1 Copy Offer Code / OTP button.
	- Quick Reply (QUICK_REPLY) buttons up to 10.
	- Button labels must be unique across all buttons.
	- Mixing different button types (e.g. Website, Phone, Flow, Quick Reply) is fully supported by Meta.
	"""
	if not buttons:
		return

	if len(buttons) > WHATSAPP_TEMPLATE_BUTTONS_MAX:
		frappe.throw(
			_("Maximum of {0} buttons total is allowed.").format(WHATSAPP_TEMPLATE_BUTTONS_MAX)
		)

	num_qr = num_url = num_phone = num_voice = num_flow = num_otp = 0
	labels = set()

	for btn in buttons:
		btype = btn.button_type
		label = (btn.button_label or "").strip()
		if not label:
			frappe.throw(_("Button text is required for all buttons."))
		if label.lower() in labels:
			frappe.throw(_("You cannot enter the same text for multiple buttons: '{0}'").format(label))
		labels.add(label.lower())

		if btype == "Quick Reply":
			num_qr += 1
			if len(label) > 25:
				frappe.throw(_("Quick Reply button text cannot exceed 25 characters."))
		elif btype == "Visit Website":
			num_url += 1
			if len(label) > 40:
				frappe.throw(_("Visit Website button text cannot exceed 40 characters."))
			if not btn.website_url:
				frappe.throw(_("Website URL is required for Visit Website buttons."))
		elif btype == "Call Phone":
			num_phone += 1
			if len(label) > 40:
				frappe.throw(_("Call Phone button text cannot exceed 40 characters."))
			if not btn.phone_number:
				frappe.throw(_("Phone Number is required for Call Phone Number buttons."))
		elif btype == "Voice Call":
			num_voice += 1
			if len(label) > 40:
				frappe.throw(_("Call on WhatsApp button text cannot exceed 40 characters."))
		elif btype == "Flow":
			num_flow += 1
			if len(label) > 40:
				frappe.throw(_("Flow button text cannot exceed 40 characters."))
		elif btype in ("OTP", "Copy Offer Code"):
			num_otp += 1
			if len(label) > 40:
				frappe.throw(_("Offer Code button text cannot exceed 40 characters."))
			otp_type = btn.get("otp_type") or "COPY_CODE"
			if otp_type == "COPY_CODE" and category != "AUTHENTICATION":
				code = offer_code or btn.get("example_url")
				if code and len(code) > WHATSAPP_COUPON_CODE_MAX:
					frappe.throw(
						_("Offer/Coupon Code cannot exceed {0} characters.").format(WHATSAPP_COUPON_CODE_MAX)
					)

	if num_url > 2:
		frappe.throw(_("Maximum of 2 Visit Website (URL) buttons is allowed."))
	if num_phone > 1:
		frappe.throw(_("Maximum of 1 Call Phone Number button is allowed."))
	if num_voice > 1:
		frappe.throw(_("Maximum of 1 Call on WhatsApp (Voice Call) button is allowed."))
	if num_flow > 1:
		frappe.throw(_("Maximum of 1 Flow button is allowed."))
	if num_otp > 1:
		frappe.throw(_("Maximum of 1 Copy Offer Code button is allowed."))


def validate_variables_before_push(
	template_body: str, sample_values: str | None, parameter_format: str
) -> None:
	"""Validate that sample values are present and correctly shaped for every
	{{variable}} placeholder before pushing to Meta."""
	variables = re.findall(r"\{\{(\w+)\}\}", template_body or "")
	if not variables:
		return

	if not sample_values:
		frappe.throw(
			_("Sample Values are required when template body has variables ({0}).").format(
				", ".join(f"{{{{{v}}}}}" for v in variables)
			)
		)

	if parameter_format == ParameterFormat.NAMED:
		parsed = {}
		for pair in sample_values.split(","):
			pair = pair.strip()
			if "=" not in pair:
				frappe.throw(
					_("For Named variables, Sample Values must be in key=value format. Example: {0}").format(
						",".join(f"{v}=sample_value" for v in variables)
					)
				)
			key, val = pair.split("=", 1)
			parsed[key.strip()] = val.strip()

		missing = [v for v in variables if v not in parsed]
		if missing:
			frappe.throw(
				_("Missing sample values for: {0}. Expected format: {1}").format(
					", ".join(f"{{{{{v}}}}}" for v in missing),
					",".join(f"{v}=example" for v in variables),
				)
			)
	else:
		samples = [s.strip() for s in sample_values.split(",") if s.strip()]
		unique_vars = set(variables)
		if len(samples) != len(unique_vars):
			frappe.throw(
				_(
					"For Positional variables, the number of sample values ({0}) must "
					"match the number of placeholders ({1}). Example: {2}"
				).format(
					len(samples),
					len(unique_vars),
					", ".join(f"value{i + 1}" for i in range(len(unique_vars))),
				)
			)

	# Meta policy: parameter-to-word ratio limit (error subcode 2388293)
	static_text = re.sub(r"\{\{[^}]+\}\}", " ", template_body or "")
	words = [w for w in re.findall(r"\b\w+\b", static_text) if w]
	if len(variables) > 1 and len(words) < len(variables) * 2.5:
		frappe.throw(
			_(
				"This template has too many variables for its message length ({0} variables for {1} words). "
				"Meta requires adding more text to the message body or reducing the number of variables."
			).format(len(variables), len(words)),
			title=_("Variable Ratio Exceeded"),
		)

