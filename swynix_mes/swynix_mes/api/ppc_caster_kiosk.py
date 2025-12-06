# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, get_datetime, now_datetime
from frappe.utils.xlsxutils import make_xlsx
from datetime import timedelta

# Status lists for scheduling logic
# Plans that can still be shifted (not yet started)
SHIFTABLE_STATUSES = ["Planned", "Released"]
# Plans that are locked (already in production or completed)
LOCKED_STATUSES = ["Melting", "Metal Ready", "Casting", "Coils Complete", "Not Produced"]


def ensure_not_in_past(start_dt, label="plan"):
	"""
	Ensure the given start datetime is not before 'now'.
	Raises if violated.
	"""
	if not start_dt:
		return

	now = now_datetime()
	# Convert to comparable datetime
	start_dt = get_datetime(start_dt)

	if start_dt < now:
		frappe.throw(
			_("Cannot schedule this {0} in the past. "
			  "Start time {1} is earlier than current time {2}.").format(
				label,
				frappe.format(start_dt, {"fieldtype": "Datetime"}),
				frappe.format(now, {"fieldtype": "Datetime"})
			)
		)


def compute_shift_window_and_delta(caster, new_start, new_end):
	"""
	For a new plan [new_start, new_end] on a caster, compute:
	- shift_from: the earliest start_datetime of any SHIFTABLE plan >= new_start
	- delta_seconds: max(0, (new_end - shift_from).total_seconds())

	If there is no future shiftable plan, returns (None, 0) → no shift.

	Example:
		P1: 17:00–21:00
		New: 15:00–19:00
		first_future_start = 17:00 → delta = 19:00–17:00 = 2h
		New stays 15:00–19:00, P1 becomes 19:00–23:00.
	"""
	if not caster or not (new_start and new_end):
		return None, 0

	new_start = get_datetime(new_start)
	new_end = get_datetime(new_end)

	# Get earliest shiftable plan starting at/after new_start
	first_future = frappe.db.get_value(
		"PPC Casting Plan",
		{
			"casting_workstation": caster,
			"status": ["in", SHIFTABLE_STATUSES],
			"start_datetime": [">=", new_start],
		},
		"start_datetime",
		order_by="start_datetime asc",
	)

	if not first_future:
		return None, 0

	first_future = get_datetime(first_future)
	delta = (new_end - first_future).total_seconds()

	if delta <= 0:
		# New plan ends before or exactly at first_future_start
		# → no need to shift anything
		return None, 0

	return first_future, int(delta)


