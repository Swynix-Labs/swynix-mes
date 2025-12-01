# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CirclePackingLog(Document):
	pass


@frappe.whitelist()
def generate_packing_id():
	"""Generate unique Packing ID in format CPACK-####"""
	prefix = "CPACK"
	# Get max existing number
	last_id = frappe.db.sql("""
		SELECT packing_id 
		FROM `tabCircle Packing Log` 
		WHERE packing_id LIKE %s 
		ORDER BY CAST(SUBSTRING_INDEX(packing_id, '-', -1) AS UNSIGNED) DESC 
		LIMIT 1
	""", (f"{prefix}-%",), as_dict=True)
	
	if last_id and last_id[0].get("packing_id"):
		last_num = int(last_id[0]["packing_id"].split("-")[1])
		new_num = last_num + 1
	else:
		new_num = 1
	
	return f"{prefix}-{new_num:04d}"
