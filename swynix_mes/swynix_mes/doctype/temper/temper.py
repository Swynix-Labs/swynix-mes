# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Temper(Document):
	def validate(self):
		self.validate_temper_code()
		self.validate_alloy_mappings()

	def validate_temper_code(self):
		"""Validate and sanitize temper code"""
		if not self.temper_code:
			frappe.throw(_("Temper Code is required."))

		# Trim and uppercase code
		self.temper_code = self.temper_code.strip().upper()

		# Ensure no spaces in code
		if " " in self.temper_code:
			frappe.throw(_("Temper Code cannot contain spaces."))

	def validate_alloy_mappings(self):
		"""Validate alloy mapping rows"""
		if not self.alloy_mappings:
			return

		seen_alloys = set()

		for idx, row in enumerate(self.alloy_mappings, start=1):
			# Alloy is required
			if not row.alloy:
				frappe.throw(_("Row {0}: Alloy is required in Temper Alloy Mapping.").format(idx))

			# Check for duplicate alloy
			if row.alloy in seen_alloys:
				frappe.throw(
					_("Row {0}: Duplicate alloy '{1}' in Temper Alloy Mapping.").format(idx, row.alloy)
				)
			seen_alloys.add(row.alloy)

			# Ensure alloy item belongs to Item Group 'Alloy'
			item_group = frappe.db.get_value("Item", row.alloy, "item_group")
			if item_group != "Alloy":
				frappe.throw(
					_("Row {0}: Item '{1}' is not under Item Group 'Alloy'. Current group: '{2}'").format(
						idx, row.alloy, item_group
					)
				)

			# Gauge range sanity check (if provided)
			if row.min_gauge_mm and row.max_gauge_mm:
				if row.min_gauge_mm <= 0 or row.max_gauge_mm <= 0:
					frappe.throw(
						_("Row {0}: Gauge values must be positive.").format(idx)
					)
				if row.min_gauge_mm >= row.max_gauge_mm:
					frappe.throw(
						_("Row {0}: Min Gauge ({1}) must be less than Max Gauge ({2}).").format(
							idx, row.min_gauge_mm, row.max_gauge_mm
						)
					)
			elif row.min_gauge_mm and row.min_gauge_mm <= 0:
				frappe.throw(_("Row {0}: Min Gauge must be positive.").format(idx))
			elif row.max_gauge_mm and row.max_gauge_mm <= 0:
				frappe.throw(_("Row {0}: Max Gauge must be positive.").format(idx))


@frappe.whitelist()
def get_tempers_for_alloy(alloy):
	"""Get all active tempers that are mapped to a specific alloy.
	
	Args:
		alloy: Item code of the alloy
	
	Returns:
		list: List of temper codes compatible with the alloy
	"""
	tempers = frappe.db.sql("""
		SELECT DISTINCT t.name, t.temper_code, t.description, t.series, t.hardness_level,
			   tam.min_gauge_mm, tam.max_gauge_mm, tam.preferred
		FROM `tabTemper` t
		INNER JOIN `tabTemper Alloy Mapping` tam ON tam.parent = t.name
		WHERE t.is_active = 1
		AND tam.alloy = %s
		ORDER BY tam.preferred DESC, t.temper_code
	""", (alloy,), as_dict=True)
	
	return tempers


@frappe.whitelist()
def get_alloys_for_temper(temper):
	"""Get all alloys mapped to a specific temper.
	
	Args:
		temper: Temper code/name
	
	Returns:
		list: List of alloy item codes compatible with the temper
	"""
	if not frappe.db.exists("Temper", temper):
		return []
	
	doc = frappe.get_doc("Temper", temper)
	return [
		{
			"alloy": row.alloy,
			"min_gauge_mm": row.min_gauge_mm,
			"max_gauge_mm": row.max_gauge_mm,
			"preferred": row.preferred,
			"remark": row.remark
		}
		for row in doc.alloy_mappings
	]


@frappe.whitelist()
def validate_temper_alloy_gauge(temper, alloy, gauge_mm):
	"""Validate if a gauge is valid for a temper-alloy combination.
	
	Args:
		temper: Temper code
		alloy: Alloy item code
		gauge_mm: Gauge in mm to validate
	
	Returns:
		dict: {valid: bool, message: str}
	"""
	gauge_mm = float(gauge_mm)
	
	mapping = frappe.db.sql("""
		SELECT min_gauge_mm, max_gauge_mm
		FROM `tabTemper Alloy Mapping`
		WHERE parent = %s AND alloy = %s
	""", (temper, alloy), as_dict=True)
	
	if not mapping:
		return {
			"valid": False,
			"message": f"Alloy {alloy} is not mapped to temper {temper}"
		}
	
	row = mapping[0]
	
	# Check min gauge
	if row.min_gauge_mm and gauge_mm < row.min_gauge_mm:
		return {
			"valid": False,
			"message": f"Gauge {gauge_mm}mm is below minimum {row.min_gauge_mm}mm for {temper}/{alloy}"
		}
	
	# Check max gauge
	if row.max_gauge_mm and gauge_mm > row.max_gauge_mm:
		return {
			"valid": False,
			"message": f"Gauge {gauge_mm}mm exceeds maximum {row.max_gauge_mm}mm for {temper}/{alloy}"
		}
	
	return {"valid": True, "message": "Valid"}

