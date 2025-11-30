# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class PackingBatch(Document):
	"""Packing Batch document."""

	pass


@frappe.whitelist()
def load_items_from_source(source_doctype: str, source_name: str):
	"""Generic hook to pull items from a source document into Packing Batch.

	This is intentionally simple and can be extended per site needs.
	"""
	if not source_doctype or not source_name:
		frappe.throw("Source Doctype and Source Name are required")

	source_doc = frappe.get_doc(source_doctype, source_name)

	items = []
	for child_table_field in ("items", "wip_items", "finished_goods"):
		if hasattr(source_doc, child_table_field):
			for row in getattr(source_doc, child_table_field):
				items.append(
					{
						"item": getattr(row, "item", None),
						"source_reference": source_name,
						"qty": getattr(row, "qty", 0),
						"uom": getattr(row, "uom", None),
					}
				)
			if items:
				break

	return {"items": items}
