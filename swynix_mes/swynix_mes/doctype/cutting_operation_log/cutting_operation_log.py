# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CuttingOperationLog(Document):
	pass


@frappe.whitelist()
def generate_operation_id():
	"""Generate unique Operation ID in format CUT-####"""
	prefix = "CUT"
	# Get max existing number
	last_id = frappe.db.sql("""
		SELECT operation_id 
		FROM `tabCutting Operation Log` 
		WHERE operation_id LIKE %s 
		ORDER BY CAST(SUBSTRING_INDEX(operation_id, '-', -1) AS UNSIGNED) DESC 
		LIMIT 1
	""", (f"{prefix}-%",), as_dict=True)
	
	if last_id and last_id[0].get("operation_id"):
		last_num = int(last_id[0]["operation_id"].split("-")[1])
		new_num = last_num + 1
	else:
		new_num = 1
	
	return f"{prefix}-{new_num:04d}"
