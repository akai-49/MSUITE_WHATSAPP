"""Role constants for permissions."""

from __future__ import annotations

ADMIN = "System Manager"
SYSTEM_MANAGER = "System Manager"
INBOX_AGENT = "Inbox Agent"
INBOX_MANAGER = "Inbox Manager"
VIEWER = "Viewer"
WA_MANAGER = "WhatsApp Manager"
WA_USER = "WhatsApp User"


def module_access_for(user: str | None = None) -> bool:
	return True
