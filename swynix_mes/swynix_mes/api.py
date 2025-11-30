# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe


@frappe.whitelist()
def fetch_recipe_materials(recipe_name):
	"""
	Server Script for Fetching Recipe Materials
	Script Type: API
	API Method: swynix_mes.fetch_recipe_materials
	"""
	try:
		# Get Recipe Master document (ignore permissions)
		recipe = frappe.get_doc("Recipe Master", recipe_name, ignore_permissions=True)
		
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
		
		# Return the response
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

