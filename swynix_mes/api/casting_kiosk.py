"""
API endpoints for Casting Kiosk
"""

import frappe
from frappe import _
from frappe.utils import nowdate, getdate, now_datetime


@frappe.whitelist()
def get_casters():
	"""Get all casters (workstations of type Caster)"""
	casters = frappe.get_all(
		"Workstation",
		filters={"workstation_type": "Caster"},
		fields=["name", "workstation_name", "caster_no"],
		order_by="caster_no"
	)
	return casters


@frappe.whitelist()
def get_casting_plans(caster, date=None):
	"""
	Get casting plans for a specific caster and date
	
	Args:
		caster: Workstation name (caster)
		date: Date to filter (defaults to today)
	
	Returns:
		List of casting plans with details
	"""
	if not date:
		date = nowdate()
	
	plans = frappe.get_all(
		"PPC Casting Plan",
		filters={
			"caster": caster,
			"plan_date": date,
			"status": ["not in", ["Cancelled"]],
			"docstatus": ["<", 2]
		},
		fields=[
			"name", "cast_no", "status", "plan_type",
			"caster", "furnace",
			"alloy", "product_item", "temper",
			"planned_width_mm", "planned_gauge_mm", "planned_weight_mt",
			"final_width_mm", "final_gauge_mm", "final_weight_mt",
			"start_datetime", "end_datetime",
			"melting_batch", "customer",
			"actual_start", "actual_end"
		],
		order_by="start_datetime asc"
	)
	
	# Get actual cast weight for each plan
	for plan in plans:
		# Calculate actual weight from temporary coils
		actual_weight = frappe.db.sql("""
			SELECT COALESCE(SUM(weight_mt), 0) as total_weight
			FROM `tabTemporary Coil`
			WHERE casting_plan = %s AND docstatus < 2
		""", (plan.name,), as_dict=True)
		
		plan["actual_weight_mt"] = actual_weight[0].total_weight if actual_weight else 0
		
		# Get active casting run
		active_run = frappe.db.get_value(
			"Casting Run",
			{"casting_plan": plan.name, "status": ["in", ["Planned", "Casting"]], "docstatus": ["<", 2]},
			["name", "status", "run_start_time", "run_end_time"],
			as_dict=True
		)
		plan["active_run"] = active_run
		
		# Get temp coil count
		temp_coil_count = frappe.db.count(
			"Temporary Coil",
			{"casting_plan": plan.name, "docstatus": ["<", 2]}
		)
		plan["temp_coil_count"] = temp_coil_count
	
	return plans


@frappe.whitelist()
def start_casting(casting_plan, caster):
	"""
	Start casting for a plan
	
	Args:
		casting_plan: Casting Plan name
		caster: Caster workstation
	
	Returns:
		dict with casting_run name and status
	"""
	from swynix_mes.swynix_mes.doctype.casting_run.casting_run import start_casting_run
	
	# Get plan details
	plan = frappe.get_doc("PPC Casting Plan", casting_plan)
	
	if plan.status not in ["Metal Ready", "Planned"]:
		frappe.throw(_("Casting can only be started when status is 'Metal Ready' or 'Planned'"))
	
	# Start casting run
	result = start_casting_run(
		casting_plan=casting_plan,
		melting_batch=plan.melting_batch,
		caster=caster,
		furnace=plan.furnace
	)
	
	return result


@frappe.whitelist()
def stop_casting(casting_run):
	"""
	Stop/Complete a casting run
	
	Args:
		casting_run: Casting Run name
	
	Returns:
		dict with status
	"""
	from swynix_mes.swynix_mes.doctype.casting_run.casting_run import stop_casting_run
	
	return stop_casting_run(casting_run)


@frappe.whitelist()
def create_temp_coil(casting_run, weight_mt, width_mm=None, gauge_mm=None, length_m=None, surface_observation=None, remarks=None):
	"""
	Create a temporary coil during casting
	
	Args:
		casting_run: Casting Run name
		weight_mt: Weight in MT
		width_mm: Width in mm
		gauge_mm: Gauge in mm
		length_m: Length in meters
		surface_observation: Surface observations
		remarks: Remarks
	
	Returns:
		dict with temporary_coil name
	"""
	from swynix_mes.swynix_mes.doctype.casting_run.casting_run import create_temporary_coil
	
	return create_temporary_coil(
		casting_run_name=casting_run,
		weight_mt=weight_mt,
		width_mm=width_mm,
		gauge_mm=gauge_mm,
		length_m=length_m,
		surface_observation=surface_observation,
		remarks=remarks
	)


@frappe.whitelist()
def get_plan_details(plan_name):
	"""Get detailed information about a specific casting plan"""
	plan = frappe.get_doc("PPC Casting Plan", plan_name)
	
	# Get melting batch details
	melting_batch = None
	if plan.melting_batch:
		melting_batch = frappe.get_doc("Melting Batch", plan.melting_batch)
	
	# Get temporary coils
	temp_coils = frappe.get_all(
		"Temporary Coil",
		filters={"casting_plan": plan_name, "docstatus": ["<", 2]},
		fields=["name", "temp_coil_id", "weight_mt", "width_mm", "gauge_mm", "temp_status", "cast_date"],
		order_by="creation desc"
	)
	
	# Get active casting run
	active_run = frappe.db.get_value(
		"Casting Run",
		{"casting_plan": plan_name, "status": ["in", ["Planned", "Casting"]], "docstatus": ["<", 2]},
		["name", "status", "run_start_time"],
		as_dict=True
	)
	
	return {
		"plan": plan.as_dict(),
		"melting_batch": melting_batch.as_dict() if melting_batch else None,
		"temp_coils": temp_coils,
		"active_run": active_run,
		"total_weight": sum([c.weight_mt or 0 for c in temp_coils])
	}


@frappe.whitelist()
def approve_coil_and_generate_number(mother_coil_name):
	"""
	Approve a mother coil and generate final coil number
	
	Args:
		mother_coil_name: Name of the Mother Coil
	
	Returns:
		dict with coil_no
	"""
	mother_coil = frappe.get_doc("Mother Coil", mother_coil_name)
	
	if mother_coil.qc_status != "Pending":
		frappe.throw(_("Cannot approve coil. Current QC status: {0}").format(mother_coil.qc_status))
	
	mother_coil.qc_status = "Approved"
	mother_coil.save(ignore_permissions=True)
	
	frappe.db.commit()
	
	return {
		"coil_no": mother_coil.coil_no,
		"message": f"Coil approved. Coil number: {mother_coil.coil_no}"
	}


@frappe.whitelist()
def convert_temp_to_final(temp_coil_name):
	"""
	Convert temporary coil to mother coil
	
	Args:
		temp_coil_name: Name of the Temporary Coil
	
	Returns:
		dict with mother_coil name
	"""
	from swynix_mes.swynix_mes.doctype.mother_coil.mother_coil import convert_temp_to_mother
	
	return convert_temp_to_mother(temp_coil_name)
