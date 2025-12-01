# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FinishingProductionLog(Document):
	pass


@frappe.whitelist()
def generate_log_id():
	"""Generate unique Log ID in format FINISH-####"""
	prefix = "FINISH"
	# Get max existing number
	last_id = frappe.db.sql("""
		SELECT log_id 
		FROM `tabFinishing Production Log` 
		WHERE log_id LIKE %s 
		ORDER BY CAST(SUBSTRING_INDEX(log_id, '-', -1) AS UNSIGNED) DESC 
		LIMIT 1
	""", (f"{prefix}-%",), as_dict=True)
	
	if last_id and last_id[0].get("log_id"):
		last_num = int(last_id[0]["log_id"].split("-")[1])
		new_num = last_num + 1
	else:
		new_num = 1
	
	return f"{prefix}-{new_num:04d}"
