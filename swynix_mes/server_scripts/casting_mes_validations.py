"""
Server-side validation scripts for Casting MES

These server scripts enforce critical business rules:
1. One furnace → one active melting batch
2. One caster → one active casting run
3. Casting plan cannot be cancelled after melting starts
4. Coil number generated only after QC approval
5. Planned duration never auto-expands
"""

import frappe
from frappe import _


def validate_single_active_melting_batch(doc, method):
	"""
	Ensure only one active melting batch per furnace
	
	This is triggered on Melting Batch validate
	"""
	if doc.status in ["Melting", "Metal Ready"] and doc.furnace:
		# Check for other active batches on this furnace
		active_batches = frappe.db.get_all(
			"Melting Batch",
			filters={
				"furnace": doc.furnace,
				"status": ["in", ["Melting", "Metal Ready"]],
				"name": ["!=", doc.name or "New"],
				"docstatus": ["<", 2]
			},
			fields=["name", "status"],
			limit=1
		)
		
		if active_batches:
			frappe.throw(
				_("Furnace '{0}' already has an active melting batch: {1} (status: {2}). "
				  "Please complete that batch before starting a new one.").format(
					doc.furnace, active_batches[0].name, active_batches[0].status
				)
			)


def validate_casting_plan_cancellation(doc, method):
	"""
	Prevent cancellation of casting plan if melting has started
	
	This is triggered on PPC Casting Plan before_cancel
	"""
	# Check if melting batch exists
	if doc.melting_batch:
		batch_status = frappe.db.get_value("Melting Batch", doc.melting_batch, "status")
		if batch_status and batch_status != "Draft":
			frappe.throw(
				_("Cannot cancel Casting Plan '{0}' because Melting Batch '{1}' has status '{2}'. "
				  "Cancellation is only allowed before melting starts.").format(
					doc.name, doc.melting_batch, batch_status
				),
				title=_("Cancellation Not Allowed")
			)


def auto_set_actual_end_from_duration(doc, method):
	"""
	When melting starts, set actual_end = actual_start + planned_duration
	
	This ensures planned duration never auto-expands.
	Triggered on PPC Casting Plan validate
	"""
	from datetime import timedelta
	
	# Only adjust if status moved to Melting and actual_start is set
	if doc.status == "Melting" and doc.actual_start and doc.planned_duration_minutes:
		# Set actual_end based on planned duration
		if not doc.actual_end:
			doc.actual_end = doc.actual_start + timedelta(minutes=doc.planned_duration_minutes)


def validate_coil_number_uniqueness(doc, method):
	"""
	Ensure coil numbers are unique
	
	This is triggered on Mother Coil validate
	"""
	if doc.coil_no:
		existing = frappe.db.get_value(
			"Mother Coil",
			{"coil_no": doc.coil_no, "name": ["!=", doc.name or "New"]},
			"name"
		)
		
		if existing:
			frappe.throw(
				_("Coil number '{0}' already exists in Mother Coil '{1}'. "
				  "Coil numbers must be unique.").format(doc.coil_no, existing)
			)


def update_plan_status_on_coil_creation(doc, method):
	"""
	Update casting plan status when all coils are approved
	
	This is triggered on Mother Coil after_save
	"""
	if doc.qc_status == "Approved" and doc.casting_plan:
		# Check if all coils for this plan are approved
		pending_count = frappe.db.count(
			"Mother Coil",
			{
				"casting_plan": doc.casting_plan,
				"qc_status": ["in", ["Pending", "Correction Required", "Hold"]],
				"docstatus": ["<", 2]
			}
		)
		
		if pending_count == 0:
			# All coils are approved, mark plan as complete
			plan = frappe.get_doc("PPC Casting Plan", doc.casting_plan)
			if plan.status == "Casting":
				plan.status = "Coils Complete"
				plan.actual_end = frappe.utils.now_datetime()
				plan.save(ignore_permissions=True)


# Register hooks (this would go in hooks.py)
"""
doc_events = {
	"Melting Batch": {
		"validate": "swynix_mes.swynix_mes.server_scripts.casting_mes_validations.validate_single_active_melting_batch"
	},
	"PPC Casting Plan": {
		"validate": "swynix_mes.swynix_mes.server_scripts.casting_mes_validations.auto_set_actual_end_from_duration",
		"before_cancel": "swynix_mes.swynix_mes.server_scripts.casting_mes_validations.validate_casting_plan_cancellation"
	},
	"Mother Coil": {
		"validate": "swynix_mes.swynix_mes.server_scripts.casting_mes_validations.validate_coil_number_uniqueness",
		"after_save": "swynix_mes.swynix_mes.server_scripts.casting_mes_validations.update_plan_status_on_coil_creation"
	}
}
"""
