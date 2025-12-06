# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, get_datetime


class CastingRun(Document):
	def validate(self):
		"""Validation logic for Casting Run"""
		self.validate_workstation_types()
		self.validate_single_active_run()
		self.calculate_totals()
	
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
	
	def validate_single_active_run(self):
		"""Ensure only one active casting run per caster"""
		if self.status == "Casting" and self.caster:
			# Check for other active runs on this caster
			active_runs = frappe.db.get_all(
				"Casting Run",
				filters={
					"caster": self.caster,
					"status": "Casting",
					"name": ["!=", self.name or "New"],
					"docstatus": ["<", 2]
				},
				fields=["name"],
				limit=1
			)
			
			if active_runs:
				frappe.throw(
					_("Caster '{0}' already has an active casting run: {1}. "
					  "Please complete or abort that run before starting a new one.").format(
						self.caster, active_runs[0].name
					)
				)
	
	def calculate_totals(self):
		"""Calculate totals from coils child table"""
		if not self.coils:
			self.total_coils = 0
			self.total_cast_weight = 0
			self.total_scrap_weight = 0
			return
		
		self.total_coils = len(self.coils)
		self.total_cast_weight = sum([coil.weight_mt or 0 for coil in self.coils])
		self.total_scrap_weight = sum([coil.scrap_weight_mt or 0 for coil in self.coils if coil.is_scrap])


@frappe.whitelist()
def start_casting_run(casting_plan, melting_batch, caster, furnace=None, operator=None):
	"""
	Start a new casting run
	
	Args:
		casting_plan: Casting Plan name
		melting_batch: Melting Batch name
		caster: Caster workstation
		furnace: Furnace workstation (optional)
		operator: Operator name (optional)
	
	Returns:
		dict with casting_run name
	"""
	# Validate inputs
	if not casting_plan:
		frappe.throw(_("Casting Plan is required"))
	if not melting_batch:
		frappe.throw(_("Melting Batch is required"))
	if not caster:
		frappe.throw(_("Caster is required"))
	
	# Check for active run on this caster
	active_run = frappe.db.get_value(
		"Casting Run",
		{"caster": caster, "status": "Casting", "docstatus": ["<", 2]},
		"name"
	)
	
	if active_run:
		frappe.throw(_("Caster '{0}' already has an active casting run: {1}").format(caster, active_run))
	
	# Get furnace from melting batch if not provided
	if not furnace:
		furnace = frappe.db.get_value("Melting Batch", melting_batch, "furnace")
	
	# Create new Casting Run
	casting_run = frappe.new_doc("Casting Run")
	casting_run.casting_plan = casting_plan
	casting_run.melting_batch = melting_batch
	casting_run.caster = caster
	casting_run.furnace = furnace
	casting_run.status = "Casting"
	casting_run.run_start_time = now_datetime()
	casting_run.run_date = now_datetime().date()
	
	casting_run.insert(ignore_permissions=True)
	
	# Update Casting Plan status
	plan = frappe.get_doc("PPC Casting Plan", casting_plan)
	plan.status = "Casting"
	plan.casting_start = casting_run.run_start_time
	if not plan.actual_start:
		plan.actual_start = casting_run.run_start_time
	plan.save(ignore_permissions=True)
	
	frappe.db.commit()
	
	return {
		"casting_run": casting_run.name,
		"message": f"Casting run {casting_run.name} started successfully"
	}


@frappe.whitelist()
def stop_casting_run(casting_run_name):
	"""
	Stop/Complete a casting run
	
	Args:
		casting_run_name: Name of the casting run
	
	Returns:
		dict with status
	"""
	casting_run = frappe.get_doc("Casting Run", casting_run_name)
	
	if casting_run.status != "Casting":
		frappe.throw(_("Casting run is not active"))
	
	casting_run.status = "Completed"
	casting_run.run_end_time = now_datetime()
	casting_run.save(ignore_permissions=True)
	
	# Update Casting Plan
	if casting_run.casting_plan:
		plan = frappe.get_doc("PPC Casting Plan", casting_run.casting_plan)
		plan.casting_end = casting_run.run_end_time
		plan.save(ignore_permissions=True)
	
	frappe.db.commit()
	
	return {
		"message": f"Casting run {casting_run_name} completed successfully"
	}


@frappe.whitelist()
def create_temporary_coil(casting_run_name, weight_mt, width_mm=None, gauge_mm=None, length_m=None, surface_observation=None, remarks=None):
	"""
	Create a temporary coil during casting
	
	Args:
		casting_run_name: Name of the casting run
		weight_mt: Weight in MT
		width_mm: Width in mm (optional)
		gauge_mm: Gauge in mm (optional)
		length_m: Length in meters (optional)
		surface_observation: Surface observations (optional)
		remarks: Remarks (optional)
	
	Returns:
		dict with temporary_coil name
	"""
	casting_run = frappe.get_doc("Casting Run", casting_run_name)
	
	# Create Temporary Coil
	temp_coil = frappe.new_doc("Temporary Coil")
	temp_coil.casting_run = casting_run.name
	temp_coil.casting_plan = casting_run.casting_plan
	temp_coil.melting_batch = casting_run.melting_batch
	temp_coil.caster = casting_run.caster
	temp_coil.furnace = casting_run.furnace
	
	# Get product details from casting plan
	if casting_run.casting_plan:
		plan = frappe.get_doc("PPC Casting Plan", casting_run.casting_plan)
		temp_coil.alloy = plan.alloy
		temp_coil.product_item = plan.product_item
		temp_coil.temper = plan.temper
	
	# Set dimensions
	temp_coil.weight_mt = weight_mt
	temp_coil.width_mm = width_mm
	temp_coil.gauge_mm = gauge_mm
	temp_coil.length_m = length_m
	temp_coil.surface_observation = surface_observation
	temp_coil.remarks = remarks
	temp_coil.temp_status = "Pending QC"
	
	temp_coil.insert(ignore_permissions=True)
	
	frappe.db.commit()
	
	return {
		"temporary_coil": temp_coil.name,
		"temp_coil_id": temp_coil.temp_coil_id,
		"message": f"Temporary coil {temp_coil.temp_coil_id} created successfully"
	}
