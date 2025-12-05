# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime


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
		
		# Auto-populate fields from Casting Plan if linked
		if self.casting_plan and not self.alloy:
			self.populate_from_casting_plan()

	def validate(self):
		"""Validate coil data."""
		self.validate_mother_coil()
		self.validate_dimensions()
		self.validate_timing()

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

	def validate_timing(self):
		"""Validate coil timing fields."""
		if self.coil_start_time and self.coil_end_time:
			if get_datetime(self.coil_start_time) > get_datetime(self.coil_end_time):
				frappe.throw(_("Coil Start Time cannot be after Coil End Time."))

	def populate_from_casting_plan(self):
		"""Populate coil fields from linked Casting Plan."""
		if not self.casting_plan:
			return
		
		try:
			plan = frappe.get_doc("PPC Casting Plan", self.casting_plan)
			
			updates = {}
			if not self.alloy and plan.alloy:
				updates["alloy"] = plan.alloy
			if not self.temper and plan.temper:
				updates["temper"] = plan.temper
			if not self.product_item and plan.product_item:
				updates["product_item"] = plan.product_item
			if not self.width_mm and plan.planned_width_mm:
				updates["width_mm"] = plan.planned_width_mm
			if not self.thickness_mm and plan.planned_gauge_mm:
				updates["thickness_mm"] = plan.planned_gauge_mm
			if not self.caster and plan.caster:
				updates["caster"] = plan.caster
			if not self.furnace and plan.furnace:
				updates["furnace"] = plan.furnace
			if not self.melting_batch and plan.melting_batch:
				updates["melting_batch"] = plan.melting_batch
			
			if updates:
				for field, value in updates.items():
					self.db_set(field, value, update_modified=False)
		except Exception:
			pass  # Don't block on errors

	def before_submit(self):
		"""Actions before submitting the coil."""
		# Ensure coil_id is set
		if not self.coil_id:
			self.coil_id = self.name
		
		# Set default timing if not set
		if not self.coil_end_time:
			self.coil_end_time = now_datetime()
		if not self.coil_start_time:
			self.coil_start_time = self.coil_end_time

	def on_submit(self):
		"""
		Actions when coil is submitted.
		
		Updates the linked PPC Casting Plan with:
		- casting_start: earliest coil_start_time for this plan
		- casting_end: latest coil_end_time for this plan
		- actual_end: same as casting_end
		- status: Casting or Coils Complete
		
		Then triggers rescheduling of future plans if actual_end deviates from planned_end.
		"""
		if not self.casting_plan:
			return
		
		# Only process Mother coils for casting plan updates
		if self.coil_role != "Mother":
			return
		
		self.sync_to_casting_plan()

	def sync_to_casting_plan(self):
		"""Sync coil completion data back to PPC Casting Plan."""
		if not self.casting_plan:
			return
		
		try:
			cp = frappe.get_doc("PPC Casting Plan", self.casting_plan)
			
			# Don't update cancelled plans
			if cp.docstatus == 2:
				return
			
			# Remember old planned_end for delta calculation
			old_planned_end = get_datetime(cp.end_datetime) if cp.end_datetime else None
			
			updates = {}
			
			# 1. Set casting_start if empty or if this coil started earlier
			coil_start = get_datetime(self.coil_start_time) if self.coil_start_time else None
			if coil_start:
				if not cp.casting_start:
					updates["casting_start"] = coil_start
				elif coil_start < get_datetime(cp.casting_start):
					updates["casting_start"] = coil_start
			
			# 2. Always move casting_end to the latest coil_end_time
			coil_end = get_datetime(self.coil_end_time) if self.coil_end_time else None
			if coil_end:
				if not cp.casting_end:
					updates["casting_end"] = coil_end
					updates["actual_end"] = coil_end
				elif coil_end > get_datetime(cp.casting_end):
					updates["casting_end"] = coil_end
					updates["actual_end"] = coil_end
			
			# 3. Update status to Coils Complete
			if cp.status in ["Planned", "Released", "Melting", "Metal Ready", "Casting"]:
				updates["status"] = "Coils Complete"
			
			# 4. Link the mother coil if not already linked
			if not cp.mother_coil:
				updates["mother_coil"] = self.name
			
			# Apply updates
			if updates:
				for field, value in updates.items():
					cp.db_set(field, value, update_modified=True)
				
				# Reload the plan with updated values
				cp.reload()
				
				# 5. Trigger rescheduling of future plans
				# This happens when actual_end differs from planned_end
				if cp.actual_end and old_planned_end:
					actual_end = get_datetime(cp.actual_end)
					delta_seconds = (actual_end - old_planned_end).total_seconds()
					
					if delta_seconds != 0:
						# Update planned_end to match actual_end
						cp.db_set("end_datetime", actual_end, update_modified=True)
						
						# Shift future plans
						from swynix_mes.swynix_mes.utils.ppc_scheduler import shift_future_plans_for_caster
						shift_future_plans_for_caster(
							casting_plan_name=cp.name,
							delta_seconds=delta_seconds,
							from_time=old_planned_end
						)
			
		except Exception as e:
			frappe.log_error(
				title="Coil → Casting Plan Sync Error",
				message=f"Error syncing coil {self.name} to plan {self.casting_plan}: {str(e)}"
			)

	def on_cancel(self):
		"""Actions when coil is cancelled."""
		self.coil_status = "Cancelled"


