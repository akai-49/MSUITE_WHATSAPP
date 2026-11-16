"""
WhatsApp template message — build the Meta payload for a SEND.

Distinct from `template_provider.py` which builds the components array
for template *creation* (admin pushes a template to Meta for approval).
This file fills in the variables on an approved template and emits the
body that goes to `/messages`.

Shared by every WhatsApp send path so the variable substitution / header
media / dynamic button URLs / MPM action are all built in one place.

This module replaces `whatsapp.utils.template_send`, which now
re-exports `build_template_meta` for backward compatibility.
"""

from __future__ import annotations

import json
import re

import frappe
from frappe import _

from msuite_whatsapp.constants import (
	WHATSAPP_INTERACTIVE_BODY_MAX,
	WHATSAPP_PRODUCT_CAROUSEL_MAX,
	WHATSAPP_PRODUCT_CAROUSEL_MIN,
)
from msuite_whatsapp.constants import WHATSAPP_COUPON_CODE_MAX
from msuite_whatsapp.integrations.meta import media_provider
from msuite_whatsapp.services.validators.template_validator import parse_limited_time_offer


# Purpose: assemble the full Meta `template` payload for a SEND — body vars, header media,
# carousel cards, MPM/catalog action, and dynamic buttons — for one approved template.
# WhatsApp-only: yes — every send path (Bulk, Notification, Flow, agent reply) funnels here.
def build_template_meta(
	template_name: str,
	body_param: dict | str | None = None,
	attach: str | None = None,
	product_catalog_json: dict | str | None = None,
	product: dict | str | None = None,
	carousel_products: list[dict] | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	whatsapp_account: str | None = None,
	thumbnail_product_retailer_id: str | None = None,
	limited_time_offer_expiry_ms: int | None = None,
	coupon_code: str | None = None,
	tap_target: dict | None = None,
) -> dict:
	"""Return the Meta `template` dict ready to nest under the send body.

	Args:
	    template_name: WhatsApp Templates doc name.
	    body_param:   Variable values — dict, JSON string, or None.
	                  For NAMED templates: `{"student": "Sagar"}`.
	                  For POSITIONAL: `{"1": "Sagar"}`.
	    attach:       Frappe file URL to use as the header media (overrides
	                  the template's stored sample).
	    product_catalog_json: MPM catalog action.
	    product:      For an SPM template (PRODUCT header, not a carousel),
	                  `{"product_retailer_id": ..., "catalog_id": ...}` or
	                  the equivalent JSON string.
	    carousel_products: For a Product Card Carousel template — 2 to 10
	                  `{"product_retailer_id": ..., "catalog_id": ...}` dicts,
	                  one per card, in send order.
	    reference_doctype + reference_name: Used to resolve dynamic
	                  website-URL buttons; the URL field is treated as a
	                  Frappe printf and rendered against the ref doc.
	    thumbnail_product_retailer_id: Optional retailer ID for Catalog button thumbnail.
	    limited_time_offer_expiry_ms: Offer expiry as a UNIX ms timestamp; required
	                  when the template's limited-time offer has_expiration.
	    coupon_code:  Value for a Copy Offer Code button (<= WHATSAPP_COUPON_CODE_MAX
	                  chars); defaults to the template's `offer_code`.
	    tap_target:   `{"url", "title"}` send-time CTA override for header-less /
	                  media templates (tap-target-url-title-override doc).

	Raises:
	    frappe.ValidationError: missing/invalid expiry, coupon code or tap target.

	Returns:
	    Dict: `{"name", "language": {"code"}, "components": [...]}` —
	    plus the resolved `body_parameters` list under `_resolved_parameters`
	    for the caller's convenience (audit / analytics).
	"""
	template = frappe.get_cached_doc("WhatsApp Templates", template_name)
	is_named = template.parameter_format == "NAMED"
	var_names = re.findall(r"\{\{(\w+)\}\}", template.template or "") if is_named else []

	components: list[dict] = []
	resolved: list[str] = []

	# ── Body parameters ────────────────────────────────────────────────
	parameters = _build_body_parameters(
		template=template,
		is_named=is_named,
		var_names=var_names,
		body_param=body_param,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
		resolved_out=resolved,
	)
	if parameters:
		components.append({"type": "body", "parameters": parameters})

	# ── Header media ───────────────────────────────────────────────────
	header_param = _build_header_param(template, attach, whatsapp_account, product)
	if header_param:
		components.append({"type": "header", "parameters": [header_param]})

	# ── Limited-time offer — expiry timer ──────────────────────────────
	lto_component = _build_limited_time_offer_component(template, limited_time_offer_expiry_ms)
	if lto_component:
		components.append(lto_component)

	# ── Carousel — per-card parameters ────────────────────────────────
	# Product Card Carousel gets per-card PRODUCT headers from `carousel_products`;
	# Media Card Carousel gets per-card IMAGE/VIDEO headers (+ button params)
	# from the template's own cards — its media isn't auto-filled at send time
	# (Meta #132012 "header component parameter should not be empty" otherwise).
	if template.is_carousel:
		if carousel_products:
			components.append(_build_carousel_send_component(carousel_products))
		elif any((c.header_format or "") in ("IMAGE", "VIDEO") for c in (template.carousel_cards or [])):
			components.append(_build_media_carousel_send_component(template, whatsapp_account))

	# ── MPM (Multi-Product Message) — interactive catalog ──────────────
	has_mpm = False
	if product_catalog_json:
		catalog = (
			json.loads(product_catalog_json)
			if isinstance(product_catalog_json, str)
			else product_catalog_json
		)
		components.append(
			{
				"type": "button",
				"sub_type": "mpm",
				"index": "0",
				"parameters": [{"type": "action", "action": catalog}],
			}
		)
		has_mpm = True

	# ── Buttons ───────────────────────────────────────────────────────
	components.extend(
		_build_button_components(
			template=template,
			has_mpm=has_mpm,
			reference_doctype=reference_doctype,
			reference_name=reference_name,
			thumbnail_product_retailer_id=thumbnail_product_retailer_id,
			coupon_code=coupon_code,
		)
	)

	# ── Tap-target URL/title override ──────────────────────────────────
	tap_component = _build_tap_target_component(tap_target)
	if tap_component:
		components.append(tap_component)

	meta_template = {
		"name": template.actual_name or template.template_name,
		"language": {"code": template.language_code},
		"components": components,
	}
	# Stash the resolved params for the caller; not sent to Meta — pop
	# before serialisation if you don't want it surfacing in logs.
	meta_template["_resolved_parameters"] = resolved
	return meta_template


