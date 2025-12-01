# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CasterQCInspection(Document):
	pass


@frappe.whitelist()
def generate_qc_id():
	"""Generate unique QC ID in format QC-####"""
	prefix = "QC"
	# Get max existing number
	last_id = frappe.db.sql("""
		SELECT qc_id 
		FROM `tabCaster QC Inspection` 
		WHERE qc_id LIKE %s 
		ORDER BY CAST(SUBSTRING_INDEX(qc_id, '-', -1) AS UNSIGNED) DESC 
		LIMIT 1
	""", (f"{prefix}-%",), as_dict=True)
	
	if last_id and last_id[0].get("qc_id"):
		last_num = int(last_id[0]["qc_id"].split("-")[1])
		new_num = last_num + 1
	else:
		new_num = 1
	
	return f"{prefix}-{new_num:04d}"
