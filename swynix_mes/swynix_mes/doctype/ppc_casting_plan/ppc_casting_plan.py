# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

from datetime import timedelta

import frappe
from frappe import _
from frappe.model.document import Document

# Status lists for scheduling logic
# Plans that can still be shifted (not yet started)
SHIFTABLE_STATUSES = ["Planned"]
# Plans that are locked (already in production or completed)
LOCKED_STATUSES = ["Melting", "Metal Ready", "Casting", "Coils Complete"]


class PPCCastingPlan(Document):
	def validate(self):
		self.validate_required_fields()
		self.validate_datetime_range()
		self.calculate_duration()
		self.set_planned_duration()  # Store original planned duration for rescheduling
		self.auto_set_plan_date()
		self.auto_set_defaults()

		# Type-specific validations
		if self.plan_type == "Casting":
			self.validate_casting_fields()
		elif self.plan_type == "Downtime":
			self.validate_downtime_fields()

		# Overlap check (Casting + Downtime both block caster)
		self.check_caster_overlap()

		# Validate workstation types
		self.validate_workstations()

	def validate_required_fields(self):
		"""Validate required common fields"""
		required_fields = [
			("plan_type", "Plan Type"),
			("caster", "Caster"),
			("start_datetime", "Start Datetime"),
			("end_datetime", "End Datetime")
		]

		for field, label in required_fields:
			if not getattr(self, field, None):
				frappe.throw(_("{0} is required.").format(label))

	def validate_datetime_range(self):
		"""Start must be before End"""
		if self.start_datetime and self.end_datetime:
			if self.start_datetime >= self.end_datetime:
				frappe.throw(_("End Datetime must be greater than Start Datetime."))

	def calculate_duration(self):
		"""Auto-calculate duration in minutes"""
		if self.start_datetime and self.end_datetime:
			delta = self.end_datetime - self.start_datetime
			self.duration_minutes = int(delta.total_seconds() // 60)

			if self.duration_minutes <= 0:
				frappe.throw(_("Duration must be positive."))

	def set_planned_duration(self):
		"""
		Store original planned duration in minutes.
		
		This is used for rescheduling when melting starts early/late.
		The planned_duration_minutes field preserves the originally intended
		duration even when start/end times are shifted.
		
		Rules:
		- Only set if both start and end datetimes exist
		- Only set if the plan hasn't started yet (status in Planned, Released)
		- Once melting starts, the planned duration is locked
		"""
		from frappe.utils import get_datetime
		
		# Only update planned duration for plans that haven't started yet
		if self.status not in SHIFTABLE_STATUSES:
			return
		
		if self.start_datetime and self.end_datetime:
			start = get_datetime(self.start_datetime)
			end = get_datetime(self.end_datetime)
			delta_min = (end - start).total_seconds() / 60.0
			
			# Store only if positive
			if delta_min > 0:
				self.planned_duration_minutes = delta_min

	def auto_set_plan_date(self):
		"""Auto set plan_date from start_datetime if missing"""
		if not self.plan_date and self.start_datetime:
			self.plan_date = self.start_datetime.date()

	def auto_set_defaults(self):
		"""Set default values"""
		# Default status
		if not self.status:
			self.status = "Planned"

		# Auto cast_no if empty - use name after insert
		if not self.cast_no and self.name:
			self.cast_no = self.name

	def before_insert(self):
		"""Set cast_no before first save if empty"""
		if not self.cast_no:
			# Will be set to name after insert in after_insert
			pass

	def after_insert(self):
		"""Set cast_no to name if still empty"""
		if not self.cast_no:
			self.db_set("cast_no", self.name)
			self.cast_no = self.name

	def validate_casting_fields(self):
		"""Validate fields specific to Casting plan type"""
		# Required fields for Casting
		required_casting_fields = [
			("product_item", "Product Item"),
			("alloy", "Alloy"),
			("temper", "Temper"),
			("planned_width_mm", "Cast Width (mm)"),
			("planned_gauge_mm", "Final Gauge (mm)"),
			("planned_weight_mt", "Cast Weight (MT)"),
		]

		for field, label in required_casting_fields:
			if not getattr(self, field, None):
				frappe.throw(_("{0} is mandatory for PPC Casting Plan.").format(label))

		# Validate product_item belongs to Product item group
		if self.product_item:
			prod_item_group = frappe.db.get_value("Item", self.product_item, "item_group")
			if prod_item_group != "Product":
				frappe.throw(
					_("Selected Product Item '{0}' is under Item Group '{1}'. "
					  "Only Items under Item Group 'Product' can be selected as Product Item.").format(
						self.product_item, prod_item_group or "Unknown"
					)
				)

		# Positive number validations for planned parameters
		if self.planned_width_mm and self.planned_width_mm <= 0:
			frappe.throw(_("Planned Width (mm) must be greater than 0."))

		if self.planned_gauge_mm and self.planned_gauge_mm <= 0:
			frappe.throw(_("Planned Gauge (mm) must be greater than 0."))

		# Positive number validations for final parameters
		if self.final_width_mm and self.final_width_mm <= 0:
			frappe.throw(_("Final Width (mm) must be greater than 0."))

		if self.final_gauge_mm and self.final_gauge_mm <= 0:
			frappe.throw(_("Final Gauge (mm) must be greater than 0."))

		if self.planned_weight_mt is not None and self.planned_weight_mt <= 0:
			frappe.throw(_("Planned Weight (MT) must be greater than 0."))

		# Validate alloy belongs to Alloy item group
		if self.alloy:
			item_group = frappe.db.get_value("Item", self.alloy, "item_group")
			if item_group != "Alloy":
				frappe.throw(
					_("Selected alloy '{0}' is not under Item Group 'Alloy'. Current group: '{1}'").format(
						self.alloy, item_group
					)
				)

		# Auto-set customer from first Sales Order if not set
		if self.sales_orders and len(self.sales_orders) > 0:
			first_so = self.sales_orders[0].sales_order
			if first_so and not self.customer:
				cust = frappe.db.get_value("Sales Order", first_so, "customer")
				if cust:
					self.customer = cust


	def validate_downtime_fields(self):
		"""Validate fields specific to Downtime plan type"""
		if not self.downtime_type:
			frappe.throw(_("Downtime Type is required for Downtime plans."))

	def shift_future_plans(self):
		"""
		Shift future plans on the same caster forward to make room for this plan.

		This is used by the PPC Caster Kiosk when inserting a new plan in the middle
		of the schedule. We move all plans with start_datetime >= this plan's
		start_datetime forward by this plan's duration.
		"""
		if not self.casting_workstation or not self.start_datetime or not self.end_datetime:
			return

		# Duration of the new plan
		duration = self.end_datetime - self.start_datetime
		if duration.total_seconds() <= 0:
			return

		# Fetch all future plans for this caster that are shiftable
		future_plans = frappe.get_all(
			"PPC Casting Plan",
			filters={
				"caster": self.casting_workstation,
				"status": ["in", SHIFTABLE_STATUSES],
				"docstatus": ["<", 2],
				"start_datetime": [">=", self.start_datetime],
			},
			fields=["name", "start_datetime", "end_datetime"],
			order_by="start_datetime asc",
		)

		if not future_plans:
			return

		# Shift each plan forward by the duration of the new plan.
		# We update via db.set_value to avoid triggering overlap validation
		# on each shifted document; overall ordering and gaps are preserved.
		for p in future_plans:
			# Safety: skip self if somehow present
			if p.name == (self.name or "New"):
				continue

			new_start = p.start_datetime + duration
			new_end = p.end_datetime + duration

			frappe.db.set_value(
				"PPC Casting Plan",
				p.name,
				{
					"start_datetime": new_start,
					"end_datetime": new_end,
				},
				update_modified=True,
			)

	def check_caster_overlap(self):
		"""
		Check for overlapping plans on the same caster.
		
		Status-aware overlap checking:
		- LOCKED plans (Melting, Metal Ready, Casting, Coils Complete, Not Produced) must NEVER overlap
		- SHIFTABLE plans that start at/after this plan's start are being shifted, so allow overlap
		- SHIFTABLE plans that start BEFORE this plan's start must not overlap
		"""
		if not self.casting_workstation or not self.start_datetime or not self.end_datetime:
			return

		# 1) Always check for overlaps with LOCKED plans
		locked_overlap = frappe.db.sql(
			"""
			SELECT name, status
			FROM `tabPPC Casting Plan`
			WHERE
				name != %s
				AND caster = %s
				AND status IN %s
				AND docstatus < 2
				AND (
					(start_datetime <= %s AND end_datetime > %s) OR
					(start_datetime < %s AND end_datetime >= %s) OR
					(start_datetime >= %s AND end_datetime <= %s)
				)
			LIMIT 1
			""",
			(
				self.name or "New",
				self.casting_workstation,
				tuple(LOCKED_STATUSES),
				self.start_datetime, self.start_datetime,
				self.end_datetime, self.end_datetime,
				self.start_datetime, self.end_datetime,
			),
			as_dict=True
		)

		if locked_overlap:
			other = locked_overlap[0]
			frappe.throw(
				_("Time slot overlaps with {0} plan <b>{1}</b> on this caster. "
				  "Cannot overlap plans that are in production or completed.").format(
					other.status, other.name
				)
			)

		# 2) Check for overlaps with SHIFTABLE plans that start BEFORE this plan's start
		# (We don't shift plans that start before, so they must not overlap)
		shiftable_overlap = frappe.db.sql(
			"""
			SELECT name
			FROM `tabPPC Casting Plan`
			WHERE
				name != %s
				AND caster = %s
				AND status IN %s
				AND docstatus < 2
				AND start_datetime < %s
				AND (
					(start_datetime <= %s AND end_datetime > %s) OR
					(start_datetime < %s AND end_datetime >= %s) OR
					(start_datetime >= %s AND end_datetime <= %s)
				)
			LIMIT 1
			""",
			(
				self.name or "New",
				self.casting_workstation,
				tuple(SHIFTABLE_STATUSES),
				self.start_datetime,  # Only plans that start BEFORE this plan
				self.start_datetime, self.start_datetime,
				self.end_datetime, self.end_datetime,
				self.start_datetime, self.end_datetime,
			),
			as_dict=True
		)

		if shiftable_overlap:
			other = shiftable_overlap[0].name
			frappe.throw(
				_("Time slot overlaps with another plan on this caster: <b>{0}</b>. "
				  "Please adjust timing or move that plan.").format(other)
			)

		# Note: We allow overlap with SHIFTABLE plans that start at/after this plan's start
		# because those will be shifted by shift_future_plans()

	def validate_workstations(self):
		"""Ensure casting workstation and furnace workstation types are correct."""
		# Validate casting workstation - must be workstation_type = 'Casting'
		if self.casting_workstation:
			ws_type = frappe.db.get_value("Workstation", self.casting_workstation, "workstation_type")
			if ws_type != "Casting":
				frappe.throw(
					_("Selected workstation '{0}' is of type '{1}'. "
					  "Only Workstations with type 'Casting' can be selected as Casting Workstation.").format(
						self.casting_workstation, ws_type or "Unknown"
					)
				)

		# Validate furnace - must be workstation_type = 'Furnace'
		if self.furnace:
			furnace_type = frappe.db.get_value("Workstation", self.furnace, "workstation_type")
			if furnace_type != "Furnace":
				frappe.throw(
					_("Selected furnace '{0}' is of type '{1}'. "
					  "Only Workstations with type 'Furnace' can be selected as Furnace.").format(
						self.furnace, furnace_type or "Unknown"
					)
				)

	def on_submit(self):
		"""Actions on submit"""
		if self.status == "Planned":
			# Keep as Planned on submit (was Draft before)
			pass

	def before_cancel(self):
		"""Validate that plan can be cancelled"""
		self.validate_can_cancel()

	def validate_can_cancel(self):
		"""
		Block cancellation if melting has already started or coils have been produced.
		
		Cancellation is only allowed when:
		- status is in ("Planned", "Released")
		- linked_melting_batch is empty OR the batch is still Draft with no materials
		"""
		# Check status - block if already in production
		if self.status in LOCKED_STATUSES:
			frappe.throw(
				_("Casting Plan cannot be cancelled because {0}.<br><br>"
				  "If the heat was rejected, mark the Melting Batch as 'Scrapped' "
				  "and set this plan's status to 'Not Produced'.").format(
					self._get_cancel_block_reason()
				),
				title=_("Cannot Cancel")
			)
		
		# Check linked melting batch
		if self.melting_batch:
			batch_doc = frappe.get_doc("Melting Batch", self.melting_batch)
			if batch_doc.docstatus == 2:
				# Batch is cancelled, OK to proceed
				pass
			elif batch_doc.status != "Draft":
				frappe.throw(
					_("Cannot cancel this Casting Plan because Melting Batch <b>{0}</b> "
					  "has status '{1}'.<br><br>"
					  "To cancel this plan, first cancel or scrap the Melting Batch.").format(
						self.melting_batch, batch_doc.status
					),
					title=_("Plan Locked")
				)
			elif batch_doc.raw_materials and len(batch_doc.raw_materials) > 0:
				frappe.throw(
					_("Cannot cancel this Casting Plan because Melting Batch <b>{0}</b> "
					  "already has raw materials charged.<br><br>"
					  "If the heat was rejected, mark the batch as 'Scrapped'.").format(
						self.melting_batch
					),
					title=_("Plan Locked")
				)
		
		# Also check if any non-cancelled Melting Batch is linked via ppc_casting_plan
		linked_batches = frappe.db.get_all(
			"Melting Batch",
			filters={
				"ppc_casting_plan": self.name,
				"docstatus": ["!=", 2]
			},
			fields=["name", "status"],
			limit=1,
		)
		
		if linked_batches:
			batch = linked_batches[0]
			if batch.status != "Draft":
				frappe.throw(
					_("Cannot cancel this Casting Plan because Melting Batch <b>{0}</b> "
					  "is linked and has status '{1}'.").format(
						batch.name, batch.status
					),
					title=_("Plan Locked")
				)
	
	def _get_cancel_block_reason(self):
		"""Return human-readable reason why cancellation is blocked."""
		reasons = {
			"Melting": "melting has already started",
			"Metal Ready": "metal is ready for casting (melting completed)",
			"Casting": "casting is in progress",
			"Coils Complete": "coils have already been produced",
			"Not Produced": "the plan has been marked as Not Produced"
		}
		return reasons.get(self.status, f"status is '{self.status}'")

	def on_cancel(self):
		"""Actions on cancel"""
		# Status update not needed - document is cancelled
		pass
	
	def adjust_future_plans_for_caster(self):
		"""
		Adjust future plans on the same caster when actual_end deviates from planned_end.
		
		This is a legacy wrapper for backward compatibility.
		The actual shifting logic is now in shift_future_plans_after.
		"""
		shift_future_plans_after(self)
	
	def shift_schedule_on_melting_start(self, actual_start_time=None):
		"""
		Re-anchor this plan when melting starts and shift future plans to prevent overlaps.
		
		This method:
		1. Updates the plan's start time to the actual melting start
		2. Recalculates end time using the original planned_duration_minutes
		3. Sets melting_start and actual_start timestamps
		4. Shifts all future plans for the same caster to remove overlaps
		
		Args:
			actual_start_time: When melting actually started (defaults to now)
		
		Example:
			Plan A: 12:00–13:00, Plan B: 13:00–14:00 (duration 60min each)
			Melting for Plan B starts at 11:45.
			→ Re-anchor Plan B to 11:45–12:45 (60min duration preserved)
			→ Plan A remains at 12:00–13:00 (earlier, not affected)
			→ Any plan overlapping with 11:45–12:45 gets pushed after 12:45
		"""
		from frappe.utils import now_datetime, get_datetime
		
		if not actual_start_time:
			actual_start_time = now_datetime()
		else:
			actual_start_time = get_datetime(actual_start_time)
		
		if not self.start_datetime:
			return
		
		old_planned_start = get_datetime(self.start_datetime)
		
		# Only re-anchor if actual differs from planned
		if actual_start_time == old_planned_start:
			return
		
		# Get planned duration - use stored value or calculate from current times
		duration_minutes = self.planned_duration_minutes
		if not duration_minutes and self.end_datetime:
			old_planned_end = get_datetime(self.end_datetime)
			duration_minutes = (old_planned_end - old_planned_start).total_seconds() / 60.0
		
		if not duration_minutes:
			duration_minutes = 60  # Default to 60 minutes if nothing else
		
		# Re-anchor this plan to the actual melting start
		self.start_datetime = actual_start_time
		self.end_datetime = actual_start_time + timedelta(minutes=duration_minutes)
		
		# Set melting and actual start timestamps
		self.melting_start = actual_start_time
		if not self.actual_start:
			self.actual_start = actual_start_time
		
		# Update status to Melting
		if self.status in SHIFTABLE_STATUSES:
			self.status = "Melting"
		
		self.save(ignore_permissions=True)
		
		# Shift future plans to remove overlaps
		shift_future_plans_after(self)


@frappe.whitelist()
def get_casting_plans_for_caster(caster, from_date=None, to_date=None):
	"""Get all casting plans for a caster within a date range.
	Used for Gantt/calendar views.
	
	Args:
		caster: Workstation name
		from_date: Start date filter
		to_date: End date filter
	
	Returns:
		list: List of casting plan documents
	"""
	filters = {
		"caster": caster,
		"status": ["not in", ["Not Produced"]],  # Show all except Not Produced
		"docstatus": ["<", 2]
	}

	if from_date:
		filters["plan_date"] = [">=", from_date]
	if to_date:
		if "plan_date" in filters:
			filters["plan_date"] = ["between", [from_date, to_date]]
		else:
			filters["plan_date"] = ["<=", to_date]

	return frappe.get_all(
		"PPC Casting Plan",
		filters=filters,
		fields=[
			"name", "cast_no", "plan_type", "plan_date", "shift", "status",
			"casting_workstation", "furnace",
			"start_datetime", "end_datetime", "duration_minutes",
			"melting_start", "melting_end", "casting_start", "casting_end",
			"actual_start", "actual_end",
			"product_item", "alloy", "temper", "planned_width_mm", "planned_gauge_mm",
			"planned_weight_mt", "final_width_mm", "final_gauge_mm", "final_weight_mt",
			"customer", "block_color",
			"downtime_type", "downtime_reason",
			"melting_batch", "mother_coil",
			"overlap_flag", "overlap_note"
		],
		order_by="start_datetime"
	)


@frappe.whitelist()
def get_available_slots(caster, date, min_duration_minutes=60):
	"""Get available time slots on a caster for a given date.
	
	Args:
		caster: Workstation name
		date: Date to check
		min_duration_minutes: Minimum slot duration to return
	
	Returns:
		list: List of available slots with start/end times
	"""
	from datetime import datetime, time, timedelta

	# Get all plans for the day
	plans = frappe.get_all(
		"PPC Casting Plan",
		filters={
			"caster": caster,
			"plan_date": date,
			"status": ["not in", ["Not Produced"]],
			"docstatus": ["<", 2]
		},
		fields=["start_datetime", "end_datetime"],
		order_by="start_datetime"
	)

	# Define day boundaries (6 AM to 10 PM)
	day_start = datetime.combine(
		datetime.strptime(date, "%Y-%m-%d").date() if isinstance(date, str) else date,
		time(6, 0)
	)
	day_end = datetime.combine(
		datetime.strptime(date, "%Y-%m-%d").date() if isinstance(date, str) else date,
		time(22, 0)
	)

	available_slots = []
	current_start = day_start

	for plan in plans:
		if plan.start_datetime > current_start:
			slot_duration = (plan.start_datetime - current_start).total_seconds() / 60
			if slot_duration >= min_duration_minutes:
				available_slots.append({
					"start": current_start,
					"end": plan.start_datetime,
					"duration_minutes": int(slot_duration)
				})
		current_start = max(current_start, plan.end_datetime)

	# Check remaining time after last plan
	if current_start < day_end:
		slot_duration = (day_end - current_start).total_seconds() / 60
		if slot_duration >= min_duration_minutes:
			available_slots.append({
				"start": current_start,
				"end": day_end,
				"duration_minutes": int(slot_duration)
			})

	return available_slots


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_so_items_for_order(doctype, txt, searchfield, start, page_len, filters):
	"""Get Sales Order Items filtered by parent Sales Order.
	Used in so_item field query in child table.
	"""
	sales_order = filters.get("sales_order")
	if not sales_order:
		return []

	return frappe.db.sql(
		"""
		SELECT soi.name, soi.item_code, soi.item_name, soi.qty
		FROM `tabSales Order Item` soi
		WHERE soi.parent = %s
		AND (soi.item_code LIKE %s OR soi.item_name LIKE %s)
		ORDER BY soi.idx
		LIMIT %s, %s
		""",
		(sales_order, f"%{txt}%", f"%{txt}%", start, page_len)
	)


# ==================== SCHEDULE SHIFTING HELPERS ====================

def shift_future_plans_after(current_plan):
	"""
	Ensure no overlaps for this caster after current_plan.
	
	This function is called when:
	1. A plan is re-anchored on melting start
	2. A plan's actual_end is set after coil completion
	
	Algorithm:
	- Get all plans for same caster with start_datetime >= current_plan.start_datetime,
	  excluding current_plan, ordered by start_datetime.
	- For each next_plan:
	    if next_plan.start_datetime < last_end:
	        # push it forward to last_end, keeping its original duration
	        if next_plan.planned_duration_minutes:
	            next_plan.start_datetime = last_end
	            next_plan.end_datetime = last_end + timedelta(minutes=next_plan.planned_duration_minutes)
	        else:
	            # fallback: keep same duration as before
	            dur = next_plan.end_datetime - next_plan.start_datetime
	            next_plan.start_datetime = last_end
	            next_plan.end_datetime = last_end + dur
	        next_plan.save()
	        last_end = next_plan.end_datetime
	    else:
	        last_end = next_plan.end_datetime
	
	Example:
	# Plan A: 12:00–13:00, Plan B: 13:00–14:00 (duration 60min each)
	# Melting for Plan B starts at 11:45.
	# → Re-anchor Plan B to 11:45–12:45 (60min)
	# → Plan A remains at 12:00–13:00 (because it is earlier than current_plan's new start)
	# If a later plan C is at 12:30–13:30, it will be pushed after 12:45 etc.
	"""
	from frappe.utils import get_datetime
	
	if not current_plan.caster or not current_plan.start_datetime or not current_plan.end_datetime:
		return
	
	caster = current_plan.caster
	last_end = get_datetime(current_plan.end_datetime)
	
	# Get all future plans for this caster that could potentially overlap
	# We only shift plans that haven't started yet (SHIFTABLE_STATUSES)
	future_plans = frappe.get_all(
		"PPC Casting Plan",
		filters={
			"name": ["!=", current_plan.name],
			"caster": caster,
			"start_datetime": [">=", current_plan.start_datetime],
			"status": ["in", SHIFTABLE_STATUSES],
			"docstatus": ["<", 2],  # Not cancelled
		},
		fields=["name", "start_datetime", "end_datetime", "planned_duration_minutes"],
		order_by="start_datetime asc",
	)
	
	for row in future_plans:
		next_plan = frappe.get_doc("PPC Casting Plan", row.name)
		start = get_datetime(next_plan.start_datetime)
		end = get_datetime(next_plan.end_datetime)
		
		if start < last_end:
			# Need to push forward - there's an overlap
			duration_min = next_plan.planned_duration_minutes
			if not duration_min:
				# Fallback: calculate duration from current times
				duration_min = (end - start).total_seconds() / 60.0
			
			# Push forward to last_end
			next_plan.start_datetime = last_end
			next_plan.end_datetime = last_end + timedelta(minutes=duration_min)
			next_plan.save(ignore_permissions=True)
			
			last_end = get_datetime(next_plan.end_datetime)
		else:
			# No overlap, but update last_end for subsequent plans
			last_end = end
	
	frappe.db.commit()


@frappe.whitelist()
def start_melting_for_plan(plan_name, melting_batch_name=None, melt_start=None):
	"""
	Called from Melting Kiosk when operator starts melting for a PPC plan.
	
	This function:
	1. Links the melting batch to the plan (if provided)
	2. Updates plan status to "Melting"
	3. Re-anchors the plan's time window based on planned_duration_minutes
	4. Sets actual_start timestamp
	5. Shifts all future plans for the caster to remove overlaps
	
	Args:
		plan_name: Name of the PPC Casting Plan
		melting_batch_name: Name of the linked Melting Batch (optional)
		melt_start: When melting started (defaults to now)
	
	Returns:
		dict with plan_name and updated timestamps
	"""
	from frappe.utils import now_datetime, get_datetime
	
	if not plan_name:
		frappe.throw(_("Casting Plan is required."))
	
	plan = frappe.get_doc("PPC Casting Plan", plan_name)
	
	# Default melt_start = now
	melt_start_dt = get_datetime(melt_start) if melt_start else now_datetime()
	
	# 1) Link melting batch if provided
	if melting_batch_name:
		plan.melting_batch = melting_batch_name
	
	# 2) Ensure planned_duration_minutes is set
	if not plan.planned_duration_minutes:
		if plan.start_datetime and plan.end_datetime:
			start = get_datetime(plan.start_datetime)
			end = get_datetime(plan.end_datetime)
			plan.planned_duration_minutes = (end - start).total_seconds() / 60.0
		else:
			plan.planned_duration_minutes = 60  # Default fallback
	
	# 3) Re-anchor the plan to the actual melting start
	if plan.planned_duration_minutes:
		plan.start_datetime = melt_start_dt
		plan.end_datetime = melt_start_dt + timedelta(minutes=plan.planned_duration_minutes)
	
	# 4) Set timestamps
	if not plan.actual_start:
		plan.actual_start = melt_start_dt
	plan.melting_start = melt_start_dt
	
	# 5) Update status
	if plan.status in SHIFTABLE_STATUSES:
		plan.status = "Melting"
	
	plan.save(ignore_permissions=True)
	
	# 6) Shift future plans to remove overlaps
	shift_future_plans_after(plan)
	
	frappe.db.commit()
	
	return {
		"plan_name": plan.name,
		"start_datetime": str(plan.start_datetime),
		"end_datetime": str(plan.end_datetime),
		"actual_start": str(plan.actual_start),
		"status": plan.status
	}


@frappe.whitelist()
def mark_casting_complete(plan_name, completion_time=None):
	"""
	Called when casting/coils are completed for a PPC plan.
	
	This function:
	1. Sets actual_end from the completion time
	2. Updates plan status to "Coils Complete"
	3. Updates the plan's from/to times to match actuals (for calendar display)
	4. Shifts future plans again (because actual_end may be later than planned)
	
	Args:
		plan_name: Name of the PPC Casting Plan
		completion_time: When casting completed (defaults to now)
	
	Returns:
		dict with plan_name and updated timestamps
	"""
	from frappe.utils import now_datetime, get_datetime
	
	if not plan_name:
		frappe.throw(_("Casting Plan is required."))
	
	plan = frappe.get_doc("PPC Casting Plan", plan_name)
	
	complete_dt = get_datetime(completion_time) if completion_time else now_datetime()
	
	# Set actual end and casting end
	plan.actual_end = complete_dt
	plan.casting_end = complete_dt
	
	# Update status
	plan.status = "Coils Complete"
	
	# For the calendar, update from/to to match actuals
	# This ensures the calendar shows the true production window
	if plan.actual_start and plan.actual_end:
		plan.start_datetime = plan.actual_start
		plan.end_datetime = plan.actual_end
	
	plan.save(ignore_permissions=True)
	
	# Shift future plans again because actual_end may differ from planned
	shift_future_plans_after(plan)
	
	frappe.db.commit()
	
	return {
		"plan_name": plan.name,
		"start_datetime": str(plan.start_datetime),
		"end_datetime": str(plan.end_datetime),
		"actual_start": str(plan.actual_start) if plan.actual_start else None,
		"actual_end": str(plan.actual_end) if plan.actual_end else None,
		"status": plan.status
	}