@frappe.whitelist()
def create_mother_coil_from_plan(casting_plan, weight_mt=None, width_mm=None, thickness_mm=None,
                                   coil_start_time=None, coil_end_time=None):
	"""
	Create a Mother Coil from a PPC Casting Plan.
	
	Args:
		casting_plan: Name of the PPC Casting Plan
		weight_mt: Weight in MT (optional, defaults from plan)
		width_mm: Width in mm (optional, defaults from plan)
		thickness_mm: Thickness in mm (optional, defaults from plan)
		coil_start_time: When casting started (optional, defaults to now)
		coil_end_time: When casting ended (optional, defaults to now)
	
	Returns:
		dict with coil details
	"""
	if not casting_plan:
		frappe.throw(_("Casting Plan is required."))
	
	plan = frappe.get_doc("PPC Casting Plan", casting_plan)
	
	# Create the coil
	coil = frappe.new_doc("Coil")
	coil.coil_role = "Mother"
	coil.casting_plan = casting_plan
	coil.melting_batch = plan.melting_batch
	coil.caster = plan.caster
	coil.furnace = plan.furnace
	coil.alloy = plan.alloy
	coil.temper = plan.temper
	coil.product_item = plan.product_item
	
	# Set dimensions - use provided values or defaults from plan
	coil.width_mm = float(width_mm) if width_mm else plan.planned_width_mm
	coil.thickness_mm = float(thickness_mm) if thickness_mm else plan.planned_gauge_mm
	coil.weight_mt = float(weight_mt) if weight_mt else plan.planned_weight_mt
	
	# Set timing
	coil.coil_start_time = coil_start_time or now_datetime()
	coil.coil_end_time = coil_end_time or now_datetime()
	coil.cast_datetime = coil.coil_end_time
	
	# Set status
	coil.coil_status = "Cast"
	coil.current_stage = "Casting"
	
	# Set heat number from melting batch if available
	if plan.melting_batch:
		coil.heat_number = plan.melting_batch
	
	coil.insert()
	
	return {
		"name": coil.name,
		"coil_id": coil.coil_id or coil.name,
		"casting_plan": casting_plan,
		"alloy": coil.alloy,
		"temper": coil.temper,
		"width_mm": coil.width_mm,
		"thickness_mm": coil.thickness_mm,
		"weight_mt": coil.weight_mt
	}


@frappe.whitelist()
def get_coils_for_plan(casting_plan):
	"""
	Get all coils for a PPC Casting Plan.
	
	Args:
		casting_plan: Name of the PPC Casting Plan
	
	Returns:
		list of coil records
	"""
	if not casting_plan:
		return []
	
	return frappe.get_all(
		"Coil",
		filters={
			"casting_plan": casting_plan,
			"docstatus": ["<", 2]  # Not cancelled
		},
		fields=[
			"name", "coil_id", "coil_role", "coil_status",
			"alloy", "temper", "width_mm", "thickness_mm", "weight_mt",
			"coil_start_time", "coil_end_time", "cast_datetime",
			"qc_status", "qc_grade", "current_stage"
		],
		order_by="coil_start_time asc"
	)