# Purpose: send-time limited_time_offer component carrying the offer expiry.
# WhatsApp-only: yes — Meta limited-time-offer template send format.
def _build_limited_time_offer_component(template, expiry_ms) -> dict | None:
	"""Return the `limited_time_offer` send component, or None when the template
	has no offer or one without expiration. Throws on a missing/non-positive expiry."""
	lto = parse_limited_time_offer(template.get("button_configuration"))
	if not (lto and lto.get("has_expiration")):
		return None
	try:
		expiry = int(expiry_ms)
	except (TypeError, ValueError):
		expiry = 0
	if expiry <= 0:
		frappe.throw(_("A limited-time offer expiry (UNIX milliseconds) is required for this template."))
	return {
		"type": "limited_time_offer",
		"parameters": [{"type": "limited_time_offer", "limited_time_offer": {"expiration_time_ms": expiry}}],
	}


# Purpose: send-time tap_target_configuration component (custom URL + title for the template tap target).
# WhatsApp-only: yes — Meta tap-target URL/title override.
def _build_tap_target_component(tap_target) -> dict | None:
	"""Validate `{"url","title"}` (dict or its JSON string, as RPC form posts send it) and return the component, or None if not requested."""
	if not tap_target:
		return None
	if isinstance(tap_target, str):
		try:
			tap_target = json.loads(tap_target)
		except ValueError:
			pass  # falls through to the not-a-dict error below
	if not isinstance(tap_target, dict):
		frappe.throw(_("Tap target needs an http(s) URL and a title."))
	url = str(tap_target.get("url") or "").strip()
	title = str(tap_target.get("title") or "").strip()
	if not (url.lower().startswith(("https://", "http://")) and title):
		frappe.throw(_("Tap target needs an http(s) URL and a title."))
	return {
		"type": "tap_target_configuration",
		"parameters": [
			{"type": "tap_target_configuration", "tap_target_configuration": [{"url": url, "title": title}]}
		],
	}


