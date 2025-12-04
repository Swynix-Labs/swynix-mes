# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class MeltingBatch(Document):
	def validate(self):
		self.set_melting_batch_id()
		self.calculate_charged_weight()
		self.calculate_yield_percent()
		self.validate_datetime_sequence()
		self.validate_status_workflow()

	def before_submit(self):
		self.validate_submit_status()

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
			"Draft": ["Charging", "Cancelled"],
			"Charging": ["Melting", "Cancelled"],
			"Melting": ["Ready for Transfer", "Cancelled"],
			"Ready for Transfer": ["Transferred", "Cancelled"],
			"Transferred": [],  # Terminal state
			"Cancelled": ["Draft"]  # Can reopen to Draft
		}

		allowed = valid_transitions.get(old_status, [])
		if new_status not in allowed:
			frappe.throw(
				_("Invalid status transition from '{0}' to '{1}'. Allowed: {2}").format(
					old_status, new_status, ", ".join(allowed) or "None"
				)
			)

	def validate_submit_status(self):
		"""Only allow submission when status is Transferred"""
		if self.status != "Transferred":
			frappe.throw(
				_("Melting Batch can only be submitted when status is 'Transferred'. Current status: '{0}'").format(
					self.status
				)
			)

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
			self.batch_start_datetime = frappe.utils.now_datetime()
		self.save()
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
			self.transfer_start_datetime = frappe.utils.now_datetime()
		self.save()
		return self.status

	@frappe.whitelist()
	def complete_transfer(self):
		"""Complete transfer and set status to Transferred"""
		if self.status != "Ready for Transfer":
			frappe.throw(_("Transfer can only complete when status is 'Ready for Transfer'"))
		
		self.status = "Transferred"
		if not self.transfer_end_datetime:
			self.transfer_end_datetime = frappe.utils.now_datetime()
		if not self.batch_end_datetime:
			self.batch_end_datetime = frappe.utils.now_datetime()
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

