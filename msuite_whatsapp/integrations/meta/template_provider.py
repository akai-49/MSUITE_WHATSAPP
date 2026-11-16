"""
WhatsApp Template provider — all Meta Graph API calls for template
create/update/delete, plus the payload builders that feed them.

This is the only place that knows the shape of Meta's `message_templates`
endpoint. `services/template_service.py` orchestrates (validate → build →
call → persist); doctypes never call this module directly.
"""

from __future__ import annotations

import json
import os

import frappe
import requests
from frappe import _
from frappe.integrations.utils import make_post_request, make_request

from msuite_whatsapp.constants import GRAPH_API_URL, GRAPH_API_VERSION
from msuite_whatsapp.utils.files import detect_mime
from msuite_whatsapp.services.domain import BUTTON_TYPE_TO_META, ParameterFormat
from msuite_whatsapp.queries import account_repository as accounts
from msuite_whatsapp.services.validators.template_validator import parse_limited_time_offer

# ── Credentials ────────────────────────────────────────────────────────────


def get_credentials(whatsapp_account: str) -> dict:
	"""Load API credentials from the linked WhatsApp Account, returned as a
	plain dict so the caller doesn't need to hold a live doc reference."""
	account = accounts.get_account_doc(whatsapp_account)
	token = account.get_password("token")
	waba_id = account.waba_id or account.business_id
	return {
		"token": token,
		"url": GRAPH_API_URL,
		"version": GRAPH_API_VERSION,
		"waba_id": waba_id,
		"business_id": account.business_id,
		"app_id": account.app_id,
		"headers": {
			"authorization": f"Bearer {token}",
			"content-type": "application/json",
		},
	}


# ── Components builder (template *creation* payload) ──────────────────────


def build_components(doc) -> list[dict]:
	"""
	Build the components array for Meta API template create/update.

	Args:
	    doc: WhatsApp Templates document (needs template, buttons, header_type, etc.)

	Returns:
	    list of component dicts ready for Meta API
	"""
	components = []

	# LIMITED_TIME_OFFER (MARKETING + IMAGE/VIDEO header; validated on save).
	# Meta's documented order is header, limited_time_offer, body, buttons.
	lto = parse_limited_time_offer(doc.get("button_configuration"))
	if lto and lto.get("text"):
		if doc.header_type:  # Meta: HEADER -> limited_time_offer -> BODY
			components.append(_build_header(doc))
		components.append(
			{
				"type": "limited_time_offer",
				"limited_time_offer": {
					"text": lto["text"],
					"has_expiration": bool(lto.get("has_expiration", False)),
				},
			}
		)

	# BODY
	body = {"type": "BODY", "text": doc.template}
	example = _build_body_example(doc)
	if example:
		body["example"] = example
	if doc.category == "AUTHENTICATION" and doc.add_security_recommendation:
		body["add_security_recommendation"] = True
	components.append(body)

	# A Catalog template is BODY (+optional FOOTER) + one CATALOG button.
	# Meta binds the catalog at the WABA level; template_type carries the
	# intent — doc.buttons is usually empty for these — so the button is
	# injected here. Any HEADER/other buttons are rejected (400) alongside
	# CATALOG, so return early like the carousel branch below.
	if doc.get("template_type") == "CATALOGUE":
		if doc.footer:
			components.append({"type": "FOOTER", "text": doc.footer})
		label = (
			next(
				(b.button_label for b in (doc.buttons or []) if b.button_type in ("Catalog", "CATALOG")),
				None,
			)
			or "View catalog"
		)
		components.append({"type": "BUTTONS", "buttons": [{"type": "CATALOG", "text": label}]})
		return components

	# A Product Card Carousel template is BODY + CAROUSEL only — Meta
	# rejects (400) a top-level HEADER/FOOTER/BUTTONS alongside CAROUSEL.
	# Each card carries its own HEADER (format=PRODUCT) and BUTTONS
	# instead (see _build_carousel_component).
	if doc.is_carousel and doc.carousel_cards:
		components.append(_build_carousel_component(doc))
		return components

	# HEADER (already emitted ahead of the limited-time offer when there is one)
	if doc.header_type and not (lto and lto.get("text")):
		components.append(_build_header(doc))

	# FOOTER (not supported alongside a limited-time offer)
	if doc.footer and not (lto and lto.get("text")):
		footer = {"type": "FOOTER", "text": doc.footer}
		if doc.category == "AUTHENTICATION" and doc.code_expiration_minutes:
			footer["code_expiration_minutes"] = doc.code_expiration_minutes
		components.append(footer)

	# BUTTONS
	# Single-Product Message template: a PRODUCT header implies exactly one
	# fixed "View" (SPM) button — nothing else. Return early.
	if doc.header_type == "PRODUCT":
		components.append({"type": "BUTTONS", "buttons": [{"type": "SPM", "text": "View"}]})
		return components

	# Multi-Product Message template: HEADER(optional)+BODY+FOOTER(optional)
	# plus one fixed "View items" (MPM) button. Return early.
	if doc.get("template_type") == "MPM":
		label = (
			next((b.button_label for b in (doc.buttons or []) if b.button_type == "MPM"), None)
			or "View items"
		)
		components.append({"type": "BUTTONS", "buttons": [{"type": "MPM", "text": label}]})
		return components

	has_voice_call = False
	if doc.buttons:
		button_block = {"type": "BUTTONS", "buttons": []}
		for btn in doc.buttons:
			button_block["buttons"].append(_build_button(btn, doc))
			if btn.button_type == "Voice Call":
				has_voice_call = True
		components.append(button_block)

	# CALL_PERMISSION_REQUEST
	if has_voice_call or doc.is_call_permission:
		components.append({"type": "CALL_PERMISSION_REQUEST"})

	return components


