# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CastingOperation2(Document):
	pass


@frappe.whitelist()
def generate_casting_operation_id():
	"""Generate unique Casting Operation ID in format CAST2-####"""
	prefix = "CAST2"
	# Get max existing number
	last_id = frappe.db.sql("""
		SELECT casting_operation_id 
		FROM `tabCasting Operation 2` 
		WHERE casting_operation_id LIKE %s 
		ORDER BY CAST(SUBSTRING_INDEX(casting_operation_id, '-', -1) AS UNSIGNED) DESC 
		LIMIT 1
	""", (f"{prefix}-%",), as_dict=True)
	
	if last_id and last_id[0].get("casting_operation_id"):
		last_num = int(last_id[0]["casting_operation_id"].split("-")[1])
		new_num = last_num + 1
	else:
		new_num = 1
	
	return f"{prefix}-{new_num:04d}"
