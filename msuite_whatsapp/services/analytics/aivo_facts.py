"""
Pure rule-based Aivo insights helper for WhatsApp Overview Dashboard.

Produces deterministic facts and recommendations based on:
1. Rejected templates (with reason from Meta)
2. Quality rating dips (Yellow / Red)
3. Category with lowest delivery rate
4. Clean empty state when nothing needs attention.

No LLM calls, no dummy strings, no non-functional action buttons.
"""

from __future__ import annotations

from typing import Any


def get_whatsapp_aivo_facts(
	rejected_templates: list[dict[str, Any]] | None = None,
	quality_rating: str | None = None,
	category_metrics: list[dict[str, Any]] | None = None,
	prev_quality_rating: str | None = None,
) -> dict[str, Any]:
	"""Derive rule-based account health and optimization facts.

	Args:
		rejected_templates: List of rejected template summaries with template_name
			and rejection_reason.
		quality_rating: Account or phone quality rating ('GREEN', 'YELLOW', 'RED', 'UNKNOWN').
		category_metrics: List of per-category delivery performance dicts.
		prev_quality_rating: Previous period quality rating for detecting dips.

	Returns:
		dict with keys:
			has_issues: bool
			title: str
			kicker: str
			summary: str
			issues: list[dict]
			stats: list[dict] (for hero insight card)
	"""
	rejected_templates = rejected_templates or []
	category_metrics = category_metrics or []
	issues: list[dict[str, Any]] = []
	stats: list[dict[str, Any]] = []

	# 1. Check rejected templates
	if rejected_templates:
		reject_items = []
		for t in rejected_templates:
			name = t.get("template_name") or t.get("name") or "Template"
			reason = t.get("rejection_reason") or "Policy violation"
			reject_items.append(
				{
					"name": name,
					"reason": reason,
					"fix": "Review template content and parameters against Meta WhatsApp Business Messaging Policy.",
				}
			)

		cnt = len(rejected_templates)
		issues.append(
			{
				"chip": "Meta rejection",
				"chipIcon": "alert-circle",
				"severity": "danger",
				"when": "Recent reviews",
				"title": f"{cnt} template{'s' if cnt > 1 else ''} rejected by Meta",
				"why": (
					f"<b>{cnt} template{'s were' if cnt > 1 else ' was'} rejected</b> during Meta policy checks. "
					"Messages cannot be broadcast using unapproved templates."
				),
				"rejects": reject_items,
				"fixH": "Recommended fixes",
				"fixes": [
					"Ensure template body text complies with Meta commercial terms.",
					"Verify all variable placeholders ({{1}}, {{2}}) include valid sample content.",
					"Resubmit edited templates for Meta review.",
				],
			}
		)
		stats.append(
			{
				"label": f"Rejected templates ({cnt})",
				"value": f"{cnt} failed",
				"dotColor": "var(--status-danger-dot, #EF4444)",
			}
		)

	# 2. Check quality rating
	norm_quality = (quality_rating or "").strip().upper()
	if norm_quality in ("YELLOW", "MEDIUM"):
		issues.append(
			{
				"chip": "Quality dip",
				"chipIcon": "alert-triangle",
				"severity": "warn",
				"when": "Account health",
				"title": "Sender quality rating is Medium",
				"why": (
					"Meta reported elevated user reports or blocks. A prolonged Medium or Low rating "
					"restricts daily messaging tier progression."
				),
				"fixH": "Recommended fixes",
				"fixes": [
					"Exclude unengaged contacts from upcoming marketing broadcasts.",
					"Include clear opt-out options (e.g. reply STOP to unsubscribe).",
					"Ensure recipient lists have opted in recently to avoid spam reporting.",
				],
			}
		)
		stats.append(
			{
				"label": "Sender quality",
				"value": "Medium (Watch)",
				"dotColor": "var(--status-warning-dot, #F59E0B)",
			}
		)
	elif norm_quality in ("RED", "LOW"):
		issues.append(
			{
				"chip": "Critical quality",
				"chipIcon": "alert-triangle",
				"severity": "danger",
				"when": "Account health",
				"title": "Sender quality rating is Low",
				"why": (
					"Meta has flagged this account for excessive user blocks or spam reports. "
					"Sending limits may be immediately throttled."
				),
				"fixH": "Immediate remediation",
				"fixes": [
					"Pause promotional bulk broadcasts immediately.",
					"Verify sender phone number reputation and opt-in consent records.",
					"Prioritize essential transactional confirmations until quality recovers.",
				],
			}
		)
		stats.append(
			{
				"label": "Sender quality",
				"value": "Low (Critical)",
				"dotColor": "var(--status-danger-dot, #EF4444)",
			}
		)
	else:
		stats.append(
			{
				"label": "Sender quality",
				"value": "High",
				"dotColor": "var(--status-success-dot, #10B981)",
			}
		)

	# 3. Check lowest delivery category (ties resolved deterministically by category name)
	active_categories = [
		c for c in category_metrics if int(c.get("sent") or 0) > 0 and c.get("delivery_rate") is not None
	]
	if active_categories:
		# Sort by delivery_rate asc, then category name asc for stable tie-breaking
		sorted_by_delivery = sorted(
			active_categories,
			key=lambda c: (float(c.get("delivery_rate", 0)), str(c.get("category", ""))),
		)
		lowest = sorted_by_delivery[0]
		low_rate = float(lowest.get("delivery_rate", 0))
		low_cat = lowest.get("category") or "Unknown"

		# If delivery is below 90%, flag as an issue
		if low_rate < 90.0:
			issues.append(
				{
					"chip": "Delivery drop",
					"chipIcon": "alert-triangle",
					"severity": "warn",
					"when": "Delivery performance",
					"title": f"{low_cat} delivery rate is {low_rate:.1f}%",
					"why": (
						f"<b>{lowest.get('delivered', 0)} of {lowest.get('sent', 0)}</b> {low_cat.lower()} messages were delivered. "
						f"Failed deliveries suggest invalid numbers or network unreachable contacts."
					),
					"fixH": "Recommended fixes",
					"fixes": [
						"Scrub recipient lists to remove deactivated numbers.",
						"Verify country dial codes on recipient contact records.",
					],
				}
			)
			stats.append(
				{
					"label": f"Lowest delivery — {low_cat}",
					"value": f"{low_rate:.1f}%",
					"dotColor": "var(--status-warning-dot, #F59E0B)",
				}
			)
		else:
			# Highest delivery or most reliable touch
			highest = sorted(
				active_categories,
				key=lambda c: (float(c.get("delivery_rate", 0)), str(c.get("category", ""))),
				reverse=True,
			)[0]
			stats.append(
				{
					"label": f"Most reliable — {highest.get('category')}",
					"value": f"{float(highest.get('delivery_rate', 0)):.1f}% delivered",
					"dotColor": "var(--status-success-dot, #10B981)",
				}
			)

	has_issues = len(issues) > 0
	if not has_issues:
		title = "All systems healthy"
		summary = "Templates are approved and sender quality rating is optimal."
	else:
		title = issues[0]["title"]
		summary = f"{len(issues)} issue{'s' if len(issues) > 1 else ''} detected requiring attention."

	return {
		"has_issues": has_issues,
		"kicker": "Aivo · account health",
		"title": title,
		"summary": summary,
		"issues": issues,
		"stats": stats,
	}
