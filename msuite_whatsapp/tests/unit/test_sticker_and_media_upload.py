# Copyright (c) 2026, MSuite and Contributors
# See license.txt

"""Unit tests for WhatsApp sticker support and local media upload."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("FRAPPE_STREAM_LOGGING", "1")

import frappe
from msuite_inbox.inbox.constants import STICKER_MIME, MessageContentType
from msuite_whatsapp.constants import (
	LOCAL_PRIVATE_FILE_PATH_PREFIX,
	MEDIA_SEND_KINDS,
)
from msuite_whatsapp.services.channels import inbox_channel as wa_channel

# Test fixture constants
TEST_FIXTURE_RECIPIENT_PHONE = "919876543210"
TEST_FIXTURE_CUSTOMER_PHONE = "919999999999"
TEST_FIXTURE_ACCOUNT_NAME = "WABA-Test-Account"
TEST_FIXTURE_CONV_NAME = "CONV-001"
TEST_FIXTURE_HANDLE_NAME = "HANDLE-001"
TEST_FIXTURE_INBOX_NAME = "INBOX-001"
TEST_FIXTURE_WABA_ACC_NAME = "WABA-ACC-1"
TEST_FIXTURE_PRIVATE_FILE_DOC = "FILE-0001"
TEST_FIXTURE_DENIED_FILE_DOC = "FILE-0002"


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


class TestStickerConstantsAndShapes(unittest.TestCase):
	"""Test sticker MIME, content types, builder routing, and shape mapping."""

	def setUp(self) -> None:
		"""Initialize clean flags for sticker shapes tests.

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

	def test_constants_defined(self) -> None:
		"""Verify sticker MIME and content type constants are properly registered.

		What:
			Asserts STICKER_MIME is webp and sticker kind maps to MessageContentType.STICKER.

		Params:
			None.

		Returns:
			None.

		Raises:
			AssertionError: If sticker constants do not match expectations.

		Side effects:
			None.
		"""
		self.assertEqual(STICKER_MIME, "image/webp")
		self.assertIn("sticker", MEDIA_SEND_KINDS)
		self.assertIn("sticker", wa_channel._MEDIA_KIND_TO_CONTENT_TYPE)
		self.assertEqual(wa_channel._MEDIA_KIND_TO_CONTENT_TYPE["sticker"], MessageContentType.STICKER)

	def test_build_send_body_sticker_with_link(self) -> None:
		"""Verify outbound sticker payload generation using external URL link.

		What:
			Tests _build_send_body with sticker type and media_url link.

		Params:
			None.

		Returns:
			None.

		Raises:
			AssertionError: If sticker type or link structure does not match expected payload.

		Side effects:
			None.
		"""
		payload = {
			"type": "sticker",
			"media_url": "https://example.com/sticker.webp",
		}
		body = wa_channel._build_send_body(TEST_FIXTURE_RECIPIENT_PHONE, payload)
		self.assertIsNotNone(body)
		self.assertEqual(body["type"], "sticker")
		self.assertEqual(body["sticker"]["link"], "https://example.com/sticker.webp")
		self.assertNotIn("caption", body["sticker"])

	def test_build_send_body_sticker_with_media_id(self) -> None:
		"""Verify outbound sticker payload generation using pre-uploaded media ID.

		What:
			Tests _build_send_body with sticker type and uploaded media_id.

		Params:
			None.

		Returns:
			None.

		Raises:
			AssertionError: If sticker id is not populated in send body.

		Side effects:
			None.
		"""
		payload = {
			"type": "sticker",
			"media_id": "meta_sticker_123",
		}
		body = wa_channel._build_send_body(TEST_FIXTURE_RECIPIENT_PHONE, payload)
		self.assertIsNotNone(body)
		self.assertEqual(body["type"], "sticker")
		self.assertEqual(body["sticker"]["id"], "meta_sticker_123")

	def test_build_send_body_sticker_ignores_caption(self) -> None:
		"""Verify sticker send body strips any disallowed caption field.

		What:
			Tests that captions are excluded from Meta sticker payloads.

		Params:
			None.

		Returns:
			None.

		Raises:
			AssertionError: If caption key is present in sticker payload dictionary.

		Side effects:
			None.
		"""
		payload = {
			"type": "sticker",
			"media_url": "https://example.com/sticker.webp",
			"caption": "Disallowed sticker caption",
		}
		body = wa_channel._build_send_body(TEST_FIXTURE_RECIPIENT_PHONE, payload)
		self.assertIsNotNone(body)
		self.assertNotIn("caption", body["sticker"])

	def test_build_send_body_sticker_rejects_non_webp_mime(self) -> None:
		"""Verify sticker send body rejects non-webp MIME types like image/png.

		What:
			Tests that non-webp MIME types cause _build_send_body to return None.

		Params:
			None.

		Returns:
			None.

		Raises:
			AssertionError: If body is created for invalid MIME.

		Side effects:
			None.
		"""
		payload = {
			"type": "sticker",
			"media_url": "https://example.com/sticker.png",
			"mime_type": "image/png",
		}
		body = wa_channel._build_send_body(TEST_FIXTURE_RECIPIENT_PHONE, payload)
		self.assertIsNone(body)

	def test_build_send_body_sticker_accepts_explicit_webp_mime(self) -> None:
		"""Verify sticker send body succeeds when explicit image/webp MIME is supplied.

		What:
			Tests that explicit image/webp MIME produces valid sticker body.

		Params:
			None.

		Returns:
			None.

		Raises:
			AssertionError: If valid webp payload is rejected.

		Side effects:
			None.
		"""
		payload = {
			"type": "sticker",
			"media_url": "https://example.com/sticker.webp",
			"mime_type": "image/webp",
		}
		body = wa_channel._build_send_body(TEST_FIXTURE_RECIPIENT_PHONE, payload)
		self.assertIsNotNone(body)
		self.assertEqual(body["sticker"]["link"], "https://example.com/sticker.webp")

	def test_outbound_shape_builder_for_sticker(self) -> None:
		"""Verify outbound shape builder normalizes sticker messages into message attachment docs.

		What:
			Tests that _OUTBOUND_SHAPE_BUILDERS["sticker"] returns MessageContentType.STICKER and attachment doc.

		Params:
			None.

		Returns:
			None.

		Raises:
			AssertionError: If content type or attachment media type does not match expectations.

		Side effects:
			None.
		"""
		builder = wa_channel._OUTBOUND_SHAPE_BUILDERS.get("sticker")
		self.assertIsNotNone(builder)
		content_type, text, attachments, _, _ = builder({
			"type": "sticker",
			"media_url": "https://example.com/sticker.webp",
		})
		self.assertEqual(content_type, MessageContentType.STICKER)
		self.assertEqual(len(attachments), 1)
		self.assertEqual(attachments[0].media_type, "Sticker")
		self.assertEqual(attachments[0].file_url, "https://example.com/sticker.webp")


