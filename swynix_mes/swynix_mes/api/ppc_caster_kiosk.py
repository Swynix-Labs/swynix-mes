# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe import _


@frappe.whitelist()
def get_casters():
	"""Get all Workstations with workstation_type = 'Casting'"""
	return frappe.get_all(
		"Workstation",
		filters={"workstation_type": "Casting"},
		fields=["name"],
		order_by="name asc"
	)


@frappe.whitelist()
def get_furnaces():
	"""Get all Workstations with workstation_type = 'Foundry'"""
	return frappe.get_all(
		"Workstation",
		filters={"workstation_type": "Foundry"},
		fields=["name"],
		order_by="name asc"
	)


@frappe.whitelist()
def get_plans_for_day(caster, date):
	"""Get all PPC Casting Plans for a given caster and date"""
	if not caster or not date:
		return []

	return frappe.get_all(
		"PPC Casting Plan",
		filters={
			"caster": caster,
			"plan_date": date,
			"status": ["!=", "Cancelled"],
			"docstatus": ["<", 2]  # Not cancelled
		},
		fields=[
			"name",
			"plan_type",
			"start_datetime",
			"end_datetime",
			"duration_minutes",
			"product_item",
			"alloy",
			"temper",
			"width_mm",
			"final_gauge_mm",
			"planned_weight_mt",
			"customer",
			"status",
			"downtime_type",
			"downtime_reason",
			"furnace"
		],
		order_by="start_datetime asc"
	)


@frappe.whitelist()
def get_plans_for_range(caster, from_date, to_date):
	"""Get all PPC Casting Plans for a given caster within a date range"""
	if not caster or not from_date or not to_date:
		return []

	return frappe.get_all(
		"PPC Casting Plan",
		filters={
			"caster": caster,
			"plan_date": ["between", [from_date, to_date]],
			"status": ["!=", "Cancelled"],
			"docstatus": ["<", 2]
		},
		fields=[
			"name",
			"plan_type",
			"plan_date",
			"start_datetime",
			"end_datetime",
			"duration_minutes",
			"product_item",
			"alloy",
			"temper",
			"width_mm",
			"final_gauge_mm",
			"planned_weight_mt",
			"customer",
			"status",
			"downtime_type",
			"downtime_reason",
			"furnace"
		],
		order_by="start_datetime asc"
	)


@frappe.whitelist()
def create_plan(data):
	"""Create a new PPC Casting Plan"""
	from frappe.utils import get_datetime

	if isinstance(data, str):
		import json
		data = json.loads(data)

	data = frappe._dict(data)

	# Required field validation
	if not data.caster:
		frappe.throw(_("Caster is required"))
	if not data.plan_type:
		frappe.throw(_("Plan Type is required"))
	if not data.start_datetime:
		frappe.throw(_("Start Datetime is required"))
	if not data.end_datetime:
		frappe.throw(_("End Datetime is required"))

	# Create document
	doc = frappe.new_doc("PPC Casting Plan")

	# Common fields
	doc.caster = data.caster
	doc.plan_type = data.plan_type
	# Convert datetime strings to datetime objects
	doc.start_datetime = get_datetime(data.start_datetime)
	doc.end_datetime = get_datetime(data.end_datetime)
	doc.status = "Planned"

	if data.furnace:
		doc.furnace = data.furnace

	if data.planned_weight_mt:
		doc.planned_weight_mt = data.planned_weight_mt

	# Casting-specific fields
	if data.plan_type == "Casting":
		if data.product_item:
			doc.product_item = data.product_item
		if data.alloy:
			doc.alloy = data.alloy
		if data.temper:
			doc.temper = data.temper
		if data.width_mm:
			doc.width_mm = data.width_mm
		if data.final_gauge_mm:
			doc.final_gauge_mm = data.final_gauge_mm

	# Downtime-specific fields
	elif data.plan_type == "Downtime":
		if data.downtime_type:
			doc.downtime_type = data.downtime_type
		if data.downtime_reason:
			doc.downtime_reason = data.downtime_reason

	# Insert (validates via controller)
	doc.insert()

	# Submit the document
	doc.submit()

	return doc.name


@frappe.whitelist()
def update_plan_times(plan_name, start_datetime, end_datetime):
	"""Update start and end times for a plan (for drag-drop functionality)"""
	from frappe.utils import get_datetime

	if not plan_name:
		frappe.throw(_("Plan name is required"))

	doc = frappe.get_doc("PPC Casting Plan", plan_name)

	# Check if can be modified
	if doc.docstatus == 2:
		frappe.throw(_("Cannot modify cancelled plan"))

	if doc.status in ["Completed", "In Process"]:
		frappe.throw(_("Cannot modify plan in status: {0}").format(doc.status))

	# If submitted, need to amend
	if doc.docstatus == 1:
		# Cancel and amend
		doc.cancel()
		doc = frappe.copy_doc(doc)
		doc.amended_from = plan_name
		doc.start_datetime = start_datetime
		doc.end_datetime = end_datetime
		doc.insert()
		doc.submit()
	else:
		# Just update
		doc.start_datetime = start_datetime
		doc.end_datetime = end_datetime
		doc.save()

	return doc.name


@frappe.whitelist()
def cancel_plan(plan_name):
	"""Cancel a PPC Casting Plan"""
	if not plan_name:
		frappe.throw(_("Plan name is required"))

	doc = frappe.get_doc("PPC Casting Plan", plan_name)

	if doc.docstatus == 2:
		frappe.throw(_("Plan is already cancelled"))

	if doc.docstatus == 1:
		doc.cancel()
	else:
		doc.status = "Cancelled"
		doc.save()

	return {"message": "Plan cancelled successfully"}

