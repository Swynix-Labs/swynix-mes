# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FoilOperation(Document):
	"""Foil Operation document."""

	pass


@frappe.whitelist()
def load_from_reel(reel: str):
	"""Return basic data from Reel to prefill Foil Operation."""
	if not reel:
		frappe.throw("Reel is required")

	reel_doc = frappe.get_doc("Reel", reel)

	return {
		"width": getattr(reel_doc, "width", None),
		"thickness": getattr(reel_doc, "thickness", None),
		"coil": getattr(reel_doc, "coil", None),
	}


@frappe.whitelist()
def generate_foil_operation_id():
	"""Generate unique Foil Operation ID in format FOIL-####"""
	prefix = "FOIL"
	# Get max existing number
	last_id = frappe.db.sql("""
		SELECT foil_operation_id 
		FROM `tabFoil Operation` 
		WHERE foil_operation_id LIKE %s 
		ORDER BY CAST(SUBSTRING_INDEX(foil_operation_id, '-', -1) AS UNSIGNED) DESC 
		LIMIT 1
	""", (f"{prefix}-%",), as_dict=True)
	
	if last_id and last_id[0].get("foil_operation_id"):
		last_num = int(last_id[0]["foil_operation_id"].split("-")[1])
		new_num = last_num + 1
	else:
		new_num = 1
	
	return f"{prefix}-{new_num:04d}"
