# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

from datetime import timedelta

import frappe
from frappe import _
from frappe.model.document import Document

# Import status constants from API
try:
	from swynix_mes.swynix_mes.api.ppc_caster_kiosk import SHIFTABLE_STATUSES, LOCKED_STATUSES
except ImportError:
	# Fallback if import fails
	SHIFTABLE_STATUSES = ["Draft", "Planned", "Released to Melting"]
	LOCKED_STATUSES = ["In Process", "Completed"]


class PPCCastingPlan(Document):
	def validate(self):
		self.validate_required_fields()
		self.validate_datetime_range()
		self.calculate_duration()
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

	def auto_set_plan_date(self):
		"""Auto set plan_date from start_datetime if missing"""
		if not self.plan_date and self.start_datetime:
			self.plan_date = self.start_datetime.date()

	def auto_set_defaults(self):
		"""Set default values"""
		# Default status
		if not self.status:
			self.status = "Draft"

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

		# Auto-link active CMR by alloy if not set
		if self.alloy and not self.charge_mix_recipe:
			cmr = frappe.db.get_value(
				"Charge Mix Ratio",
				{"alloy": self.alloy, "is_active": 1, "docstatus": 1},
				"name",
				order_by="effective_date desc"
			)
			if cmr:
				self.charge_mix_recipe = cmr

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
		if not self.caster or not self.start_datetime or not self.end_datetime:
			return

		# Duration of the new plan
		duration = self.end_datetime - self.start_datetime
		if duration.total_seconds() <= 0:
			return

		# Fetch all future plans for this caster (excluding Cancelled)
		future_plans = frappe.get_all(
			"PPC Casting Plan",
			filters={
				"caster": self.caster,
				"status": ["!=", "Cancelled"],
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
		- LOCKED plans (In Process / Completed) must NEVER overlap
		- SHIFTABLE plans that start at/after this plan's start are being shifted, so allow overlap
		- SHIFTABLE plans that start BEFORE this plan's start must not overlap
		"""
		if not self.caster or not self.start_datetime or not self.end_datetime:
			return

		# 1) Always check for overlaps with LOCKED plans (In Process / Completed)
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
				self.caster,
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
				  "Cannot overlap plans that are In Process or Completed.").format(
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
				self.caster,
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
		"""Ensure caster and furnace workstation types are correct."""
		# Validate caster - must be workstation_type = 'Casting'
		if self.caster:
			caster_type = frappe.db.get_value("Workstation", self.caster, "workstation_type")
			if caster_type != "Casting":
				frappe.throw(
					_("Selected caster '{0}' is of type '{1}'. "
					  "Only Workstations with type 'Casting' can be selected as Caster.").format(
						self.caster, caster_type or "Unknown"
					)
				)

		# Validate furnace - must be workstation_type = 'Foundry'
		if self.furnace:
			furnace_type = frappe.db.get_value("Workstation", self.furnace, "workstation_type")
			if furnace_type != "Foundry":
				frappe.throw(
					_("Selected furnace '{0}' is of type '{1}'. "
					  "Only Workstations with type 'Foundry' can be selected as Furnace.").format(
						self.furnace, furnace_type or "Unknown"
					)
				)

	def on_submit(self):
		"""Actions on submit"""
		if self.status == "Draft":
			self.db_set("status", "Planned")

	def on_cancel(self):
		"""Actions on cancel"""
		self.db_set("status", "Cancelled")


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
		"status": ["!=", "Cancelled"],
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
			"caster", "start_datetime", "end_datetime", "duration_minutes",
			"product_item", "alloy", "temper", "planned_width_mm", "planned_gauge_mm",
			"planned_weight_mt", "final_width_mm", "final_gauge_mm", "final_weight_mt",
			"customer", "block_color", "charge_mix_recipe",
			"downtime_type", "downtime_reason"
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
			"status": ["!=", "Cancelled"],
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