class TestIsOwnHost(unittest.TestCase):
	"""Test hostname matching logic for local site detection."""

	def setUp(self) -> None:
		"""Initialize clean flags and request mock for hostname tests.

		What:
			Sets up isolated frappe.local.flags and frappe.local.request and registers cleanups.

		Params:
			None.

		Returns:
			None.

		Raises:
			None.

		Side effects:
			Patches frappe.local.flags and frappe.local.request with restoration on cleanup.
		"""
		self.addCleanup(_patch_local_attr(frappe.local, "flags", frappe._dict()))
		self.addCleanup(_patch_local_attr(frappe.local, "request", None))

	def test_empty_or_none_hostname(self) -> None:
		"""Verify empty or None hostnames are treated as local site URLs.

		What:
			Tests _is_own_host behavior for relative paths lacking hostnames.

		Params:
			None.

		Returns:
			None.

		Raises:
			AssertionError: If None or empty host is not identified as own host.

		Side effects:
			None.
		"""
		self.assertTrue(wa_channel._is_own_host(None))
		self.assertTrue(wa_channel._is_own_host(""))

	@patch("frappe.utils.get_url", return_value="http://lemnia.localhost:8000")
	def test_matching_site_url(self, _: MagicMock) -> None:
		"""Verify host matching site configured get_url hostname returns True.

		What:
			Tests _is_own_host match against frappe.utils.get_url.

		Params:
			_ (MagicMock): Mocked frappe.utils.get_url.

		Returns:
			None.

		Raises:
			AssertionError: If matching hostname returns False.

		Side effects:
			None.
		"""
		self.assertTrue(wa_channel._is_own_host("lemnia.localhost"))

	@patch("frappe.utils.get_url", return_value="http://lemnia.localhost:8000")
	def test_different_host(self, _: MagicMock) -> None:
		"""Verify foreign domain host returns False.

		What:
			Tests _is_own_host rejection of third-party domains.

		Params:
			_ (MagicMock): Mocked frappe.utils.get_url.

		Returns:
			None.

		Raises:
			AssertionError: If external hostname returns True.

		Side effects:
			None.
		"""
		self.assertFalse(wa_channel._is_own_host("external.domain.com"))

	@patch("frappe.utils.get_url", return_value="http://lemnia.localhost:8000")
	def test_matching_request_host(self, _: MagicMock) -> None:
		"""Verify request host header matching when get_url differs.

		What:
			Tests _is_own_host fallback to current HTTP request host header.

		Params:
			_ (MagicMock): Mocked frappe.utils.get_url.

		Returns:
			None.

		Raises:
			AssertionError: If request host match fails or unrelated host matches.

		Side effects:
			Sets frappe.local.request mock.
		"""
		frappe.local.request = MagicMock(host="tenant.local:8000")
		self.assertTrue(wa_channel._is_own_host("tenant.local"))
		self.assertFalse(wa_channel._is_own_host("unrelated.com"))


