"""Unit tests for _shape_template in inbox_channel.

Tests variable substitution from Meta payload components when body_param
is missing or empty, ensuring local preview/rendering in the Inbox conversation
matches what the recipient actually received.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import frappe
from msuite_inbox.inbox.constants import MessageContentType
from msuite_whatsapp.services.channels import inbox_channel


class TestInboxChannelShapeTemplate(unittest.TestCase):
	"""Test cases for _shape_template and template rendering in inbox_channel."""

	def _mock_db_templates(self, templates_dict: dict[str, str]):
		"""Helper to mock frappe.db.get_value for WhatsApp Templates.

		Args:
			templates_dict (dict[str, str]): Map of template_name -> template_body string.

		Returns:
			unittest.mock._patch: Active patch context manager.
		"""
		def fake_get_value(doctype, name, fieldname=None, as_dict=False):
			if doctype == "WhatsApp Templates":
				if name in templates_dict:
					body = templates_dict[name]
					if as_dict:
						return frappe._dict({"template": body, "parameter_format": "POSITIONAL"})
					return body
				return None
			return None

		return patch.object(frappe.db, "get_value", side_effect=fake_get_value)

	def test_named_variable_components_render_value(self):
		"""Test that named variable parameters in components render correctly.

		Params:
			None.
		Returns:
			None.
		Raises:
			AssertionError: If rendering or tuple structure does not match expectation.
		Side Effects:
			None.
		"""
		templates = {"admission_open_2026": "Hello {{lead_name}}, Admission Open for 2026"}
		payload = {
			"type": "template",
			"template": "admission_open_2026",
			"components": [
				{
					"type": "body",
					"parameters": [
						{"type": "text", "parameter_name": "lead_name", "text": "John Doe"}
					],
				}
			],
		}

		with self._mock_db_templates(templates):
			content_type, text, attachments, interactive_payload, template_name = inbox_channel._shape_template(payload)

		self.assertEqual(content_type, MessageContentType.TEMPLATE)
		self.assertEqual(text, "Hello John Doe, Admission Open for 2026")
		self.assertEqual(template_name, "admission_open_2026")
		self.assertEqual(attachments, [])
		self.assertEqual(interactive_payload, {})

	def test_positional_components_render_by_index(self):
		"""Test that positional parameters in components render by 1-based index.

		Params:
			None.
		Returns:
			None.
		Raises:
			AssertionError: If positional rendering fails.
		Side Effects:
			None.
		"""
		templates = {"appointment_reminder": "Hello {{1}}, your appointment is at {{2}}"}
		payload = {
			"type": "template",
			"template": "appointment_reminder",
			"components": [
				{
					"type": "body",
					"parameters": [
						{"type": "text", "text": "Jane Doe"},
						{"type": "text", "text": "10:00 AM"},
					],
				}
			],
		}

		with self._mock_db_templates(templates):
			_, text, _, _, _ = inbox_channel._shape_template(payload)

		self.assertEqual(text, "Hello Jane Doe, your appointment is at 10:00 AM")

	def test_body_param_present_still_wins_and_is_unchanged(self):
		"""Test that when body_param is provided, it wins over components and is unchanged.

		Params:
			None.
		Returns:
			None.
		Raises:
			AssertionError: If body_param does not take precedence.
		Side Effects:
			None.
		"""
		templates = {"admission_open_2026": "Hello {{lead_name}}, Admission Open for 2026"}
		payload_dict = {
			"type": "template",
			"template": "admission_open_2026",
			"body_param": {"lead_name": "Direct Winner"},
			"components": [
				{
					"type": "body",
					"parameters": [
						{"type": "text", "parameter_name": "lead_name", "text": "Components Loser"}
					],
				}
			],
		}

		with self._mock_db_templates(templates):
			_, text, _, _, _ = inbox_channel._shape_template(payload_dict)

		self.assertEqual(text, "Hello Direct Winner, Admission Open for 2026")

		# Also verify when body_param is passed as a JSON string
		payload_json = {
			"type": "template",
			"template": "admission_open_2026",
			"body_param": '{"lead_name": "JSON Winner"}',
			"components": [
				{
					"type": "body",
					"parameters": [
						{"type": "text", "parameter_name": "lead_name", "text": "Components Loser"}
					],
				}
			],
		}

		with self._mock_db_templates(templates):
			_, text_json, _, _, _ = inbox_channel._shape_template(payload_json)

		self.assertEqual(text_json, "Hello JSON Winner, Admission Open for 2026")

	def test_no_components_and_no_body_param_leaves_text_as_today(self):
		"""Test that omitting both components and body_param leaves placeholders unchanged.

		Params:
			None.
		Returns:
			None.
		Raises:
			AssertionError: If raw template text or fallback changes unexpectedly.
		Side Effects:
			None.
		"""
		templates = {"admission_open_2026": "Hello {{lead_name}}, Admission Open for 2026"}
		payload = {
			"type": "template",
			"template": "admission_open_2026",
		}

		with self._mock_db_templates(templates):
			_, text, _, _, _ = inbox_channel._shape_template(payload)

		self.assertEqual(text, "Hello {{lead_name}}, Admission Open for 2026")

		# Nonexistent template falls back to excerpt([Template] <name>)
		payload_nonexistent = {
			"type": "template",
			"template": "nonexistent_tpl",
		}
		with self._mock_db_templates(templates):
			_, text_nonexistent, _, _, _ = inbox_channel._shape_template(payload_nonexistent)

		self.assertEqual(text_nonexistent, "[Template] nonexistent_tpl")

	def test_missing_or_blank_parameter_value(self):
		"""Test that missing, empty, or None parameter values leave placeholders visible.

		Params:
			None.
		Returns:
			None.
		Raises:
			AssertionError: If missing or blank parameters are improperly formatted.
		Side Effects:
			None.
		"""
		templates = {"verification_code": "Hello {{lead_name}}, your code is {{code}}"}

		# Blank string for 'code'
		payload_empty = {
			"type": "template",
			"template": "verification_code",
			"components": [
				{
					"type": "body",
					"parameters": [
						{"type": "text", "parameter_name": "lead_name", "text": "Alice"},
						{"type": "text", "parameter_name": "code", "text": ""},
					],
				}
			],
		}
		with self._mock_db_templates(templates):
			_, text_empty, _, _, _ = inbox_channel._shape_template(payload_empty)
		self.assertEqual(text_empty, "Hello Alice, your code is {{code}}")

		# None value for 'code'
		payload_none = {
			"type": "template",
			"template": "verification_code",
			"components": [
				{
					"type": "body",
					"parameters": [
						{"type": "text", "parameter_name": "lead_name", "text": "Alice"},
						{"type": "text", "parameter_name": "code", "text": None},
					],
				}
			],
		}
		with self._mock_db_templates(templates):
			_, text_none, _, _, _ = inbox_channel._shape_template(payload_none)
		self.assertEqual(text_none, "Hello Alice, your code is {{code}}")

		# Parameter omitted completely
		payload_omitted = {
			"type": "template",
			"template": "verification_code",
			"components": [
				{
					"type": "body",
					"parameters": [
						{"type": "text", "parameter_name": "lead_name", "text": "Alice"},
					],
				}
			],
		}
		with self._mock_db_templates(templates):
			_, text_omitted, _, _, _ = inbox_channel._shape_template(payload_omitted)
		self.assertEqual(text_omitted, "Hello Alice, your code is {{code}}")

	def test_component_with_text_containing_braces_emoji_unicode(self):
		"""Test that parameters containing braces, emojis, and unicode characters render literally.

		Params:
			None.
		Returns:
			None.
		Raises:
			AssertionError: If special characters or braces break template substitution.
		Side Effects:
			None.
		"""
		templates = {"unicode_test": "Greeting: {{greeting}}, note: {{note}}"}
		payload = {
			"type": "template",
			"template": "unicode_test",
			"components": [
				{
					"type": "body",
					"parameters": [
						{"type": "text", "parameter_name": "greeting", "text": "🎉 René {Special} 🚀"},
						{"type": "text", "parameter_name": "note", "text": "{{escaped}} & éàç 🌟"},
					],
				}
			],
		}

		with self._mock_db_templates(templates):
			_, text, _, _, _ = inbox_channel._shape_template(payload)

		self.assertEqual(text, "Greeting: 🎉 René {Special} 🚀, note: {{escaped}} & éàç 🌟")

	def test_multiple_occurrences_of_same_variable(self):
		"""Test that multiple occurrences of the same named or positional variable are replaced.

		Params:
			None.
		Returns:
			None.
		Raises:
			AssertionError: If repeated placeholders are not all replaced.
		Side Effects:
			None.
		"""
		templates = {
			"multi_named": "Hi {{lead_name}}! Thanks {{lead_name}}, see you {{lead_name}}.",
			"multi_pos": "Row {{1}}: Item {{2}} is ready for {{1}}.",
		}

		payload_named = {
			"type": "template",
			"template": "multi_named",
			"components": [
				{
					"type": "body",
					"parameters": [
						{"type": "text", "parameter_name": "lead_name", "text": "Bob"},
					],
				}
			],
		}
		with self._mock_db_templates(templates):
			_, text_named, _, _, _ = inbox_channel._shape_template(payload_named)
		self.assertEqual(text_named, "Hi Bob! Thanks Bob, see you Bob.")

		payload_pos = {
			"type": "template",
			"template": "multi_pos",
			"components": [
				{
					"type": "body",
					"parameters": [
						{"type": "text", "text": "First"},
						{"type": "text", "text": "Book"},
					],
				}
			],
		}
		with self._mock_db_templates(templates):
			_, text_pos, _, _, _ = inbox_channel._shape_template(payload_pos)
		self.assertEqual(text_pos, "Row First: Item Book is ready for First.")
