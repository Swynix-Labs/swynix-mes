# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from datetime import datetime


class Coil(Document):
	pass


@frappe.whitelist()
def generate_coil_id():
	"""Generate unique Coil ID in format COIL-YYYY-#####"""
	from datetime import datetime
	current_year = datetime.now().year
	prefix = f"COIL-{current_year}"
	
	max_num = 0
	
	# Check coil_id field
	coil_ids = frappe.db.sql("""
		SELECT coil_id 
		FROM `tabCoil` 
		WHERE coil_id LIKE %s 
		AND coil_id IS NOT NULL
		AND coil_id != ''
	""", (f"{prefix}-%",), as_dict=True)
	
	for row in coil_ids:
		if row.get("coil_id"):
			try:
				parts = row["coil_id"].split("-")
				if len(parts) >= 3:
					num = int(parts[-1])
					max_num = max(max_num, num)
			except (ValueError, IndexError):
				continue
	
	# Also check document name (autoname format: COIL-.YYYY.-.#####)
	doc_names = frappe.db.sql("""
		SELECT name 
		FROM `tabCoil` 
		WHERE name LIKE %s
	""", (f"{prefix}-%",), as_dict=True)
	
	for row in doc_names:
		if row.get("name"):
			try:
				parts = row["name"].split("-")
				if len(parts) >= 3:
					num = int(parts[-1])
					max_num = max(max_num, num)
			except (ValueError, IndexError):
				continue
	
	new_num = max_num + 1
	return f"{prefix}-{new_num:05d}"
