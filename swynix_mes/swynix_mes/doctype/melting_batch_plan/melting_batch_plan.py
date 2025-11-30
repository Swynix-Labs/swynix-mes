# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class MeltingBatchPlan(Document):
	@frappe.whitelist()
	def fetch_recipe_materials(self):
		"""Fetch materials from the selected Recipe Master"""
		if not self.recipe:
			return {
				'success': False,
				'materials': [],
				'message': 'No recipe selected'
			}
		
		try:
			# Get Recipe Master document
			recipe = frappe.get_doc("Recipe Master", self.recipe)
			
			materials = []
			
			# The child table in Recipe Master is called "compositions"
			if hasattr(recipe, 'compositions') and recipe.compositions:
				for detail in recipe.compositions:
					materials.append({
						'item': detail.item if hasattr(detail, 'item') else None,
						'source_type': detail.source_type if hasattr(detail, 'source_type') else None,
						'ratio': detail.ratio if hasattr(detail, 'ratio') else 0,
						'planned_qty': detail.planned_qty if hasattr(detail, 'planned_qty') else 0
					})
			
			return {
				'success': True,
				'materials': materials,
				'message': f'{len(materials)} materials fetched from recipe'
			}
			
		except Exception as e:
			frappe.log_error(f"Error in fetch_recipe_materials: {str(e)}", "Recipe Fetch Error")
			return {
				'success': False,
				'materials': [],
				'message': str(e)
			}
