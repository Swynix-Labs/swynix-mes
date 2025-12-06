# Copyright (c) 2025, Swynix and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestMeltingBatch(FrappeTestCase):
	def test_charged_weight_calculation(self):
		"""Test that charged_weight_mt is calculated from raw materials"""
		doc = frappe.new_doc("Melting Batch")
		doc.shift = "A"
		doc.plan_date = frappe.utils.today()
		
		# Add raw materials
		doc.append("raw_materials", {
			"item_code": "Test Item",
			"qty_kg": 500
		})
		doc.append("raw_materials", {
			"item_code": "Test Item 2",
			"qty_kg": 300
		})
		
		doc.validate()
		
		self.assertEqual(doc.charged_weight_mt, 0.8)  # 800 kg = 0.8 MT

	def test_yield_calculation(self):
		"""Test yield percentage calculation"""
		doc = frappe.new_doc("Melting Batch")
		doc.charged_weight_mt = 1.0  # 1000 kg
		doc.tapped_weight_mt = 0.95  # 950 kg
		
		doc.calculate_yield_percent()
		
		self.assertEqual(doc.yield_percent, 95.0)

	def test_datetime_validation(self):
		"""Test that batch_start cannot be after batch_end"""
		doc = frappe.new_doc("Melting Batch")
		doc.batch_start_datetime = "2025-12-04 12:00:00"
		doc.batch_end_datetime = "2025-12-04 10:00:00"  # Before start
		
		with self.assertRaises(frappe.ValidationError):
			doc.validate_datetime_sequence()













