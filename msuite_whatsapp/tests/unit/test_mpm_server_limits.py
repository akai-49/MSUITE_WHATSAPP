from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe import _dict

from msuite_whatsapp.services.validators.bulk_message_validator import validate_mpm_configuration


class _Doc:
	def __init__(self, **kw):
		self.is_mpm = 1
		self.thumbnail_product_retailer_id = "SKU-0"
		self.mpm_header = "Our Products"
		self.product_ids = [_dict(item_code=f"SKU-{i}") for i in range(3)]
		self.__dict__.update(kw)


class TestMpmServerLimits(TestCase):
	def test_title_of_24_chars_is_allowed_25_is_not(self):
		validate_mpm_configuration(_Doc(mpm_header="x" * 24))
		with self.assertRaises(frappe.ValidationError):
			validate_mpm_configuration(_Doc(mpm_header="x" * 25))

	def test_30_unique_products_allowed_31_is_not(self):
		validate_mpm_configuration(_Doc(product_ids=[_dict(item_code=f"S{i}") for i in range(30)]))
		with self.assertRaises(frappe.ValidationError):
			validate_mpm_configuration(_Doc(product_ids=[_dict(item_code=f"S{i}") for i in range(31)]))

	def test_duplicate_rows_do_not_count_twice(self):
		validate_mpm_configuration(_Doc(product_ids=[_dict(item_code="S1")] * 40))

	def test_blank_title_is_allowed_the_sender_has_a_default(self):
		validate_mpm_configuration(_Doc(mpm_header=""))

	def test_non_mpm_blast_is_never_checked(self):
		validate_mpm_configuration(_Doc(is_mpm=0, mpm_header="x" * 99, product_ids=[_dict(item_code=f"S{i}") for i in range(99)]))