# ── Body params ──────────────────────────────────────────────────────────


def _parse_sample_dict(sample_values: str | None, is_named: bool, var_names: list[str]) -> dict[str, str]:
	if not sample_values:
		return {}
	try:
		raw_stripped = sample_values.strip()
		if (raw_stripped.startswith("{") and raw_stripped.endswith("}")) or (raw_stripped.startswith("[") and raw_stripped.endswith("]")):
			parsed = json.loads(raw_stripped)
			if isinstance(parsed, dict):
				return {str(k): str(v) for k, v in parsed.items()}
			if isinstance(parsed, list):
				return {
					(var_names[i] if is_named and i < len(var_names) else str(i + 1)): str(v)
					for i, v in enumerate(parsed)
				}
	except Exception:
		pass

	out: dict[str, str] = {}
	parts = [p.strip() for p in sample_values.split(",") if p.strip()]
	if is_named:
		for p in parts:
			if "=" in p:
				k, v = p.split("=", 1)
				out[k.strip()] = v.strip()
			else:
				out[p] = ""
	else:
		for i, p in enumerate(parts):
			out[str(i + 1)] = p
	return out


# Purpose: resolve a template's {{variables}} into Meta's body `parameters` list.
# WhatsApp-only: yes — shapes WhatsApp template body parameters (named/positional).
def _build_body_parameters(
	template,
	is_named: bool,
	var_names: list[str],
	body_param,
	reference_doctype,
	reference_name,
	resolved_out: list[str],
) -> list[dict]:
	"""Resolve template variables into Meta's body parameters list."""
	if body_param is not None:
		body_data = json.loads(body_param) if isinstance(body_param, str) else body_param
		return _body_params_from_dict(body_data, is_named, var_names, resolved_out)

	if not template.sample_values and not template.template:
		return []

	if reference_doctype and reference_name:
		ref_doc = frappe.get_doc(reference_doctype, reference_name)
		return _body_params_from_ref(ref_doc, template, is_named, var_names, resolved_out)

	return []


# Purpose: build body parameters from an explicit dict of caller-supplied values.
# WhatsApp-only: yes — emits WhatsApp body parameter dicts.
def _safe_param_text(param) -> str:
	if isinstance(param, dict):
		return str(param.get("value") or param.get("text") or param.get("key") or "")
	return str(param) if param is not None else ""


def _body_params_from_dict(
	body_data: dict | list, is_named: bool, var_names: list[str], resolved_out: list[str]
) -> list[dict]:
	out: list[dict] = []
	if isinstance(body_data, list):
		for val in body_data:
			text = _safe_param_text(val)
			out.append({"type": "text", "text": text})
			resolved_out.append(text)
		return out

	if is_named:
		for i, var_name in enumerate(var_names):
			raw_val = body_data.get(var_name, body_data.get(str(i + 1), ""))
			value = _safe_param_text(raw_val)
			out.append({"type": "text", "text": value, "parameter_name": var_name})
			resolved_out.append(value)
	else:
		for param in body_data.values():
			text = _safe_param_text(param)
			out.append({"type": "text", "text": text})
			resolved_out.append(text)
	return out


