# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime, get_datetime

# Active statuses that indicate a batch is occupying the furnace
ACTIVE_BATCH_STATUSES = [
	"Charging", "Melting", "Fluxing", "Sampling", "Correction", "Ready for Transfer"
]

# Statuses that indicate processing has begun (block cancellation)
PROCESSING_STARTED_STATUSES = ["Charging", "Melting", "Ready for Transfer", "Transferred", "Scrapped"]


class MeltingBatch(Document):
	def validate(self):
		self.set_melting_batch_id()
		self.calculate_charged_weight()
		self.calculate_yield_percent()
		self.validate_datetime_sequence()
		self.validate_status_workflow()
		self.validate_single_active_batch_per_furnace()

	def before_submit(self):
		self.validate_submit_status()

	def before_cancel(self):
		"""Validate that batch can be cancelled"""
		self.validate_can_cancel()

	def set_melting_batch_id(self):
		"""Set melting_batch_id from name if not already set"""
		if not self.melting_batch_id and self.name:
			self.melting_batch_id = self.name

	def calculate_charged_weight(self):
		"""Calculate total charged weight from raw materials table"""
		total_kg = 0
		for row in self.raw_materials or []:
			total_kg += flt(row.qty_kg, 3)
		
		self.charged_weight_mt = flt(total_kg / 1000, 3)

	def calculate_yield_percent(self):
		"""Calculate yield percentage based on tapped vs charged weight"""
		if flt(self.tapped_weight_mt) > 0 and flt(self.charged_weight_mt) > 0:
			self.yield_percent = flt(
				(flt(self.tapped_weight_mt) / flt(self.charged_weight_mt)) * 100, 2
			)
		else:
			self.yield_percent = 0

	def validate_datetime_sequence(self):
		"""Validate that batch_start_datetime <= batch_end_datetime"""
		if self.batch_start_datetime and self.batch_end_datetime:
			if self.batch_start_datetime > self.batch_end_datetime:
				frappe.throw(
					_("Batch Start ({0}) cannot be after Batch End ({1})").format(
						self.batch_start_datetime, self.batch_end_datetime
					)
				)

		if self.transfer_start_datetime and self.transfer_end_datetime:
			if self.transfer_start_datetime > self.transfer_end_datetime:
				frappe.throw(
					_("Transfer Start ({0}) cannot be after Transfer End ({1})").format(
						self.transfer_start_datetime, self.transfer_end_datetime
					)
				)

	def validate_status_workflow(self):
		"""Validate status transitions follow the workflow:
		Draft → Charging → Melting → Ready for Transfer → Transferred
		                                               → Scrapped
		"""
		if self.is_new():
			return

		old_doc = self.get_doc_before_save()
		if not old_doc:
			return

		old_status = old_doc.status
		new_status = self.status

		if old_status == new_status:
			return

		# Define valid transitions
		valid_transitions = {
			"Draft": ["Charging", "Scrapped"],
			"Charging": ["Melting", "Scrapped"],
			"Melting": ["Ready for Transfer", "Scrapped"],
			"Ready for Transfer": ["Transferred", "Scrapped"],
			"Transferred": [],  # Terminal state
			"Scrapped": []  # Terminal state
		}

		allowed = valid_transitions.get(old_status, [])
		if new_status not in allowed:
			frappe.throw(
				_("Invalid status transition from '{0}' to '{1}'. Allowed: {2}").format(
					old_status, new_status, ", ".join(allowed) or "None"
				)
			)

	def validate_submit_status(self):
		"""Only allow submission when status is Transferred or Scrapped"""
		if self.status not in ["Transferred", "Scrapped"]:
			frappe.throw(
				_("Melting Batch can only be submitted when status is 'Transferred' or 'Scrapped'. "
				  "Current status: '{0}'").format(self.status)
			)

	def validate_can_cancel(self):
		"""
		Validate that batch can be cancelled.
		
		A Melting Batch can be Cancelled/Deleted only if:
		- status == "Draft" AND
		- No raw materials have been added (raw_materials child table is empty) AND
		- No process events exist (burner start, fluxing, samples)
		
		Once any of those exist, block cancel with a clear error message.
		"""
		# Check if status allows cancellation
		if self.status != "Draft":
			frappe.throw(
				_("Melting Batch cannot be cancelled – material has already been processed. "
				  "Current status: '{0}'.<br><br>"
				  "Use 'Scrapped' status if the heat was rejected.").format(self.status),
				title=_("Cannot Cancel")
			)
		
		# Check if raw materials exist
		if self.raw_materials and len(self.raw_materials) > 0:
			frappe.throw(
				_("Melting Batch cannot be cancelled – raw materials have been added ({0} items).<br><br>"
				  "Use 'Scrapped' status if the heat was rejected.").format(len(self.raw_materials)),
				title=_("Cannot Cancel")
			)
		
		# Check if process logs exist
		if self.process_logs and len(self.process_logs) > 0:
			frappe.throw(
				_("Melting Batch cannot be cancelled – process events have been logged ({0} events).<br><br>"
				  "Use 'Scrapped' status if the heat was rejected.").format(len(self.process_logs)),
				title=_("Cannot Cancel")
			)
		
		# Check if spectro samples exist
		if self.spectro_samples and len(self.spectro_samples) > 0:
			frappe.throw(
				_("Melting Batch cannot be cancelled – spectro samples have been taken ({0} samples).<br><br>"
				  "Use 'Scrapped' status if the heat was rejected.").format(len(self.spectro_samples)),
				title=_("Cannot Cancel")
			)

	def validate_single_active_batch_per_furnace(self):
		"""
		Enforce single active melting batch per furnace.
		A furnace may NEVER have two batches simultaneously in active statuses.
		"""
		if not self.furnace:
			return

		# Only check if this batch is going into an active status
		if self.status not in ACTIVE_BATCH_STATUSES:
			return

		# Check if any other batch for the same furnace is currently active
		existing_active = frappe.db.sql("""
			SELECT name, status
			FROM `tabMelting Batch`
			WHERE furnace = %s
			AND name != %s
			AND status IN %s
			AND docstatus < 2
			LIMIT 1
		""", (self.furnace, self.name or "", tuple(ACTIVE_BATCH_STATUSES)), as_dict=True)

		if existing_active:
			frappe.throw(
				_("Furnace <b>{0}</b> already has an active batch <b>{1}</b> (Status: {2}).<br><br>"
				  "Complete or Transfer the existing batch before starting a new one.").format(
					self.furnace,
					existing_active[0].name,
					existing_active[0].status
				),
				title=_("Furnace Busy")
			)

	def on_update(self):
		"""Actions after save - sync with Casting Plan"""
		self.sync_to_casting_plan()

	def sync_to_casting_plan(self):
		"""
		Sync melting batch status and timing back to the linked PPC Casting Plan.
		
		Rules:
		- When batch goes to Charging (first significant action), set plan's melting_start
		- When batch goes to Transferred, set plan's melting_end and status to Metal Ready
		- When batch goes to Scrapped, set plan's status to Not Produced
		"""
		if not self.ppc_casting_plan:
			return
		
		try:
			cp = frappe.get_doc("PPC Casting Plan", self.ppc_casting_plan)
			
			# Don't update cancelled plans
			if cp.docstatus == 2:
				return
			
			updates = {}
			
			# When charging starts (first significant action)
			if self.status == "Charging" and not cp.melting_start:
				updates["melting_start"] = self.batch_start_datetime or now_datetime()
				updates["actual_start"] = updates["melting_start"]
				if cp.status in ["Planned", "Released"]:
					updates["status"] = "Melting"
			
			# When status changes to Melting
			if self.status == "Melting" and cp.status in ["Planned", "Released"]:
				if not cp.melting_start:
					updates["melting_start"] = self.batch_start_datetime or now_datetime()
					updates["actual_start"] = updates["melting_start"]
				updates["status"] = "Melting"
			
			# When batch is Transferred (metal ready in holder)
			if self.status == "Transferred":
				updates["melting_end"] = self.transfer_end_datetime or self.batch_end_datetime or now_datetime()
				# If casting has not yet started, set status to Metal Ready
				if cp.status in ["Melting", "Released", "Planned"]:
					updates["status"] = "Metal Ready"
			
			# When batch is Scrapped
			if self.status == "Scrapped":
				updates["melting_end"] = now_datetime()
				updates["status"] = "Not Produced"
			
			# Apply updates if any
			if updates:
				for field, value in updates.items():
					cp.db_set(field, value, update_modified=True)
				
		except Exception as e:
			# Log error but don't block the save
			frappe.log_error(
				title="Melting Batch → Casting Plan Sync Error",
				message=f"Error syncing batch {self.name} to plan {self.ppc_casting_plan}: {str(e)}"
			)

	def mark_melting_started_if_first_time(self):
		"""
		Called when the first irreversible melting action happens
		(e.g., Burner Start, first raw material charge, etc.).

		Behaviour:
		- Only runs once per batch.
		- If linked ppc_casting_plan exists and its melting hasn't started yet,
		  we update casting_plan.melting_start & actual_start.
		- We then move the PPC plan to start at this actual time,
		  preserving duration, and shift all future not-started plans
		  on that caster by the same delta.
		"""
		if not self.ppc_casting_plan:
			return

		from swynix_mes.swynix_mes.utils.ppc_scheduler import shift_future_plans_for_caster

		cp = frappe.get_doc("PPC Casting Plan", self.ppc_casting_plan)

		# If already recorded melting_start, do nothing.
		if getattr(cp, "melting_start", None):
			return

		now_ts = now_datetime()

		# Original planned times BEFORE we move anything.
		old_planned_start = get_datetime(cp.start_datetime) if cp.start_datetime else None
		old_planned_end = get_datetime(cp.end_datetime) if cp.end_datetime else None

		# Set melting / actual start timestamps & status.
		cp.melting_start = now_ts
		cp.actual_start = now_ts
		# If it's still Planned/Released, bump status to "Melting"
		if cp.status in ("Planned", "Released"):
			cp.status = "Melting"

		delta_seconds = 0.0

		if old_planned_start and old_planned_end:
			duration = old_planned_end - old_planned_start  # timedelta

			# delta between actual vs original start
			delta_seconds = (now_ts - old_planned_start).total_seconds()

			# Move this plan itself to the actual melting start
			cp.start_datetime = now_ts
			cp.end_datetime = now_ts + duration

		cp.save(ignore_permissions=True)

		# Shift future plans on this caster, starting from original start time
		if delta_seconds and old_planned_start:
			shift_future_plans_for_caster(
				casting_plan_name=cp.name,
				delta_seconds=delta_seconds,
				from_time=old_planned_start,
			)

	# Legacy alias for backward compatibility
	def mark_melting_started(self):
		"""Legacy alias for mark_melting_started_if_first_time()"""
		self.mark_melting_started_if_first_time()

	@frappe.whitelist()
	def set_status(self, new_status):
		"""API method to change status with validation"""
		self.status = new_status
		self.save()
		return self.status

	@frappe.whitelist()
	def start_charging(self):
		"""Transition to Charging status"""
		if self.status != "Draft":
			frappe.throw(_("Can only start charging from Draft status"))
		
		self.status = "Charging"
		if not self.batch_start_datetime:
			self.batch_start_datetime = now_datetime()
		self.save()
		
		# Trigger melting started logic (shifts schedule)
		self.mark_melting_started_if_first_time()
		
		return self.status

	@frappe.whitelist()
	def start_melting(self):
		"""Transition to Melting status"""
		if self.status != "Charging":
			frappe.throw(_("Can only start melting from Charging status"))
		
		self.status = "Melting"
		self.save()
		return self.status

	@frappe.whitelist()
	def mark_ready_for_transfer(self):
		"""Transition to Ready for Transfer status"""
		if self.status != "Melting":
			frappe.throw(_("Can only mark ready for transfer from Melting status"))
		
		self.status = "Ready for Transfer"
		self.save()
		return self.status

	@frappe.whitelist()
	def start_transfer(self):
		"""Start transfer process"""
		if self.status != "Ready for Transfer":
			frappe.throw(_("Transfer can only start when status is 'Ready for Transfer'"))
		
		if not self.transfer_start_datetime:
			self.transfer_start_datetime = now_datetime()
		self.save()
		return self.status

	@frappe.whitelist()
	def complete_transfer(self):
		"""Complete transfer and set status to Transferred"""
		if self.status != "Ready for Transfer":
			frappe.throw(_("Transfer can only complete when status is 'Ready for Transfer'"))
		
		self.status = "Transferred"
		if not self.transfer_end_datetime:
			self.transfer_end_datetime = now_datetime()
		if not self.batch_end_datetime:
			self.batch_end_datetime = now_datetime()
		self.save()
		return self.status

	@frappe.whitelist()
	def mark_scrapped(self, reason=None):
		"""Mark batch as Scrapped (rejected heat)"""
		if self.status in ["Transferred", "Scrapped"]:
			frappe.throw(_("Cannot scrap a batch that is already {0}").format(self.status))
		
		self.status = "Scrapped"
		if not self.batch_end_datetime:
			self.batch_end_datetime = now_datetime()
		if reason:
			self.remarks = (self.remarks or "") + f"\n[SCRAPPED] {reason}"
		self.save()
		return self.status


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_foundry_workstations(doctype, txt, searchfield, start, page_len, filters):
	"""Get workstations filtered by workstation_type = 'Foundry'"""
	return frappe.db.sql("""
		SELECT name, workstation_name
		FROM `tabWorkstation`
		WHERE workstation_type = 'Foundry'
		AND (name LIKE %(txt)s OR workstation_name LIKE %(txt)s)
		ORDER BY name
		LIMIT %(start)s, %(page_len)s
	""", {
		"txt": f"%{txt}%",
		"start": start,
		"page_len": page_len
	})


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_alloy_items(doctype, txt, searchfield, start, page_len, filters):
	"""Get items filtered by item_group = 'Alloy'"""
	return frappe.db.sql("""
		SELECT name, item_name
		FROM `tabItem`
		WHERE item_group = 'Alloy'
		AND (name LIKE %(txt)s OR item_name LIKE %(txt)s)
		ORDER BY name
		LIMIT %(start)s, %(page_len)s
	""", {
		"txt": f"%{txt}%",
		"start": start,
		"page_len": page_len
	})


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_product_items(doctype, txt, searchfield, start, page_len, filters):
	"""Get items filtered by item_group = 'Product'"""
	return frappe.db.sql("""
		SELECT name, item_name
		FROM `tabItem`
		WHERE item_group = 'Product'
		AND (name LIKE %(txt)s OR item_name LIKE %(txt)s)
		ORDER BY name
		LIMIT %(start)s, %(page_len)s
	""", {
		"txt": f"%{txt}%",
		"start": start,
		"page_len": page_len
	})


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_charge_mix_for_alloy(doctype, txt, searchfield, start, page_len, filters):
	"""Get active Charge Mix Ratios for a specific alloy"""
	alloy = filters.get("alloy")
	conditions = ["docstatus = 1", "is_active = 1"]
	
	if alloy:
		conditions.append("alloy = %(alloy)s")
	
	conditions.append("(name LIKE %(txt)s OR recipe_code LIKE %(txt)s)")
	
	return frappe.db.sql("""
		SELECT name, recipe_code, alloy
		FROM `tabCharge Mix Ratio`
		WHERE {conditions}
		ORDER BY effective_date DESC, name
		LIMIT %(start)s, %(page_len)s
	""".format(conditions=" AND ".join(conditions)), {
		"alloy": alloy,
		"txt": f"%{txt}%",
		"start": start,
		"page_len": page_len
	})


@frappe.whitelist()
def get_melting_batch_summary(melting_batch):
	"""Get summary data for a Melting Batch"""
	doc = frappe.get_doc("Melting Batch", melting_batch)
	
	return {
		"melting_batch_id": doc.melting_batch_id,
		"status": doc.status,
		"alloy": doc.alloy,
		"furnace": doc.furnace,
		"planned_weight_mt": doc.planned_weight_mt,
		"charged_weight_mt": doc.charged_weight_mt,
		"tapped_weight_mt": doc.tapped_weight_mt,
		"yield_percent": doc.yield_percent,
		"raw_material_count": len(doc.raw_materials or []),
		"spectro_sample_count": len(doc.spectro_samples or [])
	}
