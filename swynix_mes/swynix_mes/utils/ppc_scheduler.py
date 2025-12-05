# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

"""
PPC Scheduler Utilities

This module handles automatic rescheduling of future PPC Casting Plans
when actual timings deviate from planned timings.

When melting starts earlier or later than planned, the affected plan
and all subsequent not-yet-started plans on the same caster are shifted
to prevent overlaps, preserving their original planned durations.

Key Behavior:
- Each PPC Casting Plan stores its original planned_duration_minutes
- When melting starts (early or late), the plan is "re-anchored" to the actual start time
- The end time is recalculated as: start + planned_duration_minutes
- All future plans for the same caster are then shifted forward to remove any overlaps
- When casting completes, actual times are used and future plans are shifted again

Example:
  Plan A: 12:00–13:00, Plan B: 13:00–14:00 (duration 60min each)
  Melting for Plan B starts at 11:45.
  → Re-anchor Plan B to 11:45–12:45 (60min duration preserved)
  → Plan A at 12:00–13:00 now overlaps with Plan B
  → But Plan A started earlier, so we only shift plans AFTER Plan B's new end (12:45)
  → If Plan C is at 12:30–13:30, it gets pushed to 12:45–13:45
"""

import frappe
from frappe.utils import get_datetime
from datetime import timedelta

# Plans in these statuses are "locked" in time – we must never move them.
LOCKED_STATUSES = [
	"Melting",
	"Metal Ready",
	"Casting",
	"Coils Complete",
	"Not Produced",
]

# Plans in these statuses are free to move.
MOVABLE_STATUSES = [
	"Planned",
	"Released",
]


def shift_future_plans_for_caster(
	casting_plan_name: str,
	delta_seconds: float,
	from_time,
) -> None:
	"""
	Shift future PPC Casting Plans on the same caster by `delta_seconds`,
	starting from `from_time` (inclusive).

	Rules:
	- Only shifts plans with status in MOVABLE_STATUSES.
	- Never shifts plans that already have a NON-DRAFT Melting Batch.
	- Keeps duration of each plan intact (only start/end move).
	- Does NOT trim any plan.
	- We ignore overlap detection for now because our shift is uniform
	  and applied only to NOT-started plans after this point.

	Parameters:
	- casting_plan_name: name of the "anchor" plan causing the shift
	- delta_seconds: positive = move later, negative = move earlier
	- from_time: datetime or string; plans with start_datetime >= from_time shift
	"""

	if not delta_seconds:
		return

	cp = frappe.get_doc("PPC Casting Plan", casting_plan_name)
	caster = cp.caster
	if not caster:
		return

	from_dt = get_datetime(from_time)

	# Get future plans on the same caster, ordered by time
	future_plans = frappe.get_all(
		"PPC Casting Plan",
		filters={
			"caster": caster,
			"start_datetime": (">=", from_dt),
			"status": ("in", MOVABLE_STATUSES),
			"docstatus": ["<", 2],  # Not cancelled
		},
		fields=[
			"name",
			"start_datetime",
			"end_datetime",
			"status",
			"melting_batch",
		],
		order_by="start_datetime asc",
	)

	from datetime import timedelta

	for fp in future_plans:
		name = fp["name"]
		# Skip the current plan itself if the scheduler caller already updated it.
		# We'll let the caller decide whether to include/exclude it.
		if name == casting_plan_name:
			continue

		# If there's a linked melting batch that is NOT in Draft, do not move it.
		mb_name = fp.get("melting_batch")
		if mb_name:
			mb_status = frappe.db.get_value("Melting Batch", mb_name, "status")
			if mb_status and mb_status != "Draft":
				continue

		start = get_datetime(fp["start_datetime"])
		end = get_datetime(fp["end_datetime"])

		duration = end - start  # timedelta

		# Calculate new times using timedelta
		delta = timedelta(seconds=delta_seconds)
		new_start_dt = start + delta
		new_end_dt = new_start_dt + duration

		doc = frappe.get_doc("PPC Casting Plan", name)
		doc.start_datetime = new_start_dt
		doc.end_datetime = new_end_dt
		doc.save(ignore_permissions=True)

	frappe.db.commit()


# Legacy wrapper for backward compatibility
def adjust_future_plans_for_caster(plan):
	"""
	Legacy wrapper - called when actual_end deviates from planned_end.
	This is called after coils are complete.
	
	Now delegates to the new shift_future_plans_after function in ppc_casting_plan.py
	which properly handles durations and prevents overlaps.
	
	Args:
		plan: PPC Casting Plan document (must have actual_end and end_datetime)
	"""
	from swynix_mes.swynix_mes.doctype.ppc_casting_plan.ppc_casting_plan import shift_future_plans_after
	shift_future_plans_after(plan)


def shift_future_plans_after(current_plan):
	"""
	Wrapper to import and call the main implementation from ppc_casting_plan.py.
	
	Ensure no overlaps for this caster after current_plan by shifting
	future plans forward, preserving their planned_duration_minutes.
	
	Args:
		current_plan: PPCCastingPlan document that was just updated
	"""
	from swynix_mes.swynix_mes.doctype.ppc_casting_plan.ppc_casting_plan import shift_future_plans_after as _shift
	_shift(current_plan)
