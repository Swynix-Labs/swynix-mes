# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Coil(Document):
	def before_insert(self):
		"""Set coil_id to name if not already set."""
		# Note: At before_insert, name may not be set yet (autoname happens later)
		# So we handle this in after_insert or via autoname logic
		pass

	def after_insert(self):
		"""After the coil is inserted, set coil_id if empty."""
		if not self.coil_id:
			self.db_set("coil_id", self.name, update_modified=False)

	def validate(self):
		"""Validate coil data."""
		self.validate_mother_coil()
		self.validate_dimensions()

	def validate_mother_coil(self):
		"""
		- If coil_role is 'Mother', mother_coil must be empty.
		- If coil_role is 'Child', mother_coil must be set.
		"""
		if self.coil_role == "Mother" and self.mother_coil:
			frappe.throw(_("Mother Coil field must be empty for a Mother coil."))

		if self.coil_role == "Child" and not self.mother_coil:
			frappe.throw(_("Please select Mother Coil for a Child coil."))

		# Prevent circular reference
		if self.mother_coil and self.mother_coil == self.name:
			frappe.throw(_("A coil cannot be its own mother coil."))

	def validate_dimensions(self):
		"""Basic dimension validation."""
		if self.width_mm and self.width_mm < 0:
			frappe.throw(_("Width cannot be negative."))

		if self.thickness_mm and self.thickness_mm < 0:
			frappe.throw(_("Thickness cannot be negative."))

		if self.weight_mt and self.weight_mt < 0:
			frappe.throw(_("Weight cannot be negative."))

		if self.length_m and self.length_m < 0:
			frappe.throw(_("Length cannot be negative."))

	def before_submit(self):
		"""Actions before submitting the coil."""
		# Ensure coil_id is set
		if not self.coil_id:
			self.coil_id = self.name

	def on_cancel(self):
		"""Actions when coil is cancelled."""
		self.coil_status = "Cancelled"
