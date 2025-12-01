# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class DrossLog(Document):
	pass


@frappe.whitelist()
def generate_dross_id():
	"""Generate unique Dross ID in format DROSS-####"""
	prefix = "DROSS"
	# Get max existing number
	last_id = frappe.db.sql("""
		SELECT dross_id 
		FROM `tabDross Log` 
		WHERE dross_id LIKE %s 
		ORDER BY CAST(SUBSTRING_INDEX(dross_id, '-', -1) AS UNSIGNED) DESC 
		LIMIT 1
	""", (f"{prefix}-%",), as_dict=True)
	
	if last_id and last_id[0].get("dross_id"):
		last_num = int(last_id[0]["dross_id"].split("-")[1])
		new_num = last_num + 1
	else:
		new_num = 1
	
	return f"{prefix}-{new_num:04d}"