def is_media_carousel(doc) -> bool:
	"""A carousel is a Media Card Carousel (image/video headers) rather than a
	Product Card Carousel when any card declares an IMAGE/VIDEO header."""
	return any(c.header_format in ("IMAGE", "VIDEO") for c in (doc.carousel_cards or []))


def _build_carousel_component(doc) -> dict:
	"""Build the CAROUSEL component. Two flavours:

	- Product Card Carousel: each card is a PRODUCT header + one SPM/URL button
	  (exactly 2 cards defined at create).
	- Media Card Carousel: each card is an IMAGE/VIDEO header (uploaded handle),
	  an optional card BODY, and up to two buttons (2-10 cards)."""
	if is_media_carousel(doc):
		return {"type": "CAROUSEL", "cards": [_build_media_card(c) for c in doc.carousel_cards]}

	cards = []
	for card in doc.carousel_cards[:2]:
		cards.append(
			{
				"components": [
					{"type": "HEADER", "format": "PRODUCT"},
					{"type": "BUTTONS", "buttons": [_build_carousel_button(card)]},
				]
			}
		)
	return {"type": "CAROUSEL", "cards": cards}


def _build_media_card(card) -> dict:
	"""One Media Card Carousel card: IMAGE/VIDEO header (with its uploaded
	handle), optional card BODY, and optional BUTTONS (up to two)."""
	components = [
		{
			"type": "HEADER",
			"format": card.header_format,
			"example": {"header_handle": [getattr(card, "_media_id", None)]},
		}
	]
	if card.card_body:
		components.append({"type": "BODY", "text": card.card_body})
	buttons = _build_card_buttons(card)
	if buttons:
		components.append({"type": "BUTTONS", "buttons": buttons})
	return {"components": components}


