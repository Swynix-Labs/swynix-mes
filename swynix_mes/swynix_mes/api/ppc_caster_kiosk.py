# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, get_datetime
from frappe.utils.xlsxutils import make_xlsx
from datetime import timedelta

# Status lists for scheduling logic
SHIFTABLE_STATUSES = ["Draft", "Planned", "Released to Melting"]
LOCKED_STATUSES = ["In Process", "Completed"]


def shift_future_plans(caster, from_datetime, delta_seconds, exclude_name=None):
	"""
	Shift all *not-started* PPC Casting Plans for a caster that start on/after `from_datetime`
	forward by `delta_seconds`.

	- We only shift plans whose status is in SHIFTABLE_STATUSES.
	- We never touch In Process / Completed plans.
	"""
	if not caster or not delta_seconds:
		return

	delta = timedelta(seconds=int(delta_seconds))

	future_plans = frappe.get_all(
		"PPC Casting Plan",
		filters={
			"caster": caster,
			"status": ["in", SHIFTABLE_STATUSES],  # Only not-started plans
			"start_datetime": [">=", from_datetime],
		},
		fields=["name", "start_datetime", "end_datetime"],
		order_by="start_datetime asc",
	)

	for p in future_plans:
		if exclude_name and p.name == exclude_name:
			continue

		new_start = p.start_datetime + delta
		new_end = p.end_datetime + delta

		frappe.db.set_value(
			"PPC Casting Plan",
			p.name,
			{
				"start_datetime": new_start,
				"end_datetime": new_end,
			},
			update_modified=True,
		)

	frappe.db.commit()


def ensure_no_overlap_with_locked(caster, start_dt, end_dt, exclude_name=None):
	"""
	Ensure the given [start_dt, end_dt] range does NOT overlap any plan on this caster
	whose status is in LOCKED_STATUSES (In Process / Completed).

	Raise frappe.throw if overlap is found.
	"""
	if not caster or not (start_dt and end_dt):
		return

	overlap = frappe.get_all(
		"PPC Casting Plan",
		filters={
			"caster": caster,
			"status": ["in", LOCKED_STATUSES],
			"docstatus": ["<", 2],  # Not cancelled
		},
		fields=["name", "start_datetime", "end_datetime", "status"],
	)

	for p in overlap:
		if exclude_name and p.name == exclude_name:
			continue

		s = p.start_datetime
		e = p.end_datetime

		# (start < other_end) and (end > other_start) => overlap
		if start_dt < e and end_dt > s:
			frappe.throw(
				_("Cannot schedule in this time slot. It overlaps locked plan <b>{0}</b> "
				  "({1} → {2}) which is {3}.").format(
					p.name,
					frappe.format(p.start_datetime, {"fieldtype": "Datetime"}),
					frappe.format(p.end_datetime, {"fieldtype": "Datetime"}),
					p.status
				)
			)


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
def check_caster_plan_impact(caster, start_datetime):
	"""
	Return list of PPC Casting Plans on this caster that WILL be moved
	if we insert a new plan starting at `start_datetime`.
	
	Only considers plans with status in SHIFTABLE_STATUSES (not-started plans).
	"""
	if not (caster and start_datetime):
		return []

	start_dt = get_datetime(start_datetime)

	plans = frappe.get_all(
		"PPC Casting Plan",
		filters={
			"caster": caster,
			"status": ["in", SHIFTABLE_STATUSES],  # Only not-started plans
			"docstatus": ["<", 2],
			"start_datetime": [">=", start_dt],
		},
		fields=[
			"name",
			"plan_type",
			"start_datetime",
			"end_datetime",
			"product_item",
			"downtime_type",
			"status",
		],
		order_by="start_datetime asc",
	)

	return plans


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
			"customer",
			"planned_width_mm",
			"planned_gauge_mm",
			"planned_weight_mt",
			"final_width_mm",
			"final_gauge_mm",
			"final_weight_mt",
			"charge_mix_recipe",
			"status",
			"downtime_type",
			"downtime_reason",
			"remarks",
			"furnace"
		],
		order_by="start_datetime asc"
	)


@frappe.whitelist()
def get_plan_for_range(caster, start, end):
	"""
	Return PPC Casting Plans for a given caster between start and end (ISO datetimes).
	Used by FullCalendar to fetch events for the visible range.
	
	Uses overlap detection: events that start before view ends AND end after view starts.
	"""
	if not caster:
		return []

	plans = frappe.get_all(
		"PPC Casting Plan",
		filters={
			"caster": caster,
			# Overlap detection: event starts before view ends AND event ends after view starts
			"start_datetime": ["<", end],
			"end_datetime": [">", start],
			"status": ["!=", "Cancelled"],
			"docstatus": ["<", 2]  # Not cancelled
		},
		fields=[
			"name",
			"plan_type",
			"caster",
			"start_datetime",
			"end_datetime",
			"product_item",
			"alloy",
			"temper",
			"customer",
			"planned_width_mm",
			"planned_gauge_mm",
			"planned_weight_mt",
			"final_width_mm",
			"final_gauge_mm",
			"final_weight_mt",
			"charge_mix_recipe",
			"downtime_type",
			"status",
			"remarks",
		],
		order_by="start_datetime asc",
	)
	return plans


@frappe.whitelist()
def get_plans_for_range(caster, from_date, to_date):
	"""Get all PPC Casting Plans for a given caster within a date range (legacy)"""
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
			"customer",
			"planned_width_mm",
			"planned_gauge_mm",
			"planned_weight_mt",
			"final_width_mm",
			"final_gauge_mm",
			"final_weight_mt",
			"charge_mix_recipe",
			"status",
			"downtime_type",
			"downtime_reason",
			"remarks",
			"furnace"
		],
		order_by="start_datetime asc"
	)