class TestUploadLocalMedia(unittest.TestCase):
	"""Test _upload_local_media with edge cases and mocked Meta upload."""

	def setUp(self) -> None:
		"""Initialize mock Frappe database, request, and flags.

		What:
			Sets up isolated test environment mocks with cleanups for db,
			request, site_path, message_log, and local flags.

		Params:
			None.

		Returns:
			None.

		Raises:
			None.

		Side effects:
			Patches frappe.db, frappe.local.db, request, flags, and site_path.
		"""
		self.mock_db = MagicMock()
		p_db = patch.object(frappe, "db", self.mock_db)
		p_db.start()
		self.addCleanup(p_db.stop)

		self.addCleanup(_patch_local_attr(frappe.local, "db", self.mock_db))
		self.addCleanup(_patch_local_attr(frappe.local, "request", None))
		self.addCleanup(_patch_local_attr(frappe.local, "flags", frappe._dict(mute_messages=True)))
		self.addCleanup(_patch_local_attr(frappe.local, "message_log", []))

		if not getattr(frappe.local, "site_path", None):
			self.addCleanup(_patch_local_attr(frappe.local, "site_path", "/tmp/fake_site"))

		p_trans = patch("frappe.translate.get_all_translations", return_value={})
		p_trans.start()
		self.addCleanup(p_trans.stop)

		self.account = frappe._dict(name=TEST_FIXTURE_ACCOUNT_NAME)

	def test_empty_or_none_inputs(self) -> None:
		"""Verify empty or non-media bodies are safely ignored.

		What:
			Tests _upload_local_media with empty dict, text type, or already uploaded ID.

		Params:
			None.

		Returns:
			None.

		Raises:
			AssertionError: If unhandled exception occurs on edge inputs.

		Side effects:
			None.
		"""
		wa_channel._upload_local_media({}, self.account)
		wa_channel._upload_local_media({"type": "text"}, self.account)
		wa_channel._upload_local_media({"type": "image", "image": {}}, self.account)
		wa_channel._upload_local_media({"type": "image", "image": {"id": "already_uploaded"}}, self.account)

	@patch("msuite_whatsapp.services.channels.inbox_channel._is_own_host", return_value=False)
	def test_external_link_not_uploaded(self, _: MagicMock) -> None:
		"""Verify external media links are left untouched and not uploaded to Meta.

		What:
			Tests that foreign URLs (e.g. GIPHY) remain unchanged.

		Params:
			_ (MagicMock): Mocked _is_own_host returning False.

		Returns:
			None.

		Raises:
			AssertionError: If external link is replaced or id is set.

		Side effects:
			None.
		"""
		body = {
			"type": "image",
			"image": {"link": "https://giphy.com/media/xyz/giphy.gif"},
		}
		wa_channel._upload_local_media(body, self.account)
		self.assertEqual(body["image"]["link"], "https://giphy.com/media/xyz/giphy.gif")
		self.assertNotIn("id", body["image"])

	@patch("msuite_whatsapp.services.channels.inbox_channel._is_own_host", return_value=True)
	def test_path_traversal_in_link_rejected(self, _: MagicMock) -> None:
		"""Verify directory traversal attempts in file link paths are rejected.

		What:
			Tests that /files/../../ paths are normalized and excluded from local media upload.

		Params:
			_ (MagicMock): Mocked _is_own_host returning True.

		Returns:
			None.

		Raises:
			AssertionError: If traversed path triggers media upload.

		Side effects:
			None.
		"""
		body = {
			"type": "document",
			"document": {"link": "/files/../../etc/passwd"},
		}
		wa_channel._upload_local_media(body, self.account)
		self.assertIn("link", body["document"])
		self.assertNotIn("id", body["document"])

	@patch("msuite_whatsapp.services.channels.inbox_channel._is_own_host", return_value=True)
	def test_encoded_path_traversal_rejected(self, _: MagicMock) -> None:
		"""Verify percent-encoded directory traversal attempts are rejected.

		What:
			Tests URL-encoded ../ traversal protection in media links.

		Params:
			_ (MagicMock): Mocked _is_own_host returning True.

		Returns:
			None.

		Raises:
			AssertionError: If encoded traversal path triggers upload.

		Side effects:
			None.
		"""
		body = {
			"type": "image",
			"image": {"link": "/files/%2e%2e/%2e%2e/etc/shadow"},
		}
		wa_channel._upload_local_media(body, self.account)
		self.assertIn("link", body["image"])
		self.assertNotIn("id", body["image"])

	@patch("msuite_whatsapp.services.channels.inbox_channel._is_own_host", return_value=True)
	@patch("os.path.exists", return_value=False)
	def test_missing_file_leaves_link_untouched(self, _: MagicMock, __: MagicMock) -> None:
		"""Verify missing disk file preserves original link without crash.

		What:
			Tests non-existent file on disk leaves link intact and does not attach id.

		Params:
			_ (MagicMock): Mocked os.path.exists returning False.
			__ (MagicMock): Mocked _is_own_host.

		Returns:
			None.

		Raises:
			AssertionError: If non-existent file path alters link.

		Side effects:
			None.
		"""
		body = {
			"type": "image",
			"image": {"link": "/files/non_existent_image.png"},
		}
		wa_channel._upload_local_media(body, self.account)
		self.assertIn("link", body["image"])
		self.assertNotIn("id", body["image"])

	@patch("msuite_whatsapp.services.channels.inbox_channel._is_own_host", return_value=True)
	@patch("os.path.exists", return_value=True)
	@patch("msuite_whatsapp.integrations.meta.media_provider.upload_media", return_value="meta_media_img_999")
	def test_public_image_upload_success(
		self, mock_upload: MagicMock, _: MagicMock, __: MagicMock
	) -> None:
		"""Verify public image upload uploads to Meta and converts link to id.

		What:
			Tests that valid public /files/ image is uploaded via upload_media and swapped to media id.

		Params:
			mock_upload (MagicMock): Mocked upload_media function.
			_ (MagicMock): Mocked os.path.exists.
			__ (MagicMock): Mocked _is_own_host.

		Returns:
			None.

		Raises:
			AssertionError: If uploaded id is not assigned or link is not removed.

		Side effects:
			Calls mock upload_media.
		"""
		body = {
			"type": "image",
			"image": {"link": "/files/sample.png", "caption": "Hello image"},
		}
		wa_channel._upload_local_media(body, self.account)
		self.assertNotIn("link", body["image"])
		self.assertEqual(body["image"]["id"], "meta_media_img_999")
		self.assertEqual(body["image"]["caption"], "Hello image")
		mock_upload.assert_called_once_with("/files/sample.png", TEST_FIXTURE_ACCOUNT_NAME)

	@patch("msuite_whatsapp.services.channels.inbox_channel._is_own_host", return_value=True)
	@patch("os.path.exists", return_value=True)
	@patch("msuite_whatsapp.integrations.meta.media_provider.upload_media", return_value="meta_media_doc_888")
	def test_public_document_upload_success(
		self, mock_upload: MagicMock, _: MagicMock, __: MagicMock
	) -> None:
		"""Verify public document upload preserves filename and swaps link to id.

		What:
			Tests that valid public document upload preserves filename attribute and sets uploaded id.

		Params:
			mock_upload (MagicMock): Mocked upload_media function.
			_ (MagicMock): Mocked os.path.exists.
			__ (MagicMock): Mocked _is_own_host.

		Returns:
			None.

		Raises:
			AssertionError: If document filename or media id is invalid.

		Side effects:
			Calls mock upload_media.
		"""
		body = {
			"type": "document",
			"document": {"link": "/files/contract.pdf", "filename": "contract.pdf"},
		}
		wa_channel._upload_local_media(body, self.account)
		self.assertNotIn("link", body["document"])
		self.assertEqual(body["document"]["id"], "meta_media_doc_888")
		self.assertEqual(body["document"]["filename"], "contract.pdf")
		mock_upload.assert_called_once_with("/files/contract.pdf", TEST_FIXTURE_ACCOUNT_NAME)

	@patch("msuite_whatsapp.services.channels.inbox_channel._is_own_host", return_value=True)
	@patch("os.path.exists", return_value=True)
	@patch("msuite_whatsapp.integrations.meta.media_provider.upload_media", return_value="meta_media_stk_777")
	def test_public_sticker_upload_success(
		self, mock_upload: MagicMock, _: MagicMock, __: MagicMock
	) -> None:
		"""Verify public sticker upload swaps link to id without extra attributes.

		What:
			Tests that valid public sticker webp uploads to Meta and sets sticker id.

		Params:
			mock_upload (MagicMock): Mocked upload_media function.
			_ (MagicMock): Mocked os.path.exists.
			__ (MagicMock): Mocked _is_own_host.

		Returns:
			None.

		Raises:
			AssertionError: If sticker id is not set or link is retained.

		Side effects:
			Calls mock upload_media.
		"""
		body = {
			"type": "sticker",
			"sticker": {"link": "/files/smile.webp"},
		}
		wa_channel._upload_local_media(body, self.account)
		self.assertNotIn("link", body["sticker"])
		self.assertEqual(body["sticker"]["id"], "meta_media_stk_777")
		mock_upload.assert_called_once_with("/files/smile.webp", TEST_FIXTURE_ACCOUNT_NAME)

	@patch("msuite_whatsapp.services.channels.inbox_channel._is_own_host", return_value=True)
	@patch("os.path.exists", return_value=True)
	@patch("frappe.has_permission", return_value=True)
	@patch("msuite_whatsapp.integrations.meta.media_provider.upload_media", return_value="meta_media_priv_111")
	def test_private_file_upload_with_permission(
		self, mock_upload: MagicMock, mock_perm: MagicMock, _: MagicMock, __: MagicMock
	) -> None:
		"""Verify private file upload checks permission before uploading.

		What:
			Tests that /private/files/ paths verify File read permission before initiating upload.

		Params:
			mock_upload (MagicMock): Mocked upload_media function.
			mock_perm (MagicMock): Mocked frappe.has_permission returning True.
			_ (MagicMock): Mocked os.path.exists.
			__ (MagicMock): Mocked _is_own_host.

		Returns:
			None.

		Raises:
			AssertionError: If permission check or upload arguments do not match.

		Side effects:
			Queries mock database and checks permission.
		"""
		self.mock_db.get_value.return_value = TEST_FIXTURE_PRIVATE_FILE_DOC
		body = {
			"type": "document",
			"document": {"link": "/private/files/confidential.pdf"},
		}
		wa_channel._upload_local_media(body, self.account)
		self.assertEqual(body["document"]["id"], "meta_media_priv_111")
		self.assertNotIn("link", body["document"])
		self.mock_db.get_value.assert_called_once_with("File", {"file_url": "/private/files/confidential.pdf"}, "name")
		mock_perm.assert_called_once_with("File", "read", doc=TEST_FIXTURE_PRIVATE_FILE_DOC)
		mock_upload.assert_called_once_with("/private/files/confidential.pdf", TEST_FIXTURE_ACCOUNT_NAME)

	@patch("msuite_whatsapp.services.channels.inbox_channel._is_own_host", return_value=True)
	@patch("os.path.exists", return_value=True)
	@patch("frappe.has_permission", return_value=False)
	def test_private_file_upload_denied_permission(
		self, mock_perm: MagicMock, _: MagicMock, __: MagicMock
	) -> None:
		"""Verify private file upload raises PermissionError when user lacks access.

		What:
			Tests that /private/files/ without read permission raises frappe.PermissionError.

		Params:
			mock_perm (MagicMock): Mocked frappe.has_permission returning False.
			_ (MagicMock): Mocked os.path.exists.
			__ (MagicMock): Mocked _is_own_host.

		Returns:
			None.

		Raises:
			AssertionError: If frappe.PermissionError is not raised.

		Side effects:
			Queries mock database.
		"""
		self.mock_db.get_value.return_value = TEST_FIXTURE_DENIED_FILE_DOC
		body = {
			"type": "document",
			"document": {"link": "/private/files/confidential.pdf"},
		}
		with self.assertRaises(frappe.PermissionError):
			wa_channel._upload_local_media(body, self.account)

	@patch("msuite_whatsapp.services.channels.inbox_channel._is_own_host", return_value=True)
	@patch("os.path.exists", return_value=True)
	@patch("msuite_whatsapp.integrations.meta.media_provider.upload_media", side_effect=frappe.ValidationError("Meta API error: File size exceeds 16MB limit"))
	def test_oversized_file_meta_error_propagates(
		self, mock_upload: MagicMock, _: MagicMock, __: MagicMock
	) -> None:
		"""Verify upload size limit validation errors propagate cleanly to caller.

		What:
			Tests that ValidationError from Meta API upload propagates out of _upload_local_media.

		Params:
			mock_upload (MagicMock): Mocked upload_media raising ValidationError.
			_ (MagicMock): Mocked os.path.exists.
			__ (MagicMock): Mocked _is_own_host.

		Returns:
			None.

		Raises:
			AssertionError: If ValidationError is not raised or error message differs.

		Side effects:
			None.
		"""
		body = {
			"type": "image",
			"image": {"link": "/files/giant_image.png"},
		}
		with self.assertRaises(frappe.ValidationError) as cm:
			wa_channel._upload_local_media(body, self.account)
		self.assertIn("File size exceeds 16MB limit", str(cm.exception))