def _build_card_buttons(card) -> list[dict]:
	"""Build up to two Media Card Carousel buttons (quick_reply / url / phone)."""
	buttons = []
	first = _build_one_card_button(
		card.button_type, card.button_label, card.website_url, card.example_url, card.phone_number
	)
	if first:
		buttons.append(first)
	second = _build_one_card_button(
		card.get("button2_type"),
		card.get("button2_label"),
		card.get("button2_website_url"),
		card.get("button2_example_url"),
		card.get("button2_phone_number"),
	)
	if second:
		buttons.append(second)
	return buttons


def _build_one_card_button(btype, label, url, example_url, phone) -> dict | None:
	"""Map one card button (Quick Reply / URL / Call Phone) to Meta's shape.
	SPM is a Product-carousel button and never reaches here."""
	if not btype:
		return None
	if btype == "Quick Reply":
		return {"type": "QUICK_REPLY", "text": label or "Quick Reply"}
	if btype == "URL":
		b = {"type": "URL", "text": label or "Visit", "url": url}
		if url and "{{" in url and example_url:
			b["example"] = [example_url]
		return b
	if btype == "Call Phone":
		return {"type": "PHONE_NUMBER", "text": label or "Call", "phone_number": phone}
	return None


def _build_carousel_button(card) -> dict:
	"""Carousel cards only support two button types (Meta's rule): SPM
	or URL — a distinct, smaller vocabulary from the main template button
	types in `_build_button`, so it gets its own builder rather than
	overloading that string-matching logic.

	SPM text is not just a UI default — Meta rejects (error_subcode
	2388153) any SPM button whose text isn't exactly "View", so it's
	forced here regardless of what's stored on the card.
	"""
	if card.button_type == "URL":
		return {"type": "URL", "text": card.button_label or "View", "url": card.website_url}
	return {"type": "SPM", "text": "View"}


def upload_header_media(doc, creds: dict) -> str | None:
	"""
	Upload the main header media sample and get the handle for template creation.

	Args:
	    doc: WhatsApp Templates document with header_type and sample.
	    creds: dict from `get_credentials()`.

	Returns:
	    The Meta media handle string, or None if no media header.
	"""
	if doc.header_type not in ("IMAGE", "VIDEO", "DOCUMENT"):
		return None
	return _upload_media_handle(doc.media_sample or doc.sample, doc.header_type, creds)


def _upload_media_handle(media_file: str | None, fmt: str, creds: dict) -> str | None:
	"""Upload one media file (IMAGE/VIDEO/DOCUMENT) via the Resumable Upload
	API and return its header handle. Shared by the main template header and
	each Media Card Carousel card. Returns None if no file given."""
	if not media_file:
		return None

	file_path = _get_absolute_path(media_file)

	if not os.path.exists(file_path):
		frappe.throw(_("Sample file not found: {0}").format(media_file))

	file_type = detect_mime(file_path)

	# Auto-convert unsupported image formats (WebP, BMP, TIFF, etc.) to PNG
	converted_tmp = None
	if fmt == "IMAGE" and file_type not in ("image/jpeg", "image/png"):
		file_path, file_type = _convert_to_png(file_path)
		converted_tmp = file_path

	# Validate — Meta only accepts specific formats per header type
	allowed_types = {
		"IMAGE": {"image/jpeg", "image/png", "image/webp"},
		"VIDEO": {"video/mp4", "video/3gpp", "video/quicktime"},
		"DOCUMENT": {"application/pdf"},
	}
	allowed = allowed_types.get(fmt, set())
	if allowed and file_type not in allowed:
		frappe.throw(
			_("File type '{0}' is not supported for {1} headers. Accepted: {2}").format(
				file_type, fmt, ", ".join(sorted(allowed))
			)
		)

	try:
		# Step 1: Create upload session
		payload = {
			"file_length": os.path.getsize(file_path),
			"file_type": file_type,
			"messaging_product": "whatsapp",
		}
		response = make_post_request(
			f"{creds['url']}/{creds['version']}/{creds['app_id']}/uploads",
			headers=creds["headers"],
			data=json.dumps(payload),
		)
		session_id = response["id"]

		# Step 2: Upload file binary
		upload_headers = {"authorization": f"OAuth {creds['token']}"}
		with open(file_path, mode="rb") as f:
			file_content = f.read()

		response = make_post_request(
			f"{creds['url']}/{creds['version']}/{session_id}",
			headers=upload_headers,
			data=file_content,
		)
		return response["h"]
	finally:
		if converted_tmp:
			try:
				os.unlink(converted_tmp)
			except OSError:
				pass