@frappe.whitelist()
def create_plan(data):
	"""
	Create a PPC Casting Plan from kiosk dialog.
	- Only shifts not-started future plans (SHIFTABLE_STATUSES).
	- Never overlaps In Process / Completed plans.
	"""
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

	# Convert datetime strings to datetime objects
	start_dt = get_datetime(data.start_datetime)
	end_dt = get_datetime(data.end_datetime)

	if end_dt <= start_dt:
		frappe.throw(_("End Datetime must be after Start Datetime."))

	# 1) Ensure we don't overlap any locked (In Process / Completed) plan
	ensure_no_overlap_with_locked(data.caster, start_dt, end_dt, exclude_name=None)

	# 2) Compute duration and shift only not-started future plans
	duration_seconds = (end_dt - start_dt).total_seconds()
	shift_future_plans(
		caster=data.caster,
		from_datetime=start_dt,
		delta_seconds=duration_seconds,
		exclude_name=None,
	)

	# 3) Create the new plan
	doc = frappe.new_doc("PPC Casting Plan")

	# Common fields
	doc.caster = data.caster
	doc.plan_type = data.plan_type
	doc.start_datetime = start_dt
	doc.end_datetime = end_dt

	# derive plan_date from start_datetime if not provided
	if not doc.plan_date and doc.start_datetime:
		doc.plan_date = getdate(doc.start_datetime)

	doc.status = "Planned"

	# Optional common fields
	if data.furnace:
		doc.furnace = data.furnace
	if data.remarks:
		doc.remarks = data.remarks

	# Casting-specific fields
	if data.plan_type == "Casting":
		if data.product_item:
			doc.product_item = data.product_item
		if data.alloy:
			doc.alloy = data.alloy
		if data.temper:
			doc.temper = data.temper
		if data.customer:
			doc.customer = data.customer

		# Planned parameters
		if data.planned_width_mm:
			doc.planned_width_mm = data.planned_width_mm
		if data.planned_gauge_mm:
			doc.planned_gauge_mm = data.planned_gauge_mm
		if data.planned_weight_mt:
			doc.planned_weight_mt = data.planned_weight_mt

		# Final parameters (optional)
		if data.final_width_mm:
			doc.final_width_mm = data.final_width_mm
		if data.final_gauge_mm:
			doc.final_gauge_mm = data.final_gauge_mm
		if data.final_weight_mt:
			doc.final_weight_mt = data.final_weight_mt

		# Charge mix recipe
		if data.charge_mix_recipe:
			doc.charge_mix_recipe = data.charge_mix_recipe

	# Downtime-specific fields
	elif data.plan_type == "Downtime":
		if data.downtime_type:
			doc.downtime_type = data.downtime_type
		if data.downtime_reason:
			doc.downtime_reason = data.downtime_reason

	# Insert (validates via controller, but overlap check will now skip shiftable plans)
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


@frappe.whitelist()
def export_plans(caster, start, end, format="xlsx"):
	"""
	Export PPC Casting Plans for a given caster and date range.
	Supports both Excel (.xlsx) and CSV formats.
	Sets response to download the file directly.
	"""
	if not caster:
		frappe.throw(_("Caster is required for export."))

	plans = get_plan_for_range(caster, start, end)
	if not plans:
		frappe.throw(_("No plans found for the selected period."))

	# Prepare data: header + rows
	columns = [
		"Name",
		"Plan Type",
		"Caster",
		"Start Datetime",
		"End Datetime",
		"Product Item",
		"Alloy",
		"Temper",
		"Customer",
		"Planned Width (mm)",
		"Planned Gauge (mm)",
		"Planned Weight (MT)",
		"Final Width (mm)",
		"Final Gauge (mm)",
		"Final Weight (MT)",
		"Charge Mix Recipe",
		"Downtime Type",
		"Status",
		"Remarks",
	]
	data = [columns]

	for p in plans:
		row = [
			p.get("name"),
			p.get("plan_type"),
			p.get("caster") or caster,
			str(p.get("start_datetime") or ""),
			str(p.get("end_datetime") or ""),
			p.get("product_item"),
			p.get("alloy"),
			p.get("temper"),
			p.get("customer"),
			p.get("planned_width_mm"),
			p.get("planned_gauge_mm"),
			p.get("planned_weight_mt"),
			p.get("final_width_mm"),
			p.get("final_gauge_mm"),
			p.get("final_weight_mt"),
			p.get("charge_mix_recipe"),
			p.get("downtime_type"),
			p.get("status"),
			p.get("remarks"),
		]
		data.append(row)

	# Generate file based on format
	if format == "csv":
		import csv
		import io
		
		output = io.StringIO()
		writer = csv.writer(output)
		for row in data:
			# Convert None values to empty string for CSV
			writer.writerow([str(cell) if cell is not None else "" for cell in row])
		
		file_content = output.getvalue()
		file_name = f"PPC-Casting-Plan-{caster}-{start[:10]}-to-{end[:10]}.csv"
		
		frappe.response["filename"] = file_name
		frappe.response["filecontent"] = file_content
		frappe.response["type"] = "download"
	else:
		# Default to Excel
		xlsx_file = make_xlsx(data, "PPC Casting Plan")
		file_name = f"PPC-Casting-Plan-{caster}-{start[:10]}-to-{end[:10]}.xlsx"

		frappe.response["filename"] = file_name
		frappe.response["filecontent"] = xlsx_file.getvalue()
		frappe.response["type"] = "binary"


# Keep old function for backward compatibility
@frappe.whitelist()
def export_plan_excel(caster, start, end):
	"""Backward compatible Excel export."""
	return export_plans(caster, start, end, format="xlsx")
