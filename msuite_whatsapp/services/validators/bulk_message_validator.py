"""Bulk WhatsApp Message validators — pure functions, no DB writes."""

from __future__ import annotations

from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import get_datetime, get_system_timezone, now_datetime

from msuite_whatsapp.constants import WHATSAPP_COUPON_CODE_MAX
from msuite_whatsapp.queries import recipient_repository as recipients
from msuite_whatsapp.services.validators.recipient_validator import validate_and_normalize_recipients
from msuite_whatsapp.services.validators.template_validator import get_send_requirements

TAP_TARGET_URL_SCHEMES = ("https://", "http://")


# Purpose: ensure a Bulk WhatsApp Message has recipients and return the count.
# WhatsApp-only: yes — validates the WhatsApp bulk-broadcast doctype.
def validate_recipients(doc) -> int:
	"""Ensure recipients exist and return the recipient count.

	Raises if neither a populated recipient list nor an inline recipients
	table is configured. Inline (Individual-mode) rows are also cleaned
	and validated here — Frappe doesn't run a child controller's
	validate() on parent save, so without this, unvalidated numbers
	reached the send pipeline.
	"""
	if doc.recipient_type == "Recipient List":
		if not doc.recipient_list:
			frappe.throw(_("Select a recipient list."))
		count = recipients.count_recipients(doc.recipient_list)
		if count == 0:
			frappe.throw(_("Selected recipient list has no recipients."))
		return count

	if not doc.recipients:
		frappe.throw(_("Add at least one recipient."))
	validate_and_normalize_recipients(doc.recipients)
	return len(doc.recipients)


MPM_MAX_TITLE = 24  # Meta: multi-product section title
MPM_MAX_PRODUCTS = 30  # Meta: products across all sections


# Purpose: require a thumbnail + at least one product when the broadcast is an MPM.
# WhatsApp-only: yes — MPM (Multi-Product Message) is a WhatsApp Commerce message type.
def validate_mpm_configuration(doc) -> None:
	"""Validate MPM (Multi-Product Message) configuration if enabled."""
	if getattr(doc, "is_mpm", 0):
		if not getattr(doc, "thumbnail_product_retailer_id", ""):
			frappe.throw(_("Thumbnail Product Retailer ID is required for Multi-Product Messages."))
		if not getattr(doc, "product_ids", ""):
			frappe.throw(_("At least one Product Retailer ID is required for Multi-Product Messages."))

		# Meta's limits: section title <= 24 characters, <= 30 products. The wizard enforces them too, but
		# a draft saved via API / duplicated / imported would otherwise reach Meta (title) or be silently
		# truncated at send time (products).
		if len(str(getattr(doc, "mpm_header", "") or "")) > MPM_MAX_TITLE:
			frappe.throw(_("The Multi-Product Message section title cannot exceed {0} characters.").format(MPM_MAX_TITLE))
		unique_products = {row.item_code for row in doc.product_ids if row.item_code}
		if len(unique_products) > MPM_MAX_PRODUCTS:
			frappe.throw(_("A Multi-Product Message cannot include more than {0} products.").format(MPM_MAX_PRODUCTS))


# Purpose: refuse to submit a blast against a template Meta hasn't approved.
# WhatsApp-only: yes — "APPROVED" is WhatsApp Templates' own status value.
def validate_template_approved(doc) -> None:
	"""Refuse to submit a blast whose template isn't Meta-approved.

	Without this, an unapproved template's failure only surfaces per
	recipient from Meta's API at send time (bulk_send_service builds the
	outbound payload straight from `doc.template` with no status gate) —
	by then the whole blast is already queued. `status` is the field
	WhatsApp Templates uses for Meta's approval state (see
	`whatsapp_templates.json` / `api/templates.py`'s own `status ==
	"APPROVED"` checks); "APPROVED" is the only usable value — Draft,
	PENDING, REJECTED, PAUSED, and DISABLED all mean sending will fail.
	"""
	if not doc.template:
		return
	status = frappe.db.get_value("WhatsApp Templates", doc.template, "status")
	if status != "APPROVED":
		frappe.throw(
			_("Template {0} is not approved by Meta (status: {1}). Sending would fail per recipient.").format(
				doc.template, status or "Not Set"
			)
		)


# Purpose: require a catalog + 2-10 products for Product Card Carousel broadcasts
# (Media Card Carousels are exempt — their media lives in the template).
# WhatsApp-only: yes — carousel templates are a WhatsApp message format.
def validate_carousel_configuration(doc) -> None:
	"""Validate Product Carousel configuration when the selected template
	is a carousel template (`is_carousel_template` is fetched from it).

	Media Card Carousels (IMAGE/VIDEO card headers) carry their own media in
	the template and need no catalog/products — only Product Card Carousels
	(PRODUCT card headers) require a catalog and 2-10 products."""
	if not getattr(doc, "is_carousel_template", 0):
		return
	if not doc.template or not _is_product_carousel(doc.template):
		return
	if not getattr(doc, "carousel_catalog", ""):
		frappe.throw(_("Carousel Catalog is required for Product Carousel templates."))
	product_count = len({row.item_code for row in (doc.product_ids or []) if row.item_code})
	if not (2 <= product_count <= 10):
		frappe.throw(_("A Product Carousel broadcast needs 2-10 products, got {0}.").format(product_count))


