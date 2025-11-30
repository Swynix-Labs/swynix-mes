__version__ = "0.0.1"

import frappe


@frappe.whitelist()
def fetch_recipe_materials(doc=None):
	"""Backward-compatible API for old calls to `swynix_mes.fetch_recipe_materials`.

	Expected to be called with `doc` representing a Melting Batch Plan document.
	`doc` can be:
	- a JSON string
	- a dict with doctype + name or full fields
	- a Document instance
	"""
	if not doc:
		frappe.throw("Missing document data for fetch_recipe_materials")

	# Allow JSON string
	if isinstance(doc, str):
		try:
			doc = frappe.parse_json(doc)
		except Exception:
			# If it's not JSON, assume it's a name of Melting Batch Plan
			return _fetch_from_melting_batch_plan_by_name(doc)

	# If dict, convert to Document
	if isinstance(doc, dict):
		if doc.get("doctype") and doc.get("name"):
			doc = frappe.get_doc(doc.get("doctype"), doc.get("name"))
		else:
			doc = frappe.get_doc(doc)

	# If we already have a Document instance
	from swynix_mes.swynix_mes.doctype.melting_batch_plan.melting_batch_plan import (
		MeltingBatchPlan,
	)

	if isinstance(doc, MeltingBatchPlan):
		return doc.fetch_recipe_materials()

	# If it's some other doctype but has recipe + same method, try calling it
	if hasattr(doc, "fetch_recipe_materials"):
		return doc.fetch_recipe_materials()

	frappe.throw(
		f"fetch_recipe_materials is not supported for doctype {getattr(doc, 'doctype', type(doc))}"
	)


def _fetch_from_melting_batch_plan_by_name(name: str):
	"""Helper for when only a name is passed."""
	if not name:
		frappe.throw("Missing Melting Batch Plan name")

	doc = frappe.get_doc("Melting Batch Plan", name)
	return doc.fetch_recipe_materials()