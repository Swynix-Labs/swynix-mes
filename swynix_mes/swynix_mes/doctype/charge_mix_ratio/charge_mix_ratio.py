# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ChargeMixRatio(Document):
	def validate(self):
		self.auto_generate_recipe_code()
		self.validate_alloy_item_group()
		self.validate_ingredients()
		self.auto_sequence_ingredients()
		self.validate_rules()

	def auto_generate_recipe_code(self):
		"""Auto-generate recipe_code if empty"""
		if not self.recipe_code:
			alloy_code = self.alloy or "ALLOY"
			revision = self.revision_no or "01"
			self.recipe_code = f"CMR-{alloy_code}-{revision}"

	def validate_alloy_item_group(self):
		"""Validate alloy belongs to Alloy item group"""
		if self.alloy:
			item_group = frappe.db.get_value("Item", self.alloy, "item_group")
			if item_group != "Alloy":
				frappe.throw(
					_("Alloy '{0}' must belong to Item Group 'Alloy'. Current: '{1}'").format(
						self.alloy, item_group
					)
				)

	def validate_ingredients(self):
		"""Validate all ingredient rows"""
		if not self.ingredients or len(self.ingredients) == 0:
			frappe.throw(_("At least one ingredient is required."))

		self.validate_no_duplicate_ingredients()
		self.validate_ingredient_percentages()
		self.validate_ingredient_item_group_mapping()
		self.validate_mandatory_ingredients()
		self.validate_total_percentage()

	def validate_no_duplicate_ingredients(self):
		"""No duplicate ingredient rows allowed"""
		seen_ingredients = set()
		for idx, row in enumerate(self.ingredients, start=1):
			key = (row.ingredient, row.item_group)
			if key in seen_ingredients:
				frappe.throw(
					_("Row {0}: Duplicate ingredient '{1}' with Item Group '{2}' is not allowed.").format(
						idx, row.ingredient, row.item_group
					)
				)
			seen_ingredients.add(key)

	def validate_ingredient_percentages(self):
		"""Validate percentage values based on proportion_type"""
		for idx, row in enumerate(self.ingredients, start=1):
			if row.proportion_type == "Exact":
				if row.exact_pct is None:
					frappe.throw(
						_("Row {0}: Exact % is required when Proportion Type is 'Exact'.").format(idx)
					)
				if row.exact_pct < 0 or row.exact_pct > 100:
					frappe.throw(
						_("Row {0}: Exact % must be between 0 and 100. Got: {1}").format(idx, row.exact_pct)
					)
			elif row.proportion_type == "Range":
				if row.min_pct is None or row.max_pct is None:
					frappe.throw(
						_("Row {0}: Both Min % and Max % are required when Proportion Type is 'Range'.").format(idx)
					)
				if row.min_pct < 0:
					frappe.throw(
						_("Row {0}: Min % cannot be negative. Got: {1}").format(idx, row.min_pct)
					)
				if row.max_pct > 100:
					frappe.throw(
						_("Row {0}: Max % cannot exceed 100. Got: {1}").format(idx, row.max_pct)
					)
				if row.min_pct >= row.max_pct:
					frappe.throw(
						_("Row {0}: Min % ({1}) must be less than Max % ({2}).").format(
							idx, row.min_pct, row.max_pct
						)
					)

	def validate_ingredient_item_group_mapping(self):
		"""Validate item_group is allowed for the selected ingredient"""
		for idx, row in enumerate(self.ingredients, start=1):
			if not row.ingredient or not row.item_group:
				continue

			# Get allowed item groups from Ingredient Master
			allowed_groups = frappe.db.sql("""
				SELECT item_group
				FROM `tabIngredient Item Group`
				WHERE parent = %s
			""", (row.ingredient,), as_dict=True)

			allowed_group_names = [g.item_group for g in allowed_groups]

			if row.item_group not in allowed_group_names:
				frappe.throw(
					_("Row {0}: Item Group '{1}' is not allowed for Ingredient '{2}'. "
					  "Allowed groups: {3}").format(
						idx, row.item_group, row.ingredient, ", ".join(allowed_group_names) or "None"
					)
				)

	def validate_mandatory_ingredients(self):
		"""If mandatory = 1, ingredient must have exact_pct > 0 OR min_pct > 0"""
		for idx, row in enumerate(self.ingredients, start=1):
			if row.mandatory:
				has_value = False
				if row.proportion_type == "Exact" and row.exact_pct and row.exact_pct > 0:
					has_value = True
				elif row.proportion_type == "Range" and row.min_pct and row.min_pct > 0:
					has_value = True

				if not has_value:
					frappe.throw(
						_("Row {0}: Ingredient '{1}' is marked as Mandatory but has no percentage value. "
						  "Set Exact % > 0 or Min % > 0.").format(idx, row.ingredient)
					)

	def validate_total_percentage(self):
		"""Sum of maximum percentages must not exceed 100"""
		total_max_pct = 0
		for row in self.ingredients:
			if row.proportion_type == "Exact":
				total_max_pct += row.exact_pct or 0
			elif row.proportion_type == "Range":
				total_max_pct += row.max_pct or 0

		if total_max_pct > 100:
			frappe.throw(
				_("Total of maximum percentages ({0}%) exceeds 100%. "
				  "Please adjust ingredient proportions.").format(total_max_pct)
			)

	def auto_sequence_ingredients(self):
		"""Auto-assign sequence numbers if empty"""
		for idx, row in enumerate(self.ingredients, start=1):
			if not row.sequence:
				row.sequence = idx * 10  # 10, 20, 30... for easy re-ordering

		# Sort by sequence
		self.ingredients = sorted(self.ingredients, key=lambda x: x.sequence or 0)

	def validate_rules(self):
		"""Validate rules table - ensure JSON is valid if provided"""
		import json
		for idx, row in enumerate(self.rules or [], start=1):
			if row.condition_json:
				try:
					json.loads(row.condition_json)
				except json.JSONDecodeError:
					frappe.throw(
						_("Row {0} in Rules: Invalid JSON in Condition JSON field.").format(idx)
					)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_allowed_item_groups_for_ingredient(doctype, txt, searchfield, start, page_len, filters):
	"""Get allowed Item Groups for an Ingredient Master.
	Used in item_group field query in Charge Mix Ratio Ingredient.
	"""
	ingredient = filters.get("ingredient")
	if not ingredient:
		return []

	return frappe.db.sql("""
		SELECT ig.item_group, ig.item_group as description
		FROM `tabIngredient Item Group` ig
		WHERE ig.parent = %s
		AND ig.item_group LIKE %s
		ORDER BY ig.item_group
		LIMIT %s, %s
	""", (ingredient, f"%{txt}%", start, page_len))


