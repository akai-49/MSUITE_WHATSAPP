"""Tests for WhatsApp template buttons cap."""

import unittest
import frappe
from frappe.tests import IntegrationTestCase


class TestTemplateButtonsCap(unittest.TestCase):
	"""Verify WhatsApp template buttons cap behavior and constant."""

	def test_constant_value(self):
		"""WHATSAPP_TEMPLATE_BUTTONS_MAX should be exported and equal 10."""
		from msuite_whatsapp.constants import WHATSAPP_TEMPLATE_BUTTONS_MAX

		self.assertEqual(WHATSAPP_TEMPLATE_BUTTONS_MAX, 10)

	def test_ten_buttons_accepted(self):
		"""10 quick reply buttons with unique labels should be accepted."""
		from msuite_whatsapp.services.validators.template_validator import validate_buttons

		buttons = [
			frappe._dict(button_type="Quick Reply", button_label=f"QR {i}")
			for i in range(10)
		]
		# Should not throw
		validate_buttons(buttons, category="MARKETING", offer_code=None)

	def test_eleven_buttons_rejected_with_constant_in_message(self):
		"""11 buttons should raise ValidationError mentioning the limit from the constant."""
		from msuite_whatsapp.constants import WHATSAPP_TEMPLATE_BUTTONS_MAX
		from msuite_whatsapp.services.validators.template_validator import validate_buttons

		buttons = [
			frappe._dict(button_type="Quick Reply", button_label=f"QR {i}")
			for i in range(11)
		]
		with self.assertRaises(frappe.ValidationError) as ctx:
			validate_buttons(buttons, category="MARKETING", offer_code=None)

		self.assertIn(str(WHATSAPP_TEMPLATE_BUTTONS_MAX), str(ctx.exception))
