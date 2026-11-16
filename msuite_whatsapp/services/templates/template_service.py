"""
WhatsApp Template service — orchestrates validate → build → call Meta →
persist. The doctype controller calls into this module; this module
calls validators (rules), providers (Meta HTTP), and repositories (DB).
"""

from __future__ import annotations

import frappe
from frappe import _

from msuite_whatsapp.services.plans.plan_enforcer import check_feature_or_throw
from msuite_whatsapp.services.domain import ParameterFormat
from msuite_whatsapp.integrations.meta import template_provider
from msuite_whatsapp.services.validators import template_validator


def push_to_meta(doc) -> None:
	"""Create or update a template on Meta.

	Draft with no Meta ID → creates new template.
	Has Meta ID → updates existing template.
	"""
	check_feature_or_throw("templates", "Templates")
	template_validator.validate_variables_before_push(
		doc.template,
		doc.sample_values,
		doc.parameter_format,
	)

	creds = template_provider.get_credentials(doc.whatsapp_account)
	media_handle = template_provider.upload_header_media(doc, creds)
	if media_handle:
		doc._media_id = media_handle

	# Media Card Carousel — upload each card's IMAGE/VIDEO header, stash the
	# handle on the card so `build_components` can reference it.
	if doc.is_carousel and doc.carousel_cards:
		for card in doc.carousel_cards:
			if card.header_format in ("IMAGE", "VIDEO") and card.media_sample:
				card._media_id = template_provider._upload_media_handle(
					card.media_sample, card.header_format, creds
				)

	if not doc.actual_name and doc.template_name:
		doc.actual_name = doc.template_name.lower().replace(" ", "_")
		doc.db_set("actual_name", doc.actual_name)

	components = template_provider.build_components(doc)

	if doc.id:
		try:
			param_format = "NAMED" if doc.parameter_format == ParameterFormat.NAMED else "POSITIONAL"
			template_provider.update_template(
				creds,
				doc.id,
				components,
				parameter_format=param_format,
				category=doc.category,
			)
			doc.status = "PENDING"
			doc.db_set("status", "PENDING")
			frappe.msgprint(_("Template submitted for approval on Meta. Status: PENDING"), indicator="green", alert=True)
			return
		except Exception as exc:
			err_str = str(exc)
			if "does not exist" in err_str or "not found" in err_str.lower() or "Unsupported post request" in err_str:
				doc.id = None
				doc.db_set("id", None)
			elif "can't be changed" in err_str.lower() or "2388039" in err_str or "delete or add" in err_str.lower() or "once in 24 hours" in err_str.lower() or "2388124" in err_str:
				frappe.throw(
					msg=_(
						"<b>Meta Policy Restriction:</b> {0}<br><br>"
						"<b>Why:</b> Meta WhatsApp Business API enforces a strict policy allowing a template to be edited <b>only once every 24 hours</b>.<br><br>"
						"<b>Solution:</b> If you need to apply changes immediately without waiting 24 hours, click <b>Duplicate</b> on this template and give it a new name (e.g. <code>{1}_v2</code>) to submit your updated content."
					).format(err_str, doc.template_name),
					title=_("Meta 24-Hour Edit Restriction"),
				)
			else:
				raise

	result = template_provider.create_template(creds, doc, components)
	doc.id = result["id"]
	doc.status = result["status"]
	doc.db_set({"id": doc.id, "status": doc.status})
	frappe.msgprint(
		_("Template pushed to Meta. Status: {0}").format(doc.status),
		indicator="green",
		alert=True,
	)


def delete_from_meta(doc) -> None:
	"""Delete a template from Meta. No-op if it was never pushed."""
	if not doc.id or not doc.actual_name:
		return

	if not doc.whatsapp_account:
		frappe.msgprint(
			_("No WhatsApp Account associated with this template. Deleted locally only."),
			alert=True,
		)
		return

	if not frappe.db.exists("WhatsApp Account", doc.whatsapp_account):
		frappe.msgprint(
			_("WhatsApp Account '{0}' not found. Deleted locally only.").format(doc.whatsapp_account),
			alert=True,
		)
		return

	try:
		creds = template_provider.get_credentials(doc.whatsapp_account)
		template_provider.delete_template(creds, doc.actual_name)
	except Exception as e:
		frappe.msgprint(
			_("Could not delete template from Meta: {0}. Deleted locally.").format(str(e)),
			alert=True,
		)
