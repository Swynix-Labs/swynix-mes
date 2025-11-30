# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FoilOperation(Document):
	"""Foil Operation document."""

	pass


@frappe.whitelist()
def load_from_reel(reel: str):
	"""Return basic data from Reel to prefill Foil Operation."""
	if not reel:
		frappe.throw("Reel is required")

	reel_doc = frappe.get_doc("Reel", reel)

	return {
		"width": getattr(reel_doc, "width", None),
		"thickness": getattr(reel_doc, "thickness", None),
		"coil": getattr(reel_doc, "coil", None),
	}