# ── Meta HTTP — create / update / delete ───────────────────────────────────


def _raise_meta_error(exc: Exception) -> None:
	"""Re-throw a Meta Graph API failure with its actual error message.

	`make_post_request` calls `response.raise_for_status()` *before*
	returning, so for any non-2xx response (i.e. every real API error)
	it raises `requests.HTTPError` straight past the `"error" in result`
	check that used to sit after the call — that check was dead code, so
	callers only ever saw a bare "400 Client Error" traceback instead of
	Meta's `error_user_msg`. `frappe.flags.integration_request` still
	holds the raw response (set by `make_request` before raising), same
	as `delete_template` already relies on below.
	"""
	try:
		err = frappe.flags.integration_request.json().get("error", {})
	except Exception:
		frappe.throw(msg=str(exc), title=_("Meta API Error"))
		return
	frappe.throw(
		msg=err.get("error_user_msg") or err.get("message") or str(exc),
		title=err.get("error_user_title", _("Meta API Error")),
	)


def create_template(creds: dict, doc, components: list[dict]) -> dict:
	"""POST a new template to Meta. Returns {"id": ..., "status": ...}."""
	data = {
		"name": doc.actual_name,
		"language": doc.language_code,
		"category": doc.category,
		"components": components,
	}
	if doc.parameter_format == ParameterFormat.NAMED:
		data["parameter_format"] = "NAMED"

	# Meta requires `sub_category` for specialised template types.
	# Without it, templates default to DEFAULT and lose type-specific
	# behaviour (e.g., order tracking, flow triggers).
	_SUB_CATEGORY_MAP = {
		"ORDER_STATUS": "ORDER_STATUS",
		"ORDER_DETAILS": "ORDER_DETAILS",
		"FLOW": "FLOW",
	}
	template_type = doc.get("template_type") or "DEFAULT"
	if template_type in _SUB_CATEGORY_MAP:
		data["sub_category"] = _SUB_CATEGORY_MAP[template_type]

	try:
		result = make_post_request(
			f"{creds['url']}/{creds['version']}/{creds['waba_id']}/message_templates",
			headers=creds["headers"],
			data=json.dumps(data),
		)
	except requests.exceptions.HTTPError as exc:
		_raise_meta_error(exc)
		raise  # _raise_meta_error always throws; unreachable, satisfies control-flow analysis

	return {"id": result["id"], "status": result["status"]}


def update_template(
	creds: dict,
	template_id: str,
	components: list[dict],
	parameter_format: str | None = None,
	category: str | None = None,
) -> None:
	"""POST an update to an existing template on Meta."""
	data: dict = {"components": components}
	if parameter_format:
		data["parameter_format"] = parameter_format
	if category:
		data["category"] = category

	try:
		make_post_request(
			f"{creds['url']}/{creds['version']}/{template_id}",
			headers=creds["headers"],
			data=json.dumps(data),
		)
	except requests.exceptions.HTTPError as exc:
		_raise_meta_error(exc)