# Purpose: build body parameters by reading fields off a reference doc (e.g. a Lead/Contact).
# WhatsApp-only: yes — emits WhatsApp body parameter dicts.
def _body_params_from_ref(
	ref_doc, template, is_named: bool, var_names: list[str], resolved_out: list[str]
) -> list[dict]:
	out: list[dict] = []
	sample_map = _parse_sample_dict(template.sample_values, is_named, var_names)

	if is_named:
		for var_name in var_names:
			val = None
			try:
				val = ref_doc.get_formatted(var_name.strip())
			except Exception:
				val = ref_doc.get(var_name.strip())
			if not val:
				val = sample_map.get(var_name, "")
			value = str(val or "")
			out.append({"type": "text", "text": value, "parameter_name": var_name})
			resolved_out.append(value)
	else:
		field_names = (
			template.field_names.split(",") if template.field_names else template.sample_values.split(",")
		) if (template.field_names or template.sample_values) else []
		for i, field_name in enumerate(field_names):
			clean_field = field_name.strip()
			val = None
			try:
				val = ref_doc.get_formatted(clean_field)
			except Exception:
				val = ref_doc.get(clean_field)
			if not val:
				val = sample_map.get(str(i + 1), clean_field if "=" not in clean_field else "")
			value = str(val or "")
			out.append({"type": "text", "text": value})
			resolved_out.append(value)
	return out


# ── Header media ─────────────────────────────────────────────────────────


# Purpose: build the header parameter for a send — PRODUCT header, or uploaded IMAGE/VIDEO/DOCUMENT media.
# WhatsApp-only: yes — uploads to Meta and returns a WhatsApp header parameter.
def _build_header_param(template, attach, whatsapp_account, product: dict | str | None = None) -> dict | None:
	"""Upload media + return the header parameter, or None if no media header."""
	if template.header_type == "PRODUCT":
		if not product:
			return None
		product = json.loads(product) if isinstance(product, str) else product
		return {"type": "product", "product": product}
	if template.header_type not in ("IMAGE", "VIDEO", "DOCUMENT"):
		return None
	media_file = attach or template.sample
	if not media_file:
		return None
	return media_provider.get_media_header_param(media_file, template.header_type, whatsapp_account)


# Purpose: build the send-time carousel component for a Product Card Carousel (one PRODUCT-header card per product).
# WhatsApp-only: yes — WhatsApp carousel template send format.
def _build_carousel_send_component(carousel_products: list[dict]) -> dict:
	"""Build the send-time `carousel` component: one card per product, each
	carrying its own PRODUCT header parameter. 2-10 cards (Meta's rule —
	same range as the free-form Interactive Product Carousel)."""
	if not (2 <= len(carousel_products) <= 10):
		frappe.throw(f"Carousel template needs 2-10 products, got {len(carousel_products)}.")
	return {
		"type": "carousel",
		"cards": [
			{
				"card_index": i,
				"components": [{"type": "header", "parameters": [{"type": "product", "product": product}]}],
			}
			for i, product in enumerate(carousel_products)
		],
	}


# Purpose: build the send-time carousel component for a Media Card Carousel — per-card IMAGE/VIDEO
# header (re-uploaded from the template's own media) plus quick-reply button payloads.
# WhatsApp-only: yes — WhatsApp media-carousel template send format.
def _build_media_carousel_send_component(template, whatsapp_account: str | None) -> dict:
	"""Build the send-time `carousel` component for a Media Card Carousel:
	one card per template card, each carrying its own IMAGE/VIDEO header
	parameter (Meta needs the media re-supplied at send time) plus any
	quick-reply button payloads. Card index comes from enumeration, not the
	stored `card_index` (which can be stale/duplicated)."""
	cards = template.carousel_cards or []
	out_cards = []
	for i, card in enumerate(cards):
		card_components = []
		if card.media_sample:
			fmt = card.header_format or "IMAGE"
			card_components.append(
				{
					"type": "header",
					"parameters": [
						media_provider.get_media_header_param(card.media_sample, fmt, whatsapp_account)
					],
				}
			)
		# Quick-reply buttons need their payload echoed back per card; a URL/phone
		# button is static and carries no send-time parameter.
		btn_idx = 0
		for btype, blabel in ((card.button_type, card.button_label), (card.button2_type, card.button2_label)):
			if btype == "Quick Reply":
				card_components.append(
					{
						"type": "button",
						"sub_type": "quick_reply",
						"index": str(btn_idx),
						"parameters": [{"type": "payload", "payload": blabel or ""}],
					}
				)
			if btype:
				btn_idx += 1
		out_cards.append({"card_index": i, "components": card_components})
	return {"type": "carousel", "cards": out_cards}


