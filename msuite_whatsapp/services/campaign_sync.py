"""Safe campaign calendar sync wrapper. Delegates to msuite_campaigns if installed."""

from __future__ import annotations
import frappe


def on_source_save(doc, method: str | None = None) -> None:
	try:
		from msuite_campaigns.campaign.doctype.campaign_calendar_event import campaign_calendar_event
		campaign_calendar_event.on_source_save(doc, method)
	except (ImportError, Exception):
		pass


def on_source_delete(doc, method: str | None = None) -> None:
	try:
		from msuite_campaigns.campaign.doctype.campaign_calendar_event import campaign_calendar_event
		campaign_calendar_event.on_source_delete(doc, method)
	except (ImportError, Exception):
		pass
