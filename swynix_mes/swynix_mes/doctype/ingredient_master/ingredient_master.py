# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class IngredientMaster(Document):
	def validate(self):
		self.validate_ingredient_name_length()
		self.sanitize_code()
		self.auto_generate_code()
		self.validate_allowed_item_groups()
		self.validate_duplicate_item_groups()
		self.validate_item_groups_exist()

	def validate_ingredient_name_length(self):
		"""Validate ingredient_name does not exceed 100 characters"""
		if self.ingredient_name and len(self.ingredient_name) > 100:
			frappe.throw(
				_("Ingredient Name must not exceed 100 characters. Current length: {0}").format(
					len(self.ingredient_name)
				)
			)

	def sanitize_code(self):
		"""Replace spaces with hyphens in code"""
		if self.code:
			self.code = self.code.replace(" ", "-").upper()

	def auto_generate_code(self):
		"""Automatically generate code if empty"""
		if not self.code:
			self.code = self.ingredient_name.upper().replace(" ", "-")

	def validate_allowed_item_groups(self):
		"""Must have at least ONE allowed item_group"""
		if not self.allowed_item_groups or len(self.allowed_item_groups) == 0:
			frappe.throw(
				_("At least one Item Group is required in the Allowed Item Groups table.")
			)

	def validate_duplicate_item_groups(self):
		"""Do not allow duplicate Item Groups within the child table"""
		seen_item_groups = set()
		for idx, row in enumerate(self.allowed_item_groups, start=1):
			if row.item_group in seen_item_groups:
				frappe.throw(
					_("Row {0}: Duplicate Item Group '{1}' is not allowed. Each Item Group can only be added once.").format(
						idx, row.item_group
					)
				)
			seen_item_groups.add(row.item_group)

	def validate_item_groups_exist(self):
		"""Validate that all mapped item_groups exist in ERPNext"""
		for idx, row in enumerate(self.allowed_item_groups, start=1):
			if row.item_group and not frappe.db.exists("Item Group", row.item_group):
				frappe.throw(
					_("Row {0}: Item Group '{1}' does not exist.").format(idx, row.item_group)
				)


@frappe.whitelist()
def get_ingredient_by_item_group(item_group):
	"""Get the Ingredient Master for a given Item Group.
	Used in Melting Batch validation and CMR validation.
	
	Args:
		item_group: Item Group name
	
	Returns:
		str: Ingredient Master name, or None if not found
	"""
	result = frappe.db.sql("""
		SELECT parent
		FROM `tabIngredient Item Group`
		WHERE item_group = %s
		AND EXISTS (
			SELECT 1 FROM `tabIngredient Master`
			WHERE name = `tabIngredient Item Group`.parent
			AND is_active = 1
		)
		LIMIT 1
	""", (item_group,), as_dict=True)
	
	if result:
		return result[0].parent
	return None


@frappe.whitelist()
def get_allowed_item_groups(ingredient_name):
	"""Get all allowed Item Groups for an Ingredient Master.
	Used for validation during charging.
	
	Args:
		ingredient_name: Ingredient Master name
	
	Returns:
		list: List of allowed Item Group names
	"""
	if not frappe.db.exists("Ingredient Master", ingredient_name):
		return []
	
	doc = frappe.get_doc("Ingredient Master", ingredient_name)
	return [row.item_group for row in doc.allowed_item_groups]


@frappe.whitelist()
def get_active_ingredients():
	"""Get all active Ingredient Masters with their allowed Item Groups.
	Used for CMR setup and validation.
	
	Returns:
		list: List of dicts with ingredient details
	"""
	ingredients = frappe.get_all(
		"Ingredient Master",
		filters={"is_active": 1},
		fields=["name", "ingredient_name", "code", "description"]
	)
	
	for ing in ingredients:
		ing["allowed_item_groups"] = frappe.get_all(
			"Ingredient Item Group",
			filters={"parent": ing["name"]},
			fields=["item_group", "mandatory", "remark"]
		)
	
	return ingredients