def delete_template(creds: dict, actual_name: str) -> None:
	"""DELETE a template from Meta by name. Tolerates "already deleted"."""
	url = f"{creds['url']}/{creds['version']}/{creds['waba_id']}/message_templates?name={actual_name}"
	try:
		make_request("DELETE", url, headers=creds["headers"])
	except Exception as exc:
		if hasattr(frappe.flags, "integration_request") and frappe.flags.integration_request:
			try:
				res = frappe.flags.integration_request.json().get("error", {})
				if res.get("error_user_title") == "Message Template Not Found":
					frappe.msgprint(
						_("Deleted locally (already removed from Meta)."),
						alert=True,
					)
					return
				frappe.throw(
					msg=res.get("error_user_msg", "Delete failed"),
					title=res.get("error_user_title", "Error"),
				)
			except (json.JSONDecodeError, AttributeError):
				# Unparseable error body — don't block the local delete,
				# but leave a trail instead of swallowing it silently.
				frappe.log_error(
					title="WhatsApp template delete_from_meta",
					message=f"Could not delete template {actual_name!r} from Meta: {exc}",
				)
				frappe.msgprint(
					_("Could not confirm deletion on Meta (see Error Log). Deleted locally."),
					alert=True,
				)
		else:
			frappe.log_error(
				title="WhatsApp template delete_from_meta",
				message=f"Could not delete template {actual_name!r} from Meta: {exc}",
			)
			frappe.msgprint(
				_("Could not confirm deletion on Meta (see Error Log). Deleted locally."),
				alert=True,
			)


# ── Internal builders ───────────────────────────────────────────────────────


def _build_body_example(doc):
	"""
	Build the example block for BODY component based on parameter_format.

	Meta's expected formats:
	  POSITIONAL: {"body_text": [["val1", "val2"]]}
	  NAMED:      {"body_text_named_params": [
	                  {"param_name": "student", "example": "John"},
	                  {"param_name": "course", "example": "Electronics"}
	              ]}

	sample_values format:
	  POSITIONAL: "John,Electronics" (comma-separated values)
	  NAMED:      "student=John,course=Electronics" (key=value pairs)
	"""
	if not doc.sample_values:
		return {}

	if doc.parameter_format == ParameterFormat.NAMED:
		params = []
		for pair in doc.sample_values.split(","):
			pair = pair.strip()
			if "=" in pair:
				key, val = pair.split("=", 1)
				params.append(
					{
						"param_name": key.strip(),
						"example": val.strip(),
					}
				)
		return {"body_text_named_params": params} if params else {}

	# Positional
	values = [v.strip() for v in doc.sample_values.split(",")]
	return {"body_text": [values]} if values else {}


def _build_header(doc):
	"""Build header component for Meta API payload."""
	header = {"type": "HEADER", "format": doc.header_type}

	if doc.header_type == "TEXT":
		header["text"] = doc.header
		sample_text = doc.media_sample or doc.sample
		if sample_text:
			header["example"] = {"header_text": [sample_text]}
	elif doc.header_type == "LOCATION":
		pass  # Location provided at send time
	elif doc.header_type == "PRODUCT":
		pass  # Product image/title/price come live from the catalog at send time
	else:
		# IMAGE, VIDEO, DOCUMENT — media upload handle
		if hasattr(doc, "_media_id") and doc._media_id:
			header["example"] = {"header_handle": [doc._media_id]}

	return header