@frappe.whitelist()
def get_cmr_for_alloy(alloy, effective_date=None):
	"""Get the active Charge Mix Ratio for an alloy.
	Used in Melting Batch validation.
	
	Args:
		alloy: Item code of the alloy
		effective_date: Optional date to filter by effective_date
	
	Returns:
		dict: CMR document with ingredients and rules
	"""
	filters = {
		"alloy": alloy,
		"is_active": 1,
		"docstatus": 1
	}

	if effective_date:
		filters["effective_date"] = ["<=", effective_date]

	cmr_name = frappe.db.get_value(
		"Charge Mix Ratio",
		filters,
		"name",
		order_by="effective_date desc"
	)

	if cmr_name:
		return frappe.get_doc("Charge Mix Ratio", cmr_name)
	return None


@frappe.whitelist()
def validate_charge_mix(alloy, ingredients_json):
	"""Validate a proposed charge mix against the CMR.
	Used during live MES charging.
	
	Args:
		alloy: Item code of the alloy
		ingredients_json: JSON string of proposed ingredients
			Format: [{"ingredient": "...", "item_group": "...", "pct": 10.5}, ...]
	
	Returns:
		dict: {valid: bool, errors: list, warnings: list}
	"""
	import json

	result = {"valid": True, "errors": [], "warnings": []}

	try:
		proposed = json.loads(ingredients_json)
	except json.JSONDecodeError:
		return {"valid": False, "errors": ["Invalid JSON format"], "warnings": []}

	cmr = get_cmr_for_alloy(alloy)
	if not cmr:
		return {"valid": False, "errors": [f"No active Charge Mix Ratio found for alloy {alloy}"], "warnings": []}

	# Build CMR ingredient map
	cmr_map = {}
	for ing in cmr.ingredients:
		key = (ing.ingredient, ing.item_group)
		cmr_map[key] = ing

	# Validate each proposed ingredient
	for prop in proposed:
		key = (prop.get("ingredient"), prop.get("item_group"))
		pct = prop.get("pct", 0)

		if key not in cmr_map:
			result["warnings"].append(
				f"Ingredient {key[0]} with Item Group {key[1]} not in CMR"
			)
			continue

		cmr_ing = cmr_map[key]

		if cmr_ing.proportion_type == "Exact":
			if abs(pct - (cmr_ing.exact_pct or 0)) > 0.5:  # 0.5% tolerance
				result["warnings"].append(
					f"{cmr_ing.ingredient}: Expected {cmr_ing.exact_pct}%, got {pct}%"
				)
		elif cmr_ing.proportion_type == "Range":
			if pct < (cmr_ing.min_pct or 0):
				result["errors"].append(
					f"{cmr_ing.ingredient}: {pct}% is below minimum {cmr_ing.min_pct}%"
				)
				result["valid"] = False
			elif pct > (cmr_ing.max_pct or 100):
				result["errors"].append(
					f"{cmr_ing.ingredient}: {pct}% exceeds maximum {cmr_ing.max_pct}%"
				)
				result["valid"] = False

	# Check mandatory ingredients
	for ing in cmr.ingredients:
		if ing.mandatory:
			key = (ing.ingredient, ing.item_group)
			found = any(
				(p.get("ingredient"), p.get("item_group")) == key
				for p in proposed
			)
			if not found:
				result["errors"].append(
					f"Mandatory ingredient {ing.ingredient} ({ing.item_group}) is missing"
				)
				result["valid"] = False

	return result

