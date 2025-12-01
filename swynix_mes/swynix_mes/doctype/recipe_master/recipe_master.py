# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class RecipeMaster(Document):
	pass


@frappe.whitelist()
def generate_recipe_id():
	"""Generate unique Recipe ID in format RECIPE-####"""
	prefix = "RECIPE"
	# Get max existing number
	last_id = frappe.db.sql("""
		SELECT recipe_id 
		FROM `tabRecipe Master` 
		WHERE recipe_id LIKE %s 
		ORDER BY CAST(SUBSTRING_INDEX(recipe_id, '-', -1) AS UNSIGNED) DESC 
		LIMIT 1
	""", (f"{prefix}-%",), as_dict=True)
	
	if last_id and last_id[0].get("recipe_id"):
		last_num = int(last_id[0]["recipe_id"].split("-")[1])
		new_num = last_num + 1
	else:
		new_num = 1
	
	return f"{prefix}-{new_num:04d}"
