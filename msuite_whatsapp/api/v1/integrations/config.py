"""WhatsApp Chat configuration API."""

import frappe


@frappe.whitelist(allow_guest=True)
def settings(token=None):
	"""
	Return chat session configuration.

	Args:
	    token: Optional guest token (unused, kept for compatibility)

	Returns:
	    Dict with socket config, user info, chat settings
	"""
	is_admin = frappe.session.user != "Guest"

	config = {
		"socketio_port": frappe.conf.socketio_port,
		"user_email": frappe.session.user,
		"is_admin": is_admin,
		"enable_chat": True,
		"chat_status": "Online",
	}

	if is_admin:
		config["user"] = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user
		config["user_settings"] = {
			"enable_message_tone": 1,
			"enable_notifications": 1,
		}
	else:
		config["user"] = "Guest"

	return config
