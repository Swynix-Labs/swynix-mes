# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CastingOperation(Document):
	pass


@frappe.whitelist()
def generate_casting_id():
	"""Generate unique Casting ID in format CAST-####"""
	prefix = "CAST"
	# Get max existing number
	last_id = frappe.db.sql("""
		SELECT casting_id 
		FROM `tabCasting Operation` 
		WHERE casting_id LIKE %s 
		ORDER BY CAST(SUBSTRING_INDEX(casting_id, '-', -1) AS UNSIGNED) DESC 
		LIMIT 1
	""", (f"{prefix}-%",), as_dict=True)
	
	if last_id and last_id[0].get("casting_id"):
		last_num = int(last_id[0]["casting_id"].split("-")[1])
		new_num = last_num + 1
	else:
		new_num = 1
	
	return f"{prefix}-{new_num:04d}"
