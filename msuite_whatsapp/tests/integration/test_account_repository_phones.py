"""Account resolution reads the `phones` child table only (the legacy flat
fields on WhatsApp Account are gone). No network."""

import frappe
from frappe.tests import IntegrationTestCase

from msuite_whatsapp.queries import account_repository as repo


def _account(name, phones):
	doc = frappe.get_doc({"doctype": "WhatsApp Account", "account_name": name, "status": "Active", "phones": phones})
	doc.insert(ignore_permissions=True)
	return doc.name


def _phone(pid, display, **kw):
	return {"phone_number_id": pid, "display_phone_number": display, "status": "Active", **kw}


class TestAccountRepositoryPhones(IntegrationTestCase):
	def setUp(self):
		frappe.db.sql("UPDATE `tabWhatsApp Phone Number` SET is_default_incoming=0, is_default_outgoing=0")

	def test_find_account_by_phone_uses_child_table_only(self):
		acc = _account("Repo A", [_phone("repo-111", "+1 111")])
		self.assertEqual(repo.find_account_by_phone_number_id("repo-111"), acc)
		self.assertIsNone(repo.find_account_by_phone_number_id("repo-unknown"))

	def test_default_account_follows_the_phone_flag(self):
		_account("Repo B", [_phone("repo-b1", "+1 b1")])
		target = _account("Repo C", [_phone("repo-c1", "+1 c1", is_default_incoming=1)])
		self.assertEqual(repo.find_default_account("incoming"), target)

	def test_phone_number_id_requires_a_phone_row(self):
		acc = _account("Repo D", [])
		with self.assertRaises(frappe.ValidationError):
			repo.get_phone_number_id(acc)

	def test_display_phone_prefers_default_outgoing_then_first(self):
		acc = _account("Repo E", [_phone("e1", "+1 first"), _phone("e2", "+1 default", is_default_outgoing=1)])
		self.assertEqual(repo.get_display_phone_number(acc), "+1 default")
		acc2 = _account("Repo F", [_phone("f1", "+1 only")])
		self.assertEqual(repo.get_display_phone_number(acc2), "+1 only")
		self.assertEqual(repo.get_display_phone_number(_account("Repo G", [])), "")

	def test_default_phone_account_never_guesses_an_active_account(self):
		_account("Repo H", [_phone("h1", "+1 h1")])
		self.assertIsNone(repo.find_default_phone_account("incoming"))
		target = _account("Repo I", [_phone("i1", "+1 i1", is_default_incoming=1)])
		self.assertEqual(repo.find_default_phone_account("incoming"), target)

	def test_webhook_account_stamp_ignores_unknown_phone_id(self):
		from msuite_whatsapp.services.webhooks.inbound_webhook import _resolve_whatsapp_account_for_value

		acc = _account("Repo J", [_phone("j1", "+1 j1")])
		self.assertEqual(_resolve_whatsapp_account_for_value({"metadata": {"phone_number_id": "j1"}}, "no-inbox"), acc)
		self.assertEqual(_resolve_whatsapp_account_for_value({"metadata": {"phone_number_id": "zzz"}}, "no-inbox"), "")