# Purpose: distinguish a Product Card Carousel from a Media Card Carousel by card header.
# WhatsApp-only: yes — reads WhatsApp Template Carousel Card rows.
def _is_product_carousel(template_name: str) -> bool:
	"""True only if the template's carousel cards use PRODUCT headers."""
	cards = frappe.get_all(
		"WhatsApp Template Carousel Card",
		filters={"parent": template_name},
		pluck="header_format",
	)
	return any((fmt or "") == "PRODUCT" for fmt in cards)


# Purpose: check the blast's offer expiry / coupon / tap-link against what its template needs.
# WhatsApp-only: yes — limited-time-offer, Copy Offer Code and tap-target are WhatsApp template features.
def validate_offer_options(doc) -> None:
	"""Validate `offer_expires_at`, `coupon_code`, `tap_target_url/title` on a blast.

	Rules (all raise `frappe.ValidationError`): a required value must be present
	(expiry when the template has a countdown, coupon when it has a Copy Offer
	Code button and no stored code); a value the template cannot use is an error,
	not ignored; expiry must be in the future and after `scheduled_time`; coupon
	<= WHATSAPP_COUPON_CODE_MAX characters and not blank; tap link needs an
	http(s) URL and a title and a Visit Website button. Strips `coupon_code` in
	place. Reads the template (cached); no DB writes.
	"""
	if not doc.template:
		return
	req = get_send_requirements(frappe.get_cached_doc("WhatsApp Templates", doc.template))
	_validate_offer_expiry(doc, req)
	_validate_coupon(doc, req)
	_validate_tap_target(doc, req)


def to_site_naive_datetime(value):
	"""Return `value` as a naive datetime in the site time zone.

	Frappe stores Datetime fields naive in the site zone, but REST callers may
	send ISO strings with an offset (`...Z`, `+05:30`). Those are converted to
	site time (not relabelled) so comparisons with `now_datetime()` neither
	raise `TypeError` nor shift by the UTC offset. Naive input is returned as is.
	"""
	moment = get_datetime(value)
	if moment.tzinfo is None:
		return moment
	return moment.astimezone(ZoneInfo(get_system_timezone())).replace(tzinfo=None)


def _validate_offer_expiry(doc, req: dict) -> None:
	"""Expiry required iff the template has a countdown; must be future and after the schedule."""
	expiry = doc.get("offer_expires_at")
	if not expiry:
		if req["needs_expiry"]:
			frappe.throw(_("Offer end date and time is required for this template."))
		return
	if not req["needs_expiry"]:
		frappe.throw(_("This template has no limited-time offer with a countdown."))
	expiry = to_site_naive_datetime(expiry)
	# Edits to an already-submitted blast must not be blocked by an offer that has since ended.
	before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
	already_submitted = bool(before and before.get("docstatus") == 1)
	if not already_submitted and expiry <= now_datetime():
		frappe.throw(_("Offer end date and time must be in the future."))
	if doc.get("scheduled_time") and expiry <= to_site_naive_datetime(doc.scheduled_time):
		frappe.throw(_("Offer end date and time must be later than the scheduled time."))


def _validate_coupon(doc, req: dict) -> None:
	"""Coupon only for a Copy Offer Code template; required when none is stored; length by characters."""
	raw = doc.get("coupon_code")
	if raw is None or raw == "":
		if req["needs_coupon"] and not req["coupon_prefill"]:
			frappe.throw(_("A coupon code is required for this template."))
		return
	if not req["needs_coupon"]:
		frappe.throw(_("This template has no Copy Offer Code button."))
	code = str(raw).strip()
	if not code:
		frappe.throw(_("Coupon code cannot be blank."))
	if len(code) > WHATSAPP_COUPON_CODE_MAX:
		frappe.throw(_("Coupon code cannot exceed {0} characters.").format(WHATSAPP_COUPON_CODE_MAX))
	doc.coupon_code = code


def _validate_tap_target(doc, req: dict) -> None:
	"""Tap link: URL and title together, http(s) only, template must have a Visit Website button."""
	url = str(doc.get("tap_target_url") or "").strip()
	title = str(doc.get("tap_target_title") or "").strip()
	if not url and not title:
		return
	if not (url and title):
		frappe.throw(_("Tap link needs both a URL and a title."))
	if not url.lower().startswith(TAP_TARGET_URL_SCHEMES):
		frappe.throw(_("Tap link URL must start with http:// or https://."))
	if not req["supports_tap_target"]:
		frappe.throw(_("This template has no Visit Website button."))
