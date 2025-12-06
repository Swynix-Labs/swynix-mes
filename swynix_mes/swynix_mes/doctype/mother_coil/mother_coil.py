# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, getdate


class MotherCoil(Document):
	def validate(self):
		"""Validation logic for Mother Coil"""
		self.validate_workstation_types()
		self.set_temp_coil_id()
		
	def validate_workstation_types(self):
		"""Ensure caster is Caster type and furnace is Furnace type"""
		if self.caster:
			caster_type = frappe.db.get_value("Workstation", self.caster, "workstation_type")
			if caster_type != "Caster":
				frappe.throw(_(f"Caster '{self.caster}' must be of type 'Caster', found '{caster_type}'"))
		
		if self.furnace:
			furnace_type = frappe.db.get_value("Workstation", self.furnace, "workstation_type")
			if furnace_type != "Furnace":
				frappe.throw(_(f"Furnace '{self.furnace}' must be of type 'Furnace', found '{furnace_type}'"))
	
	def set_temp_coil_id(self):
		"""Set temp_coil_id to name if not set"""
		if not self.temp_coil_id and self.name:
			self.temp_coil_id = self.name
	
	def after_insert(self):
		"""Set temp_coil_id after insert"""
		if not self.temp_coil_id:
			self.db_set("temp_coil_id", self.name)
			self.temp_coil_id = self.name
	
	def before_save(self):
		"""Generate coil number when QC is approved"""
		# Generate coil_no only when QC status changes to Approved and coil_no is not yet set
		if self.qc_status == "Approved" and not self.coil_no:
			self.generate_coil_number()
	
	def generate_coil_number(self):
		"""
		Generate factory-formatted coil number: C{CasterNo}{YY}{MonthCode}{DD}{Seq}
		
		Example:
			Date: 10-10-2025
			Caster No: 1
			First coil of day: C125J10001
		
		Month Code:
			A=Jan, B=Feb, C=Mar, D=Apr, E=May, F=Jun,
			G=Jul, H=Aug, I=Sep, J=Oct, K=Nov, L=Dec
		"""
		if not self.caster:
			frappe.throw(_("Caster is required to generate coil number"))
		
		# Get caster number from workstation
		caster_no = frappe.db.get_value("Workstation", self.caster, "caster_no")
		if not caster_no:
			frappe.throw(_("Caster '{0}' does not have a caster_no defined. Please set caster_no in Workstation.").format(self.caster))
		
		# Use cast_date or today
		date_obj = getdate(self.cast_date) if self.cast_date else getdate()
		
		# Format components
		yy = date_obj.strftime("%y")  # 25 for 2025
		month_code = "ABCDEFGHIJKL"[date_obj.month - 1]  # A-L for Jan-Dec
		dd = date_obj.strftime("%d")  # 01-31
		
		# Build prefix
		prefix = f"C{caster_no}{yy}{month_code}{dd}"
		
		# Find last coil number with this prefix
		last_coil = frappe.db.sql("""
			SELECT coil_no
			FROM `tabMother Coil`
			WHERE coil_no LIKE %s
			ORDER BY coil_no DESC
			LIMIT 1
		""", (prefix + "%",), as_dict=True)
		
		if last_coil and last_coil[0].coil_no:
			# Extract sequence from last coil
			last_seq = int(last_coil[0].coil_no[-4:])
			seq = last_seq + 1
		else:
			# First coil of the day
			seq = 1
		
		# Generate final coil number
		self.coil_no = f"{prefix}{seq:04d}"
		
		frappe.msgprint(_("Coil Number Generated: {0}").format(self.coil_no), alert=True, indicator="green")


@frappe.whitelist()
def convert_temp_to_mother(temp_coil_name):
	"""
	Convert a Temporary Coil to Mother Coil after QC approval
	
	Args:
		temp_coil_name: Name of the Temporary Coil to convert
	
	Returns:
		dict with mother_coil name
	"""
	temp_coil = frappe.get_doc("Temporary Coil", temp_coil_name)
	
	# Check if already converted
	if temp_coil.converted_to_mother_coil:
		frappe.throw(_("This temporary coil has already been converted to Mother Coil: {0}").format(temp_coil.mother_coil))
	
	# Create Mother Coil
	mother_coil = frappe.new_doc("Mother Coil")
	
	# Copy all relevant fields
	mother_coil.temp_coil_id = temp_coil.temp_coil_id
	mother_coil.casting_plan = temp_coil.casting_plan
	mother_coil.casting_run = temp_coil.casting_run
	mother_coil.melting_batch = temp_coil.melting_batch
	mother_coil.caster = temp_coil.caster
	mother_coil.furnace = temp_coil.furnace
	mother_coil.alloy = temp_coil.alloy
	mother_coil.product_item = temp_coil.product_item
	mother_coil.temper = temp_coil.temper
	mother_coil.cast_date = temp_coil.cast_date
	
	# Copy dimensions
	mother_coil.actual_width_mm = temp_coil.width_mm
	mother_coil.actual_gauge_mm = temp_coil.gauge_mm
	mother_coil.actual_weight_mt = temp_coil.weight_mt
	
	# Get planned dimensions from casting plan
	if temp_coil.casting_plan:
		plan = frappe.get_doc("PPC Casting Plan", temp_coil.casting_plan)
		mother_coil.planned_width_mm = plan.planned_width_mm
		mother_coil.planned_gauge_mm = plan.planned_gauge_mm
		mother_coil.planned_weight_mt = plan.planned_weight_mt
	
	# Set QC status to Pending
	mother_coil.qc_status = "Pending"
	
	# Copy remarks
	mother_coil.remarks = temp_coil.remarks or ""
	if temp_coil.surface_observation:
		mother_coil.remarks += f"\n\nSurface Observation: {temp_coil.surface_observation}"
	
	# Save Mother Coil
	mother_coil.insert(ignore_permissions=True)
	
	# Update temporary coil
	temp_coil.converted_to_mother_coil = 1
	temp_coil.mother_coil = mother_coil.name
	temp_coil.conversion_date = now_datetime()
	temp_coil.temp_status = "Converted to Final"
	temp_coil.save(ignore_permissions=True)
	
	frappe.db.commit()
	
	return {
		"mother_coil": mother_coil.name,
		"message": f"Temporary Coil {temp_coil_name} converted to Mother Coil {mother_coil.name}"
	}
