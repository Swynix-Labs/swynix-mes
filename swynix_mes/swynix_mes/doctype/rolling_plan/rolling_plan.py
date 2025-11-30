# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class RollingPlan(Document):
	"""Rolling Plan document."""

	pass


@frappe.whitelist()
def generate_rolling_plan_id(coil: str) -> str:
	"""Generate a simple unique Rolling Plan ID based on Coil.

	Pattern: ROLL-<coil>-<####>
	"""
	if not coil:
		frappe.throw("Coil is required to generate Rolling Plan ID")

	seq = frappe.db.get_single_value("System Settings", "automatic_email_id") or 0
	try:
		seq = int(seq)
	except Exception:
		seq = 0

	seq += 1
	plan_id = f"ROLL-{coil}-{seq:04d}"

	return plan_id
