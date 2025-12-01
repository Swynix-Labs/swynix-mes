# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Reel(Document):
	pass


@frappe.whitelist()
def generate_reel_id():
	"""Generate unique Reel ID in format REEL-####"""
	prefix = "REEL"
	# Get max existing number
	last_id = frappe.db.sql("""
		SELECT reel_id 
		FROM `tabReel` 
		WHERE reel_id LIKE %s 
		ORDER BY CAST(SUBSTRING_INDEX(reel_id, '-', -1) AS UNSIGNED) DESC 
		LIMIT 1
	""", (f"{prefix}-%",), as_dict=True)
	
	if last_id and last_id[0].get("reel_id"):
		last_num = int(last_id[0]["reel_id"].split("-")[1])
		new_num = last_num + 1
	else:
		new_num = 1
	
	return f"{prefix}-{new_num:04d}"