class TestSendIntegrationWithUpload(unittest.TestCase):
	"""Test send() integrates _upload_local_media before send_to_meta."""

	def setUp(self) -> None:
		"""Initialize mock database, flags, and test document objects.

		What:
			Sets up isolated database mock and conversation documents for send integration tests.

		Params:
			None.

		Returns:
			None.

		Raises:
			None.

		Side effects:
			Patches frappe.db, frappe.local.db, and frappe.local.flags with restoration on cleanup.
		"""
		self.mock_db = MagicMock()
		p_db = patch.object(frappe, "db", self.mock_db)
		p_db.start()
		self.addCleanup(p_db.stop)

		self.addCleanup(_patch_local_attr(frappe.local, "db", self.mock_db))
		self.addCleanup(_patch_local_attr(frappe.local, "flags", frappe._dict()))
		self.conv_doc = frappe._dict(
			name=TEST_FIXTURE_CONV_NAME,
			channel_handle=TEST_FIXTURE_HANDLE_NAME,
			customer_phone=TEST_FIXTURE_CUSTOMER_PHONE,
			inbox=TEST_FIXTURE_INBOX_NAME,
		)
		self.account_doc = frappe._dict(name=TEST_FIXTURE_WABA_ACC_NAME)

	@patch("msuite_inbox.inbox.services.dispatcher.is_handle_opted_out", return_value=False)
	@patch("frappe.get_doc")
	@patch("msuite_whatsapp.services.channels.inbox_channel.get_whatsapp_account")
	@patch("msuite_whatsapp.services.channels.inbox_channel._record_outbound", return_value={"message": "MSG-001"})
	@patch("msuite_whatsapp.services.channels.inbox_channel._upload_local_media")
	@patch("msuite_whatsapp.services.channels.inbox_channel.send_to_meta", return_value=({"messages": [{"id": "wamid.123"}]}, "cloud_api"))
	def test_send_calls_upload_local_media(
		self,
		mock_send_to_meta: MagicMock,
		mock_upload: MagicMock,
		mock_record: MagicMock,
		mock_acc: MagicMock,
		mock_get_doc: MagicMock,
		_: MagicMock,
	) -> None:
		"""Verify channel send() invokes _upload_local_media before dispatching to Meta API.

		What:
			Tests that send pipeline executes media upload and Meta API dispatch.

		Params:
			mock_send_to_meta (MagicMock): Mocked Meta dispatch.
			mock_upload (MagicMock): Mocked media upload helper.
			mock_record (MagicMock): Mocked outbound message recorder.
			mock_acc (MagicMock): Mocked account loader.
			mock_get_doc (MagicMock): Mocked document getter.
			_ (MagicMock): Mocked opt-out checker.

		Returns:
			None.

		Raises:
			AssertionError: If _upload_local_media or send_to_meta is not called.

		Side effects:
			Invokes channel send method.
		"""
		mock_acc.return_value = self.account_doc
		mock_get_doc.side_effect = lambda dt, name=None: {
			"Channel Handle": frappe._dict(name=TEST_FIXTURE_HANDLE_NAME, handle_value=TEST_FIXTURE_CUSTOMER_PHONE, handle_type="phone"),
			"Inbox": frappe._dict(name=TEST_FIXTURE_INBOX_NAME, channels=[frappe._dict(channel_type="WhatsApp", whatsapp_account=TEST_FIXTURE_WABA_ACC_NAME)]),
			"WhatsApp Account": self.account_doc,
			"Channel Message": MagicMock(),
		}.get(dt, frappe._dict(name=name))
		payload = {
			"type": "image",
			"media_url": "/files/test.png",
			"to": TEST_FIXTURE_CUSTOMER_PHONE,
		}
		wa_channel.send(self.conv_doc, payload)
		self.assertTrue(mock_upload.called)
		self.assertTrue(mock_send_to_meta.called)