# ── Buttons ──────────────────────────────────────────────────────────────


# Purpose: build the per-button send components (Catalog, Quick Reply, Call Phone, dynamic URL);
# static URLs are skipped so Meta doesn't reject with #132018.
# WhatsApp-only: yes — WhatsApp template button component format.
def _build_button_components(
	template,
	has_mpm: bool,
	reference_doctype,
	reference_name,
	thumbnail_product_retailer_id: str | None = None,
	coupon_code: str | None = None,
) -> list[dict]:
	"""Build the per-button component entries. Static URLs are skipped —
	sending parameters for them triggers Meta error #132018. A Copy Offer Code
	button needs its coupon code (<= WHATSAPP_COUPON_CODE_MAX chars) at send time."""
	if not template.buttons:
		return []

	out: list[dict] = []
	for idx, btn in enumerate(template.buttons):
		current_idx = str(idx + 1) if has_mpm else str(idx)

		if btn.button_type in ("Catalog", "CATALOG", "CATALOGUE"):
			action_dict = {}
			if thumbnail_product_retailer_id:
				action_dict["thumbnail_product_retailer_id"] = thumbnail_product_retailer_id
			out.append(
				{
					"type": "button",
					"sub_type": "CATALOG",
					"index": current_idx,
					"parameters": [{"type": "action", "action": action_dict}],
				}
			)
		elif btn.button_type == "Copy Offer Code":
			code = str(coupon_code or template.get("offer_code") or "").strip()
			if not code or len(code) > WHATSAPP_COUPON_CODE_MAX:
				frappe.throw(
					_("A coupon code of 1 to {0} characters is required for this template.").format(
						WHATSAPP_COUPON_CODE_MAX
					)
				)
			out.append(
				{
					"type": "button",
					"sub_type": "copy_code",
					"index": current_idx,
					"parameters": [{"type": "coupon_code", "coupon_code": code}],
				}
			)
		elif btn.button_type == "Quick Reply":
			out.append(
				{
					"type": "button",
					"sub_type": "quick_reply",
					"index": current_idx,
					"parameters": [{"type": "payload", "payload": btn.button_label}],
				}
			)
		elif btn.button_type == "Visit Website" and btn.url_type == "Dynamic":
			url = btn.website_url
			if reference_doctype and reference_name:
				ref_doc = frappe.get_doc(reference_doctype, reference_name)
				url = ref_doc.get_formatted(btn.website_url)
			out.append(
				{
					"type": "button",
					"sub_type": "url",
					"index": current_idx,
					"parameters": [{"type": "text", "text": url}],
				}
			)
	return out


# ── Reaction / Location messages (new capability) ─────────────────────────
#
# Added per WHATSAPP_REFACTOR_PLAN.md §14.4 — outbound side only. Inbound
# parsing of these message types lives in the Inbox module's channel
# handler (`inbox.services.channels.whatsapp`), which is out of scope for
# this refactor; see IMPLEMENTATION_REPORT.md "Remaining Work".