def _build_button(btn, doc):
	"""Build a single Meta API button dict from a WhatsApp Button row."""
	meta_type = BUTTON_TYPE_TO_META.get(btn.button_type, btn.button_type)
	b = {"type": meta_type, "text": btn.button_label}

	if btn.button_type == "Visit Website":
		b["url"] = btn.website_url
		if btn.get("url_type") == "Dynamic" and btn.get("example_url"):
			b["example"] = btn.example_url.split(",")

	elif btn.button_type == "Call Phone":
		phone = btn.phone_number or ""
		if doc.country:
			parts = doc.country.strip().split()
			if len(parts) >= 2:
				isd = parts[-1]
				clean_isd = "".join(c for c in isd if c.isdigit() or c == "+")
				isd_digits = clean_isd.replace("+", "")
				if not (phone.startswith(clean_isd) or phone.startswith(isd_digits)):
					phone = clean_isd + phone
				elif not phone.startswith("+"):
					phone = "+" + phone
		has_plus = phone.startswith("+")
		digits = "".join(c for c in phone if c.isdigit())
		phone = ("+" if has_plus else "") + digits
		b["phone_number"] = phone

	elif btn.button_type == "SPM":
		b["text"] = btn.button_label or "View"

	elif btn.button_type == "Voice Call":
		# Meta Graph API rejects `phone_number` on VOICE_CALL buttons ("unexpected field").
		# WhatsApp In-App Calling buttons take only `type` and `text`.
		pass

	elif btn.button_type == "Flow":
		flow_val = btn.get("flow")
		if flow_val:
			try:
				flow_doc = frappe.get_doc("WhatsApp Flow", flow_val)
				b["flow_id"] = flow_doc.flow_id or flow_doc.flow_name
			except Exception:
				b["flow_id"] = flow_val
		elif btn.get("flow_id"):
			b["flow_id"] = btn.flow_id
		elif doc.get("flow_id"):
			b["flow_id"] = doc.flow_id

		b["flow_action"] = btn.get("flow_action") or "navigate"
		if btn.get("navigate_screen"):
			b["navigate_screen"] = btn.navigate_screen

	elif btn.button_type in ("OTP", "Copy Offer Code"):
		otp_type = btn.get("otp_type") or ("COPY_CODE" if btn.button_type == "Copy Offer Code" else "COPY_CODE")
		if otp_type == "COPY_CODE" or btn.button_type == "Copy Offer Code":
			example_code = doc.offer_code or btn.get("example_url")
			b = {
				"type": "COPY_CODE",
				"text": btn.button_label or "Copy offer code",
			}
			if example_code:
				b["example"] = [example_code] if isinstance(example_code, str) else example_code
		else:
			b = {"type": otp_type, "text": btn.button_label or "Copy Code"}
			if otp_type in ("ONE_TAP", "ZERO_TAP"):
				b["supported_apps"] = [
					{
						"package_name": btn.get("package_name"),
						"signature_hash": btn.get("signature_hash"),
					}
				]
			if otp_type == "ONE_TAP":
				b["autofill_text"] = btn.get("autofill_text") or "Autofill"

	elif btn.button_type in ("Request Contact Info", "REQUEST_CONTACT_INFO"):
		b = {"type": "REQUEST_CONTACT_INFO"}
		if btn.get("button_label"):
			b["text"] = btn.button_label

	return b


def _get_absolute_path(file_name):
	"""Resolve Frappe file path to absolute filesystem path."""
	if not file_name:
		return ""
	if os.path.isabs(file_name) and os.path.exists(file_name):
		return file_name

	clean_name = file_name.split("?")[0].split("#")[0]

	if clean_name.startswith("/files/"):
		path = frappe.get_site_path("public", clean_name.lstrip("/"))
	elif clean_name.startswith("/private/"):
		path = frappe.get_site_path(clean_name.lstrip("/"))
	else:
		path = frappe.get_site_path("public", "files", clean_name.lstrip("/"))

	return os.path.abspath(path)


def _convert_to_png(file_path):
	"""
	Convert an unsupported image format (WebP, BMP, TIFF, etc.) to PNG.

	Uses Pillow for conversion. Returns (new_path, "image/png").
	The converted file is a temp file — used only for the Meta upload.
	"""
	try:
		from PIL import Image
	except ImportError:
		frappe.throw(
			_(
				"Pillow is required to convert this image format. "
				"Install with: pip install Pillow — or upload a JPEG/PNG instead."
			)
		)

	import tempfile

	img = Image.open(file_path)
	# Convert RGBA to RGB if needed (PNG supports both, but be safe)
	if img.mode in ("RGBA", "LA", "P"):
		img = img.convert("RGBA")

	tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
	img.save(tmp.name, format="PNG")
	img.close()

	return tmp.name, "image/png"
