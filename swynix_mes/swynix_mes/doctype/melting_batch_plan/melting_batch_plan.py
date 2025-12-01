# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class MeltingBatchPlan(Document):

	@frappe.whitelist()
	def fetch_recipe_materials(self):
		"""Fetch materials from the selected Recipe Master for this document."""
		if not self.recipe:
			return {
				"success": False,
				"materials": [],
				"message": "No recipe selected",
			}

		try:
			# Get Recipe Master document
			recipe = frappe.get_doc("Recipe Master", self.recipe)

			materials = []

			# The child table in Recipe Master is called "compositions"
			if hasattr(recipe, "compositions") and recipe.compositions:
				for detail in recipe.compositions:
					materials.append(
						{
							"item": getattr(detail, "item", None),
							"source_type": getattr(detail, "source_type", None),
							"ratio": getattr(detail, "ratio", 0),
							"planned_qty": getattr(detail, "planned_qty", 0),
						}
					)

			return {
				"success": True,
				"materials": materials,
				"message": f"{len(materials)} materials fetched from recipe",
			}

		except Exception as e:
			frappe.log_error(
				f"Error in fetch_recipe_materials: {str(e)}", "Recipe Fetch Error"
			)
			return {
				"success": False,
				"materials": [],
				"message": str(e),
			}


@frappe.whitelist()
def generate_batch_plan_id():
	"""Generate unique Batch Plan ID in format MBPLAN-####"""
	prefix = "MBPLAN"
	# Get max existing number
	last_id = frappe.db.sql("""
		SELECT batch_plan_id 
		FROM `tabMelting Batch Plan` 
		WHERE batch_plan_id LIKE %s 
		ORDER BY CAST(SUBSTRING_INDEX(batch_plan_id, '-', -1) AS UNSIGNED) DESC 
		LIMIT 1
	""", (f"{prefix}-%",), as_dict=True)
	
	if last_id and last_id[0].get("batch_plan_id"):
		last_num = int(last_id[0]["batch_plan_id"].split("-")[1])
		new_num = last_num + 1
	else:
		new_num = 1
	
	return f"{prefix}-{new_num:04d}"
    