# Copyright (c) 2026, MSuite and Contributors
# See license.txt

"""Unit tests for avatar enqueue delegation in WhatsApp connect service."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("FRAPPE_STREAM_LOGGING", "1")

import frappe
from msuite_whatsapp.services.accounts import connect

# Test fixture constants
TEST_FIXTURE_SYSTEM_USER_TOKEN_1 = "test_fixture_waba_token_123"
TEST_FIXTURE_SYSTEM_USER_TOKEN_2 = "test_fixture_waba_token_456"
TEST_FIXTURE_WABA_ID_1 = "12345"
TEST_FIXTURE_WABA_ID_2 = "67890"
TEST_FIXTURE_EXISTING_WABA_DOC = "EXISTING-WABA-DOC"
TEST_FIXTURE_NEW_WABA_DOC = "NEW-WABA-DOC"
TEST_FIXTURE_AVATAR_URL_1 = "https://cdn.example.com/waba_avatar.png"
TEST_FIXTURE_AVATAR_URL_2 = "https://cdn.example.com/new_avatar.png"


def _patch_local_attr(target_obj: object, attr_name: str, new_value: object):
	"""Patch an attribute on frappe.local and return a cleanup callback.

	What:
		Saves previous state and assigns new_value to target_obj.attr_name.
		Restores original value or deletes attribute if it did not exist.

	Params:
		target_obj (object): Object to patch (typically frappe.local).
		attr_name (str): Attribute name to set.
		new_value (object): Value to assign.

	Returns:
		callable: Zero-argument cleanup function that restores prior state.

	Raises:
		None.

	Side effects:
		Mutates target_obj attribute until cleanup callback is invoked.
	"""
	had_attr = hasattr(target_obj, attr_name)
	orig_val = getattr(target_obj, attr_name, None) if had_attr else None
	setattr(target_obj, attr_name, new_value)

	def cleanup() -> None:
		if had_attr:
			setattr(target_obj, attr_name, orig_val)
		elif hasattr(target_obj, attr_name):
			delattr(target_obj, attr_name)

	return cleanup


class TestEnqueueAccountAvatar(unittest.TestCase):
	"""Test lazy avatar enqueue resolution via hooks or msuite_social."""

	def setUp(self) -> None:
		"""Initialize clean test flags for avatar enqueue tests.

		What:
			Sets up isolated frappe.local.flags and registers cleanup.

		Params:
			None.

		Returns:
			None.

		Raises:
			None.

		Side effects:
			Patches frappe.local.flags with restoration on cleanup.
		"""
		self.addCleanup(_patch_local_attr(frappe.local, "flags", frappe._dict()))

	def test_empty_or_none_avatar_url(self) -> None:
		"""Verify empty or None avatar URLs bypass both hooks and app checks.

		What:
			Tests that calling _enqueue_account_avatar with empty or None url exits early.

		Params:
			None.

		Returns:
			None.

		Raises:
			AssertionError: If hooks or installed app checks are invoked.

		Side effects:
			Patches frappe.get_hooks and frappe.get_installed_apps.
		"""
		with patch("frappe.get_hooks") as mock_hooks, patch("frappe.get_installed_apps") as mock_apps:
			connect._enqueue_account_avatar("WhatsApp Account", "WABA-1", "")
			connect._enqueue_account_avatar("WhatsApp Account", "WABA-1", None)
			mock_hooks.assert_not_called()
			mock_apps.assert_not_called()

	@patch("frappe.get_hooks", return_value=["msuite_social.avatar_handler"])
	@patch("frappe.get_attr")
	def test_hook_resolution_success(self, mock_get_attr: MagicMock, _: MagicMock) -> None:
		"""Verify hook resolution executes configured handler with correct args.

		What:
			Tests successful invocation of social_account_avatar_handler hook function.

		Params:
			mock_get_attr (MagicMock): Mocked frappe.get_attr returning mock handler.
			_ (MagicMock): Mocked frappe.get_hooks.

		Returns:
			None.

		Raises:
			AssertionError: If hook handler is not called with expected arguments.

		Side effects:
			Executes mock handler function.
		"""
		mock_handler = MagicMock()
		mock_get_attr.return_value = mock_handler
		connect._enqueue_account_avatar("WhatsApp Account", "WABA-1", "https://example.com/avatar.jpg")
		mock_get_attr.assert_called_once_with("msuite_social.avatar_handler")
		mock_handler.assert_called_once_with("WhatsApp Account", "WABA-1", "https://example.com/avatar.jpg")

	@patch("frappe.get_hooks", return_value=["failing_hook"])
	@patch("frappe.get_attr")
	def test_hook_exception_swallowed_gracefully(self, mock_get_attr: MagicMock, _: MagicMock) -> None:
		"""Verify hook execution exceptions are caught and swallowed gracefully.

		What:
			Tests that exceptions in avatar hook handlers do not crash connect flow.

		Params:
			mock_get_attr (MagicMock): Mocked frappe.get_attr returning failing handler.
			_ (MagicMock): Mocked frappe.get_hooks.

		Returns:
			None.

		Raises:
			AssertionError: If exception is propagated out of _enqueue_account_avatar.

		Side effects:
			None.
		"""
		mock_handler = MagicMock(side_effect=Exception("Hook exploded"))
		mock_get_attr.return_value = mock_handler
		connect._enqueue_account_avatar("WhatsApp Account", "WABA-1", "https://example.com/avatar.jpg")
		mock_handler.assert_called_once()

	@patch("frappe.get_hooks", return_value=[])
	@patch("frappe.get_installed_apps", return_value=["msuite_social", "msuite_whatsapp"])
	def test_msuite_social_dynamic_import_success(self, _: MagicMock, __: MagicMock) -> None:
		"""Verify direct dynamic import delegation when msuite_social is installed.

		What:
			Tests fallback to msuite_social.social_post.avatar.enqueue_account_avatar when hook is absent.

		Params:
			_ (MagicMock): Mocked frappe.get_hooks returning empty list.
			__ (MagicMock): Mocked frappe.get_installed_apps.

		Returns:
			None.

		Raises:
			AssertionError: If enqueue_account_avatar on dynamic module is not called.

		Side effects:
			Patches sys.modules dictionary during test.
		"""
		mock_social_mod = MagicMock()
		with patch.dict(sys.modules, {"msuite_social.social_post.avatar": mock_social_mod}):
			connect._enqueue_account_avatar("WhatsApp Account", "WABA-1", "https://example.com/avatar.jpg")
			mock_social_mod.enqueue_account_avatar.assert_called_once_with(
				"WhatsApp Account", "WABA-1", "https://example.com/avatar.jpg"
			)

	@patch("frappe.get_hooks", return_value=[])
	@patch("frappe.get_installed_apps", return_value=["msuite_whatsapp"])
	def test_msuite_social_not_installed_noop(self, _: MagicMock, __: MagicMock) -> None:
		"""Verify no operation and no crash when msuite_social is not installed.

		What:
			Tests graceful noop when both hooks and msuite_social app are absent.

		Params:
			_ (MagicMock): Mocked frappe.get_hooks.
			__ (MagicMock): Mocked frappe.get_installed_apps.

		Returns:
			None.

		Raises:
			AssertionError: If importlib.import_module is called when app not installed.

		Side effects:
			None.
		"""
		with patch("importlib.import_module") as mock_import:
			connect._enqueue_account_avatar("WhatsApp Account", "WABA-1", "https://example.com/avatar.jpg")
			mock_import.assert_not_called()


class TestHandleWhatsAppCredentialsAvatar(unittest.TestCase):
	"""Test _handle_whatsapp_credentials triggers avatar enqueue on create and update."""

	def setUp(self) -> None:
		"""Initialize mock Frappe database, flags, and cleanup handlers.

		What:
			Mocks frappe.db and frappe.local.db, and registers restoration cleanups.

		Params:
			None.

		Returns:
			None.

		Raises:
			None.

		Side effects:
			Patches frappe.db and frappe.local.db/flags with restoration on cleanup.
		"""
		self.mock_db = MagicMock()
		p_db = patch.object(frappe, "db", self.mock_db)
		p_db.start()
		self.addCleanup(p_db.stop)

		self.addCleanup(_patch_local_attr(frappe.local, "db", self.mock_db))
		self.addCleanup(_patch_local_attr(frappe.local, "flags", frappe._dict()))

	@patch("frappe.get_doc")
	@patch("frappe.enqueue")
	@patch("msuite_whatsapp.services.accounts.connect._enqueue_account_avatar")
	def test_existing_account_enqueues_avatar(
		self, mock_enqueue_avatar: MagicMock, _: MagicMock, mock_get_doc: MagicMock
	) -> None:
		"""Verify existing WhatsApp account update dispatches avatar enqueue.

		What:
			Tests that updating an existing account enqueues avatar caching with account docname and URL.

		Params:
			mock_enqueue_avatar (MagicMock): Mocked avatar enqueue function.
			_ (MagicMock): Mocked frappe.enqueue.
			mock_get_doc (MagicMock): Mocked frappe.get_doc.

		Returns:
			None.

		Raises:
			AssertionError: If avatar enqueue is not called with expected arguments.

		Side effects:
			Patches frappe.get_doc and enqueue.
		"""
		self.mock_db.get_value.return_value = TEST_FIXTURE_EXISTING_WABA_DOC
		doc_mock = MagicMock()
		doc_mock.name = TEST_FIXTURE_EXISTING_WABA_DOC
		mock_get_doc.return_value = doc_mock

		creds = {
			"waba_id": TEST_FIXTURE_WABA_ID_1,
			"waba_name": "My Business",
			"system_user_token": TEST_FIXTURE_SYSTEM_USER_TOKEN_1,
			"avatar_url": TEST_FIXTURE_AVATAR_URL_1,
			"phones": [],
		}
		connect._handle_whatsapp_credentials(creds)
		mock_enqueue_avatar.assert_called_once_with(
			"WhatsApp Account", TEST_FIXTURE_EXISTING_WABA_DOC, TEST_FIXTURE_AVATAR_URL_1
		)

	@patch("frappe.new_doc")
	@patch("frappe.enqueue")
	@patch("msuite_whatsapp.services.accounts.connect._trigger_whatsapp_connect_sync")
	@patch("msuite_whatsapp.services.accounts.connect._enqueue_account_avatar")
	def test_new_account_enqueues_avatar(
		self, mock_enqueue_avatar: MagicMock, _: MagicMock, __: MagicMock, mock_new_doc: MagicMock
	) -> None:
		"""Verify new WhatsApp account creation dispatches avatar enqueue.

		What:
			Tests that creating a new WhatsApp account enqueues avatar caching for the newly generated doc.

		Params:
			mock_enqueue_avatar (MagicMock): Mocked avatar enqueue function.
			_ (MagicMock): Mocked frappe.enqueue.
			__ (MagicMock): Mocked sync trigger function.
			mock_new_doc (MagicMock): Mocked frappe.new_doc.

		Returns:
			None.

		Raises:
			AssertionError: If avatar enqueue is not called with expected arguments.

		Side effects:
			Patches frappe.new_doc and enqueue.
		"""
		self.mock_db.get_value.return_value = None
		doc_mock = MagicMock()
		doc_mock.name = TEST_FIXTURE_NEW_WABA_DOC
		mock_new_doc.return_value = doc_mock

		creds = {
			"waba_id": TEST_FIXTURE_WABA_ID_2,
			"waba_name": "New Business",
			"system_user_token": TEST_FIXTURE_SYSTEM_USER_TOKEN_2,
			"avatar_url": TEST_FIXTURE_AVATAR_URL_2,
			"phones": [],
		}
		connect._handle_whatsapp_credentials(creds)
		mock_enqueue_avatar.assert_called_once_with(
			"WhatsApp Account", TEST_FIXTURE_NEW_WABA_DOC, TEST_FIXTURE_AVATAR_URL_2
		)

	@patch("frappe.get_doc")
	@patch("frappe.enqueue")
	@patch("msuite_whatsapp.services.accounts.connect._enqueue_account_avatar")
	def test_no_avatar_does_not_enqueue(
		self, mock_enqueue_avatar: MagicMock, _: MagicMock, mock_get_doc: MagicMock
	) -> None:
		"""Verify missing avatar_url does not dispatch avatar enqueue.

		What:
			Tests that credential payload without avatar_url skips avatar enqueue entirely.

		Params:
			mock_enqueue_avatar (MagicMock): Mocked avatar enqueue function.
			_ (MagicMock): Mocked frappe.enqueue.
			mock_get_doc (MagicMock): Mocked frappe.get_doc.

		Returns:
			None.

		Raises:
			AssertionError: If avatar enqueue is called when URL is omitted.

		Side effects:
			Patches frappe.get_doc and enqueue.
		"""
		self.mock_db.get_value.return_value = TEST_FIXTURE_EXISTING_WABA_DOC
		doc_mock = MagicMock()
		doc_mock.name = TEST_FIXTURE_EXISTING_WABA_DOC
		mock_get_doc.return_value = doc_mock

		creds = {
			"waba_id": TEST_FIXTURE_WABA_ID_1,
			"waba_name": "My Business",
			"system_user_token": TEST_FIXTURE_SYSTEM_USER_TOKEN_1,
			"phones": [],
		}
		connect._handle_whatsapp_credentials(creds)
		mock_enqueue_avatar.assert_not_called()
