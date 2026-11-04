"""
WhatsApp module for MSuite Workspace.

Doctypes: WhatsApp Account, Message, Contact, Templates, Notification,
          Flow, Call, Bulk Message, Recipients, Settings, Profiles.

This folder holds only the DocTypes, because Frappe finds them through the module's name.
Everything else follows the app layout: api/v1/, services/, queries/, integrations/, tasks/, utils/.

Plan enforcement: all gated via hooks.py doc_events → plan_enforcer.py
"""
