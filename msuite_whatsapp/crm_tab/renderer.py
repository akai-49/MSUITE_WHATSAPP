"""Serve Frappe CRM's /crm page with the msuite WhatsApp panel added.

Frappe CRM is not changed. This renderer renders CRM's own `crm/www/crm.html` exactly as Frappe
would, then adds the panel's script and stylesheet before `</body>`. The panel (built from
`frontend/` into `public/crm_tab/`) mounts itself in the WhatsApp tab of the Lead and Deal pages.
"""

import json
import os
from functools import lru_cache

import frappe
from frappe.website.page_renderers.template_page import TemplatePage

# CRM's `website_route_rules` send every /crm/... path to this endpoint.
CRM_ENDPOINT = "crm"
ASSET_URL = "/assets/msuite_whatsapp/crm_tab/"


class CRMPageWithWhatsApp(TemplatePage):
	def can_render(self):
		return self.path == CRM_ENDPOINT and super().can_render()

	def render(self):
		html = self.add_csrf_token(self.get_html())
		return self.build_response(html.replace("</body>", f"{panel_tags()}</body>", 1))


def panel_tags() -> str:
	"""The tags that load the panel, or "" when the bundle has not been built."""
	entry = _panel_entry(_manifest_mtime())
	if not entry:
		return ""
	# The Lemnia pages hide features of MSuite apps this site lacks (see installedApps.js).
	apps = json.dumps(frappe.get_installed_apps())
	styles = "".join(f'<link rel="stylesheet" href="{ASSET_URL}{css}">' for css in entry.get("css", []))
	return (
		f"<script>window.msuite_apps = {apps};</script>"
		f"{styles}"
		f'<script type="module" src="{ASSET_URL}{entry["file"]}"></script>'
	)


def _manifest_path() -> str:
	return frappe.get_app_path("msuite_whatsapp", "public", "crm_tab", ".vite", "manifest.json")


def _manifest_mtime() -> float:
	try:
		return os.path.getmtime(_manifest_path())
	except OSError:
		return 0.0


@lru_cache(maxsize=1)
def _panel_entry(mtime: float) -> dict | None:
	"""The manifest's entry chunk. `mtime` is the cache key, so a rebuild is picked up."""
	if not mtime:
		return None
	with open(_manifest_path()) as f:
		manifest = json.load(f)
	return next((chunk for chunk in manifest.values() if chunk.get("isEntry")), None)
