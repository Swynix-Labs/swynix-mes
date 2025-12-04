# Copyright (c) 2025, Swynix and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestCoil(FrappeTestCase):
	def test_mother_coil_creation(self):
		"""Test that a Mother coil can be created without mother_coil reference."""
		coil = frappe.new_doc("Coil")
		coil.coil_role = "Mother"
		coil.coil_status = "Cast"
		coil.insert()
		coil.submit()
		
		self.assertEqual(coil.coil_role, "Mother")
		self.assertFalse(coil.mother_coil)
		self.assertEqual(coil.coil_id, coil.name)

	def test_child_coil_requires_mother(self):
		"""Test that a Child coil requires mother_coil reference."""
		coil = frappe.new_doc("Coil")
		coil.coil_role = "Child"
		coil.coil_status = "Cast"
		
		# Should throw error without mother_coil
		self.assertRaises(frappe.ValidationError, coil.insert)

	def test_child_coil_with_mother(self):
		"""Test that a Child coil can be created with mother_coil reference."""
		# First create a mother coil
		mother = frappe.new_doc("Coil")
		mother.coil_role = "Mother"
		mother.coil_status = "Cast"
		mother.insert()
		mother.submit()
		
		# Now create child coil
		child = frappe.new_doc("Coil")
		child.coil_role = "Child"
		child.coil_status = "Cast"
		child.mother_coil = mother.name
		child.insert()
		child.submit()
		
		self.assertEqual(child.mother_coil, mother.name)

	def test_mother_coil_cannot_have_mother_reference(self):
		"""Test that a Mother coil cannot have a mother_coil reference."""
		# Create a mother coil first
		mother1 = frappe.new_doc("Coil")
		mother1.coil_role = "Mother"
		mother1.coil_status = "Cast"
		mother1.insert()
		mother1.submit()
		
		# Try to create another mother with mother_coil set
		mother2 = frappe.new_doc("Coil")
		mother2.coil_role = "Mother"
		mother2.coil_status = "Cast"
		mother2.mother_coil = mother1.name
		
		# Should throw error
		self.assertRaises(frappe.ValidationError, mother2.insert)

	def test_negative_dimensions(self):
		"""Test that negative dimensions are not allowed."""
		coil = frappe.new_doc("Coil")
		coil.coil_role = "Mother"
		coil.coil_status = "Cast"
		coil.width_mm = -100
		
		self.assertRaises(frappe.ValidationError, coil.insert)

