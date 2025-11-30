__version__ = "0.0.1"

import frappe

# Re-export API method at app root so calls to `swynix_mes.fetch_recipe_materials`
# (used by old Server/Client Scripts) still work.
from .api import fetch_recipe_materials as _fetch_recipe_materials_impl


@frappe.whitelist()
def fetch_recipe_materials(recipe_name):
	"""Compatibility wrapper that forwards to `swynix_mes.api.fetch_recipe_materials`."""
	return _fetch_recipe_materials_impl(recipe_name)

