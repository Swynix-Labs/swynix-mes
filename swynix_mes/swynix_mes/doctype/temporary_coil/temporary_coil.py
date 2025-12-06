# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class TemporaryCoil(Document):
	def validate(self):
		"""Validate temporary coil data"""
		self.set_temp_coil_id()
		self.validate_workstation_types()
	
	def set_temp_coil_id(self):
		"""Set temp_coil_id to name if not set"""
		if not self.temp_coil_id and self.name:
			self.temp_coil_id = self.name
	
	def after_insert(self):
		"""Set temp_coil_id after insert"""
		if not self.temp_coil_id:
			self.db_set("temp_coil_id", self.name)
			self.temp_coil_id = self.name
	
	def validate_workstation_types(self):
		"""Ensure caster is Caster type and furnace is Furnace type"""
		if self.caster:
			caster_type = frappe.db.get_value("Workstation", self.caster, "workstation_type")
			if caster_type != "Caster":
				frappe.throw(f"Caster '{self.caster}' must be of type 'Caster', found '{caster_type}'")
		
		if self.furnace:
			furnace_type = frappe.db.get_value("Workstation", self.furnace, "workstation_type")
			if furnace_type != "Furnace":
				frappe.throw(f"Furnace '{self.furnace}' must be of type 'Furnace', found '{furnace_type}'")