# Purpose: build a reaction message body (emoji on a prior message; empty emoji removes it).
# WhatsApp-only: yes — WhatsApp `reaction` message type.
def build_reaction_body(to: str, message_id: str, emoji: str) -> dict:
	"""Build a Meta `reaction` message body.

	`emoji` may be an empty string to remove a previously-sent reaction
	(Meta's documented behaviour for unreacting).
	When `to` is a BSUID, uses the Meta-documented `recipient` field;
	when a phone is known, `to` wins.
	"""
	from msuite_whatsapp.services.channels.inbox_channel import is_bsuid

	target_field = "recipient" if is_bsuid(to) else "to"
	return {
		"messaging_product": "whatsapp",
		"recipient_type": "individual",
		target_field: to,
		"type": "reaction",
		"reaction": {"message_id": message_id, "emoji": emoji or ""},
	}


# Purpose: build a free-form Single Product Message (SPM) interactive card — no template needed.
# WhatsApp-only: yes — WhatsApp interactive `product` message.
def build_product_message(
	catalog_id: str, retailer_id: str, body_text: str | None = None, footer_text: str | None = None
) -> dict:
	"""Return the Meta `interactive` dict for a Single Product Message (SPM)
	— a free-form catalog product card, no template/approval required."""
	interactive: dict = {
		"type": "product",
		"action": {"catalog_id": catalog_id, "product_retailer_id": retailer_id},
	}
	if body_text:
		interactive["body"] = {"text": body_text}
	if footer_text:
		interactive["footer"] = {"text": footer_text}
	return interactive


# Purpose: build a free-form Interactive Product Carousel (2-10 product cards, body only, no template).
# WhatsApp-only: yes — WhatsApp interactive `carousel` message.
def build_product_carousel_message(catalog_id: str, body_text: str, retailer_ids: list[str]) -> dict:
	"""Return the Meta `interactive` dict for an Interactive Product Carousel message
	(Without Template) — 2 to 10 product cards from the same catalog.

	Meta's spec forbids a header, footer, or buttons on a carousel — body +
	cards only — so this builder deliberately takes no header/footer args."""
	if not (WHATSAPP_PRODUCT_CAROUSEL_MIN <= len(retailer_ids) <= WHATSAPP_PRODUCT_CAROUSEL_MAX):
		frappe.throw(
			f"Product carousel needs {WHATSAPP_PRODUCT_CAROUSEL_MIN}-{WHATSAPP_PRODUCT_CAROUSEL_MAX} products, got {len(retailer_ids)}."
		)
	if len(body_text or "") > WHATSAPP_INTERACTIVE_BODY_MAX:
		frappe.throw(
			f"Carousel body text exceeds Meta's {WHATSAPP_INTERACTIVE_BODY_MAX}-character limit ({len(body_text)})."
		)

	return {
		"type": "carousel",
		"body": {"text": body_text or "Check out our products:"},
		"action": {
			"cards": [
				{
					"card_index": i,
					"type": "product",
					"action": {
						"catalog_id": str(catalog_id),
						"product_retailer_id": str(retailer_id),
					},
				}
				for i, retailer_id in enumerate(retailer_ids)
			]
		},
	}


# Purpose: build a location message body (lat/long + optional name/address).
# WhatsApp-only: yes — WhatsApp `location` message type.
def build_location_body(
	to: str, latitude: float, longitude: float, name: str | None = None, address: str | None = None
) -> dict:
	"""Build a Meta `location` message body.

	When `to` is a BSUID, uses the Meta-documented `recipient` field;
	when a phone is known, `to` wins.
	"""
	from msuite_whatsapp.services.channels.inbox_channel import is_bsuid

	target_field = "recipient" if is_bsuid(to) else "to"
	location = {"latitude": latitude, "longitude": longitude}
	if name:
		location["name"] = name
	if address:
		location["address"] = address
	return {
		"messaging_product": "whatsapp",
		"recipient_type": "individual",
		target_field: to,
		"type": "location",
		"location": location,
	}