def shift_future_plans(caster, from_datetime, delta_seconds, exclude_name=None):
	"""
	Shift all *shiftable* PPC Casting Plans for a caster that start on/after `from_datetime`
	forward by `delta_seconds`. Duration is preserved.

	- We only shift plans whose status is in SHIFTABLE_STATUSES.
	- We never touch locked plans (Melting, Metal Ready, Casting, Coils Complete, Not Produced).
	- Both start_datetime and end_datetime are shifted by the same delta
	  to preserve the original plan duration.

	This is a "dumb shifter" - the smart logic lives in compute_shift_window_and_delta().
	"""
	if not caster or not delta_seconds or not from_datetime:
		return

	delta = timedelta(seconds=int(delta_seconds))

	future_plans = frappe.get_all(
		"PPC Casting Plan",
		filters={
			"casting_workstation": caster,
			"status": ["in", SHIFTABLE_STATUSES],  # Only not-started plans
			"start_datetime": [">=", from_datetime],
		},
		fields=["name", "start_datetime", "end_datetime"],
		order_by="start_datetime asc",
	)

	for p in future_plans:
		if exclude_name and p.name == exclude_name:
			continue

		# ✅ Preserve duration: shift both start and end by the same delta
		new_start = p.start_datetime + delta  # old_start + delta
		new_end = p.end_datetime + delta      # old_end + delta (NOT recalculated!)

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
	whose status is in LOCKED_STATUSES.

	Raise frappe.throw if overlap is found.
	"""
	if not caster or not (start_dt and end_dt):
		return

	overlap = frappe.get_all(
		"PPC Casting Plan",
		filters={
			"casting_workstation": caster,
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
def preview_plan_insertion(caster, start_datetime, end_datetime):
	"""
	Given a requested [start_datetime, end_datetime] for a new plan on a caster,
	suggest the actual slot the system will use and list the plans that will be shifted.

	Logic:
	- If the requested start overlaps an existing plan, snap the new start to
	  the END of the previous plan in sequence.
	- Duration is preserved = (requested_end - requested_start).
	- We only shift plans with status in SHIFTABLE_STATUSES and start >= suggested_start.
	- We never allow overlap with LOCKED_STATUSES; if that would happen, throw an error.
	"""
	if not (caster and start_datetime and end_datetime):
		frappe.throw(_("Caster, Start Datetime and End Datetime are required."))

	req_start = get_datetime(start_datetime)
	req_end = get_datetime(end_datetime)
	if req_end <= req_start:
		frappe.throw(_("End Datetime must be after Start Datetime."))

	# 🚫 No planning in the past
	ensure_not_in_past(req_start, label="plan")

	duration = req_end - req_start

	# Fetch all non-cancelled plans on this caster (exclude Not Produced)
	plans = frappe.get_all(
		"PPC Casting Plan",
		filters={
			"casting_workstation": caster,
			"status": ["not in", ["Not Produced"]],
			"docstatus": ["<", 2],
		},
		fields=["name", "start_datetime", "end_datetime", "status"],
		order_by="start_datetime asc",
	)

	suggested_start = req_start
	suggested_end = req_end

	# 1) Find if requested start lies INSIDE any existing plan
	overlapped_index = None
	for idx, p in enumerate(plans):
		if p.start_datetime <= req_start < p.end_datetime:
			overlapped_index = idx
			break

	if overlapped_index is not None:
		# New request falls inside some existing plan
		overlapped = plans[overlapped_index]
		now = now_datetime()

		# Check if the overlapped plan already started (in the past)
		if overlapped.start_datetime < now:
			# Plan already started - we CANNOT insert before it
			# Snap to the END of this running plan
			suggested_start = overlapped.end_datetime
			# If the end is also in the past (shouldn't happen for active plans),
			# snap to now
			if suggested_start < now:
				suggested_start = now
		else:
			# Plan hasn't started yet - we CAN shift it
			if overlapped_index > 0:
				# There IS a previous plan → snap to end of previous plan
				prev_plan = plans[overlapped_index - 1]
				suggested_start = prev_plan.end_datetime
				# But if that previous plan's end is in the past, use now
				if suggested_start < now:
					suggested_start = now
			else:
				# This is the FIRST plan and we are inside it.
				# We want the NEW PLAN to go BEFORE this existing one.
				suggested_start = overlapped.start_datetime

		suggested_end = suggested_start + duration

	# 🚫 Ensure suggested slot is not in the past (even after snapping)
	ensure_not_in_past(suggested_start, label="plan")

	# 2) Ensure we don't overlap LOCKED plans with the suggested slot
	ensure_no_overlap_with_locked(caster, suggested_start, suggested_end, exclude_name=None)

	# 3) Compute where shift will start & by how much (smart delta calculation)
	shift_from, delta_seconds = compute_shift_window_and_delta(
		caster=caster,
		new_start=suggested_start,
		new_end=suggested_end,
	)

	# 4) Compute affected plans = shiftable plans starting at/after shift_from
	if shift_from and delta_seconds > 0:
		affected = frappe.get_all(
			"PPC Casting Plan",
			filters={
				"casting_workstation": caster,
				"status": ["in", SHIFTABLE_STATUSES],
				"docstatus": ["<", 2],
				"start_datetime": [">=", shift_from],
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
	else:
		affected = []

	return {
		"requested_start": req_start,
		"requested_end": req_end,
		"suggested_start": suggested_start,
		"suggested_end": suggested_end,
		"shift_from": shift_from,
		"shift_delta_seconds": delta_seconds,
		"affected_plans": affected,
	}


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
			"casting_workstation": caster,
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
			"casting_workstation": caster,
			"plan_date": date,
			"status": ["not in", ["Not Produced"]],
			"docstatus": ["<", 2]  # Not cancelled
		},
		fields=[
			"name",
			"plan_type",
			"start_datetime",
			"end_datetime",
			"duration_minutes",
			"melting_start",
			"melting_end",
			"casting_start",
			"casting_end",
			"actual_start",
			"actual_end",
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
			"status",
			"downtime_type",
			"downtime_reason",
			"remarks",
			"furnace",
			"melting_batch",
			"mother_coil",
			"overlap_flag",
			"overlap_note"
		],
		order_by="start_datetime asc"
	)


@frappe.whitelist()
def get_plan_for_range(caster, start, end):
	"""
	Return PPC Casting Plans for a given caster between start and end (ISO datetimes).
	Used by FullCalendar to fetch events for the visible range.
	
	Uses overlap detection: events that start before view ends AND end after view starts.
	
	Returns fields including:
	- actual_start/actual_end: Real production times (used for calendar after completion)
	
	Note: planned_duration_minutes is an internal field used by scheduling logic,
	not exposed in this API as it's not needed for calendar display.
	"""
	if not caster:
		return []

	plans = frappe.get_all(
		"PPC Casting Plan",
		filters={
			"casting_workstation": caster,
			# Overlap detection: event starts before view ends AND event ends after view starts
			"start_datetime": ["<", end],
			"end_datetime": [">", start],
			"status": ["not in", ["Not Produced"]],
			"docstatus": ["<", 2]  # Not cancelled
		},
		fields=[
			"name",
			"plan_type",
			"casting_workstation",
			"furnace",
			"start_datetime",
			"end_datetime",
			"duration_minutes",
			"melting_start",
			"melting_end",
			"casting_start",
			"casting_end",
			"actual_start",
			"actual_end",
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
			"downtime_type",
			"status",
			"remarks",
			"melting_batch",
			"mother_coil",
			"overlap_flag",
			"overlap_note"
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
			"casting_workstation": caster,
			"plan_date": ["between", [from_date, to_date]],
			"status": ["not in", ["Not Produced"]],
			"docstatus": ["<", 2]
		},
		fields=[
			"name",
			"plan_type",
			"plan_date",
			"start_datetime",
			"end_datetime",
			"duration_minutes",
			"melting_start",
			"melting_end",
			"casting_start",
			"casting_end",
			"actual_start",
			"actual_end",
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
			"status",
			"downtime_type",
			"downtime_reason",
			"remarks",
			"furnace",
			"melting_batch",
			"mother_coil",
			"overlap_flag",
			"overlap_note"
		],
		order_by="start_datetime asc"
	)


@frappe.whitelist()
def create_plan(data):
	"""
	Create a PPC Casting Plan from kiosk dialog.
	- Only shifts not-started future plans (SHIFTABLE_STATUSES).
	- Never overlaps locked plans.
	"""
	if isinstance(data, str):
		import json
		data = json.loads(data)

	data = frappe._dict(data)

	# Required field validation
	if not data.casting_workstation:
		frappe.throw(_("Caster is required"))
	if not data.plan_type:
		frappe.throw(_("Plan Type is required"))
	if not data.start_datetime:
		frappe.throw(_("Start Datetime is required"))
	if not data.end_datetime:
		frappe.throw(_("End Datetime is required"))

	# Convert datetime strings to datetime objects
	# (These should be the SUGGESTED times from preview_plan_insertion)
	start_dt = get_datetime(data.start_datetime)
	end_dt = get_datetime(data.end_datetime)

	if not (start_dt and end_dt):
		frappe.throw(_("Start Datetime and End Datetime are required."))
	if end_dt <= start_dt:
		frappe.throw(_("End Datetime must be after Start Datetime."))

	# 🚫 No planning in the past
	ensure_not_in_past(start_dt, label="plan")

	# 1) Ensure we don't overlap any locked plan
	ensure_no_overlap_with_locked(data.casting_workstation, start_dt, end_dt, exclude_name=None)

	# 2) Compute smart shift window & amount
	# This finds the first shiftable plan >= start_dt and computes
	# delta = max(0, end_dt - first_plan_start)
	shift_from, delta_seconds = compute_shift_window_and_delta(
		caster=data.casting_workstation,
		new_start=start_dt,
		new_end=end_dt,
	)

	# 3) 🔁 Shift existing future plans only if needed
	if shift_from and delta_seconds > 0:
		shift_future_plans(
			caster=data.casting_workstation,
			from_datetime=shift_from,
			delta_seconds=delta_seconds,
			exclude_name=None,
		)

	# 4) 🆕 Now insert the new plan at start_dt–end_dt
	doc = frappe.new_doc("PPC Casting Plan")

	# Common fields
	doc.casting_workstation = data.casting_workstation
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
	if not plan_name:
		frappe.throw(_("Plan name is required"))

	doc = frappe.get_doc("PPC Casting Plan", plan_name)

	# Check if can be modified
	if doc.docstatus == 2:
		frappe.throw(_("Cannot modify cancelled plan"))

	if doc.status in LOCKED_STATUSES:
		frappe.throw(_("Cannot modify plan in status: {0}").format(doc.status))

	# Validate new times
	new_start_dt = get_datetime(start_datetime)
	new_end_dt = get_datetime(end_datetime)

	if new_end_dt <= new_start_dt:
		frappe.throw(_("New End Datetime must be after New Start Datetime."))

	# 🚫 Don't allow dragging plans into the past
	ensure_not_in_past(new_start_dt, label="plan")

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
		doc.status = "Not Produced"
		doc.save()

	return {"message": "Plan cancelled successfully"}


@frappe.whitelist()
def release_plan(plan_name):
	"""Release a Planned casting plan for melting."""
	if not plan_name:
		frappe.throw(_("Plan name is required"))

	doc = frappe.get_doc("PPC Casting Plan", plan_name)

	if doc.status != "Planned":
		frappe.throw(_("Only Planned plans can be released. Current status: {0}").format(doc.status))

	doc.db_set("status", "Released", update_modified=True)
	
	return {"message": "Plan released for melting", "status": "Released"}


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
		"Casting",
		"Status",
		"Start Datetime",
		"End Datetime",
		"Actual Start",
		"Actual End",
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
		"Charge Mix Ratio",
		"Downtime Type",
		"Melting Batch",
		"Mother Coil",
		"Remarks",
	]
	data = [columns]

	for p in plans:
		row = [
			p.get("name"),
			p.get("plan_type"),
			p.get("casting_workstation") or caster,
			p.get("status"),
			str(p.get("start_datetime") or ""),
			str(p.get("end_datetime") or ""),
			str(p.get("actual_start") or ""),
			str(p.get("actual_end") or ""),
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
			p.get("downtime_type"),
			p.get("melting_batch"),
			p.get("mother_coil"),
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
