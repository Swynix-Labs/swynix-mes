# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AlloyChemicalCompositionMaster(Document):
	def validate(self):
		self.validate_single_active_per_alloy()
		self.validate_composition_rules()

	def validate_single_active_per_alloy(self):
		"""Ensure only one active record per alloy"""
		if self.is_active:
			existing = frappe.db.exists(
				"Alloy Chemical Composition Master",
				{
					"alloy": self.alloy,
					"is_active": 1,
					"name": ("!=", self.name)
				}
			)
			if existing:
				frappe.throw(
					_("An active Chemical Composition Master already exists for alloy {0}. "
					  "Please deactivate the existing record ({1}) before activating this one.").format(
						frappe.bold(self.alloy), frappe.bold(existing)
					)
				)

	def validate_composition_rules(self):
		"""Validate all composition rules in the child table"""
		if not self.composition_rules:
			frappe.throw(_("At least one composition rule is required."))

		seen_rules = {}

		for idx, d in enumerate(self.composition_rules, start=1):
			row_label = f"Row {idx}"

			# General validations
			self.validate_general_rule(d, row_label)

			# Condition-specific validations
			if d.condition_type == "Normal Limit":
				self.validate_normal_limit(d, row_label)
			elif d.condition_type == "Sum Limit":
				self.validate_sum_limit(d, row_label)
			elif d.condition_type == "Ratio":
				self.validate_ratio(d, row_label)
			elif d.condition_type == "Remainder":
				self.validate_remainder(d, row_label)
			elif d.condition_type == "Free Text":
				self.validate_free_text(d, row_label)

			# Duplicate detection
			self.check_duplicate_rule(d, row_label, seen_rules)

	def validate_general_rule(self, d, row_label):
		"""General validations applicable to all rule types"""
		if not d.element_1:
			frappe.throw(_("{0}: Element 1 is mandatory.").format(row_label))

		if not d.condition_type:
			frappe.throw(_("{0}: Condition Type is mandatory.").format(row_label))

		# Check for duplicate elements in the same row
		elements = [d.element_1]
		if d.element_2:
			if d.element_2 == d.element_1:
				frappe.throw(_("{0}: Element 2 cannot be the same as Element 1.").format(row_label))
			elements.append(d.element_2)

		if d.element_3:
			if d.element_3 in elements:
				frappe.throw(_("{0}: Element 3 must be different from Element 1 and Element 2.").format(row_label))

		# Validate numeric fields are non-negative
		numeric_fields = [
			("min_percentage", d.min_percentage),
			("max_percentage", d.max_percentage),
			("sum_min_percentage", d.sum_min_percentage),
			("sum_max_percentage", d.sum_max_percentage),
			("ratio_value_1", d.ratio_value_1),
			("ratio_value_2", d.ratio_value_2),
			("ratio_value_3", d.ratio_value_3),
			("remainder_min_percentage", d.remainder_min_percentage),
		]

		for field_name, value in numeric_fields:
			if value is not None and value < 0:
				frappe.throw(_("{0}: {1} cannot be negative.").format(row_label, field_name))

	def validate_normal_limit(self, d, row_label):
		"""Validate Normal Limit rules (single element)"""
		# Element 2 and 3 must be empty
		if d.element_2 or d.element_3:
			frappe.throw(_("{0}: Normal Limit rule must have only Element 1. Remove Element 2 and Element 3.").format(row_label))

		if not d.limit_type:
			frappe.throw(_("{0}: Limit Type is required for Normal Limit condition.").format(row_label))

		if d.limit_type == "Minimum":
			if not d.min_percentage and d.min_percentage != 0:
				frappe.throw(_("{0}: Min (%) is required when Limit Type is 'Minimum'.").format(row_label))
		elif d.limit_type == "Maximum":
			if not d.max_percentage and d.max_percentage != 0:
				frappe.throw(_("{0}: Max (%) is required when Limit Type is 'Maximum'.").format(row_label))
		elif d.limit_type == "Equal To":
			if not d.min_percentage and d.min_percentage != 0:
				frappe.throw(_("{0}: Value (%) is required when Limit Type is 'Equal To'.").format(row_label))
		elif d.limit_type == "Range":
			if (not d.min_percentage and d.min_percentage != 0) or (not d.max_percentage and d.max_percentage != 0):
				frappe.throw(_("{0}: Both Min and Max (%) are required when Limit Type is 'Range'.").format(row_label))
			if d.min_percentage >= d.max_percentage:
				frappe.throw(_("{0}: Min (%) must be less than Max (%).").format(row_label))

		# Sum limit, ratio, and remainder fields must be empty
		self.ensure_fields_empty(d, row_label, "Normal Limit", [
			("sum_limit_type", d.sum_limit_type),
			("sum_min_percentage", d.sum_min_percentage),
			("sum_max_percentage", d.sum_max_percentage),
			("ratio_value_1", d.ratio_value_1),
			("ratio_value_2", d.ratio_value_2),
			("ratio_value_3", d.ratio_value_3),
			("remainder_min_percentage", d.remainder_min_percentage),
		])

	def validate_sum_limit(self, d, row_label):
		"""Validate Sum Limit rules (2-3 elements)"""
		# At least 2 elements required
		if not d.element_2:
			frappe.throw(_("{0}: Sum Limit rule requires at least 2 elements. Element 2 is missing.").format(row_label))

		if not d.sum_limit_type:
			frappe.throw(_("{0}: Sum Limit Type is required for Sum Limit condition.").format(row_label))

		if d.sum_limit_type == "Minimum":
			if not d.sum_min_percentage and d.sum_min_percentage != 0:
				frappe.throw(_("{0}: Min (%) is required when Limit Type is 'Minimum'.").format(row_label))
		elif d.sum_limit_type == "Maximum":
			if not d.sum_max_percentage and d.sum_max_percentage != 0:
				frappe.throw(_("{0}: Max (%) is required when Limit Type is 'Maximum'.").format(row_label))
		elif d.sum_limit_type == "Equal To":
			if not d.sum_min_percentage and d.sum_min_percentage != 0:
				frappe.throw(_("{0}: Value (%) is required when Limit Type is 'Equal To'.").format(row_label))
		elif d.sum_limit_type == "Range":
			if (not d.sum_min_percentage and d.sum_min_percentage != 0) or (not d.sum_max_percentage and d.sum_max_percentage != 0):
				frappe.throw(_("{0}: Both Min and Max (%) are required when Limit Type is 'Range'.").format(row_label))
			if d.sum_min_percentage >= d.sum_max_percentage:
				frappe.throw(_("{0}: Min (%) must be less than Max (%).").format(row_label))

		# Normal limit, ratio, and remainder fields must be empty
		self.ensure_fields_empty(d, row_label, "Sum Limit", [
			("limit_type", d.limit_type),
			("min_percentage", d.min_percentage),
			("max_percentage", d.max_percentage),
			("ratio_value_1", d.ratio_value_1),
			("ratio_value_2", d.ratio_value_2),
			("ratio_value_3", d.ratio_value_3),
			("remainder_min_percentage", d.remainder_min_percentage),
		])

	def validate_ratio(self, d, row_label):
		"""Validate Ratio rules (2-3 elements)"""
		# At least 2 elements required
		if not d.element_2:
			frappe.throw(_("{0}: Ratio rule requires at least 2 elements. Element 2 is missing.").format(row_label))

		# Ratio values validation
		if not d.ratio_value_1 or d.ratio_value_1 <= 0:
			frappe.throw(_("{0}: Ratio Value 1 is required and must be greater than 0.").format(row_label))

		if not d.ratio_value_2 or d.ratio_value_2 <= 0:
			frappe.throw(_("{0}: Ratio Value 2 is required and must be greater than 0.").format(row_label))

		if d.element_3:
			if not d.ratio_value_3 or d.ratio_value_3 <= 0:
				frappe.throw(_("{0}: Ratio Value 3 is required when Element 3 is specified.").format(row_label))

		# Normal limit, sum limit, and remainder fields must be empty
		self.ensure_fields_empty(d, row_label, "Ratio", [
			("limit_type", d.limit_type),
			("min_percentage", d.min_percentage),
			("max_percentage", d.max_percentage),
			("sum_limit_type", d.sum_limit_type),
			("sum_min_percentage", d.sum_min_percentage),
			("sum_max_percentage", d.sum_max_percentage),
			("remainder_min_percentage", d.remainder_min_percentage),
		])

	def validate_remainder(self, d, row_label):
		"""Validate Remainder rules (typically for base metal like Aluminium)"""
		# Only element_1 is used
		if d.element_2 or d.element_3:
			frappe.throw(_("{0}: Remainder rule must have only Element 1 (base metal).").format(row_label))

		# remainder_min_percentage is optional (can be empty or set for minimum requirement)
		# All other numeric fields should be empty
		self.ensure_fields_empty(d, row_label, "Remainder", [
			("limit_type", d.limit_type),
			("min_percentage", d.min_percentage),
			("max_percentage", d.max_percentage),
			("sum_limit_type", d.sum_limit_type),
			("sum_min_percentage", d.sum_min_percentage),
			("sum_max_percentage", d.sum_max_percentage),
			("ratio_value_1", d.ratio_value_1),
			("ratio_value_2", d.ratio_value_2),
			("ratio_value_3", d.ratio_value_3),
		])

	def validate_free_text(self, d, row_label):
		"""Validate Free Text rules"""
		if not d.notes:
			frappe.throw(_("{0}: Notes is required for Free Text condition.").format(row_label))

		# Element 2 and 3 must be empty
		if d.element_2 or d.element_3:
			frappe.throw(_("{0}: Free Text rule must have only Element 1.").format(row_label))

		# All numeric fields must be empty
		self.ensure_fields_empty(d, row_label, "Free Text", [
			("limit_type", d.limit_type),
			("min_percentage", d.min_percentage),
			("max_percentage", d.max_percentage),
			("sum_limit_type", d.sum_limit_type),
			("sum_min_percentage", d.sum_min_percentage),
			("sum_max_percentage", d.sum_max_percentage),
			("ratio_value_1", d.ratio_value_1),
			("ratio_value_2", d.ratio_value_2),
			("ratio_value_3", d.ratio_value_3),
			("remainder_min_percentage", d.remainder_min_percentage),
		])

	def ensure_fields_empty(self, d, row_label, condition_type, fields):
		"""Helper to ensure certain fields are empty for a given condition type"""
		for field_name, value in fields:
			if value:
				frappe.throw(
					_("{0}: {1} should be empty for {2} condition.").format(
						row_label, field_name, condition_type
					)
				)

	def check_duplicate_rule(self, d, row_label, seen_rules):
		"""Check for duplicate rules within the same parent"""
		# Create a unique key based on condition type and elements
		elements = tuple(sorted(filter(None, [d.element_1, d.element_2, d.element_3])))

		if d.condition_type == "Normal Limit":
			# For Normal Limit: no two rows with same element_1 and same limit_type
			key = ("Normal Limit", d.element_1, d.limit_type)
			if key in seen_rules:
				frappe.throw(
					_("{0}: Duplicate Normal Limit rule for element '{1}' with limit type '{2}'. "
					  "See row {3}.").format(row_label, d.element_1, d.limit_type, seen_rules[key])
				)
			seen_rules[key] = row_label

		elif d.condition_type == "Sum Limit":
			# For Sum Limit: no two rows with same set of elements and same sum_limit_type
			key = ("Sum Limit", elements, d.sum_limit_type)
			if key in seen_rules:
				frappe.throw(
					_("{0}: Duplicate Sum Limit rule for elements {1} with sum limit type '{2}'. "
					  "See row {3}.").format(row_label, elements, d.sum_limit_type, seen_rules[key])
				)
			seen_rules[key] = row_label

		elif d.condition_type == "Ratio":
			# For Ratio: no two rows with same set of elements
			key = ("Ratio", elements)
			if key in seen_rules:
				frappe.throw(
					_("{0}: Duplicate Ratio rule for elements {1}. "
					  "See row {2}.").format(row_label, elements, seen_rules[key])
				)
			seen_rules[key] = row_label

		elif d.condition_type == "Remainder":
			# Only one remainder rule per element (typically just one for base metal)
			key = ("Remainder", d.element_1)
			if key in seen_rules:
				frappe.throw(
					_("{0}: Duplicate Remainder rule for element '{1}'. "
					  "See row {2}.").format(row_label, d.element_1, seen_rules[key])
				)
			seen_rules[key] = row_label

		elif d.condition_type == "Free Text":
			# Allow multiple free text rules, but warn if same element
			pass  # No duplicate check for Free Text


@frappe.whitelist()
def get_active_composition_master(alloy):
	"""Get the active Chemical Composition Master for an alloy.
	Used by QC validation logic.
	
	Args:
		alloy: Item code of the alloy
	
	Returns:
		dict: Composition master document with rules, or None if not found
	"""
	master_name = frappe.db.get_value(
		"Alloy Chemical Composition Master",
		{"alloy": alloy, "is_active": 1},
		"name"
	)

	if master_name:
		return frappe.get_doc("Alloy Chemical Composition Master", master_name)

	return None


@frappe.whitelist()
def get_composition_rules_for_alloy(alloy):
	"""Get all composition rules for an alloy in a format suitable for QC validation.
	
	Args:
		alloy: Item code of the alloy
	
	Returns:
		list: List of composition rules with all necessary fields
	"""
	master = get_active_composition_master(alloy)
	if not master:
		return []

	rules = []
	for rule in master.composition_rules:
		rules.append({
			"element_1": rule.element_1,
			"element_2": rule.element_2,
			"element_3": rule.element_3,
			"condition_type": rule.condition_type,
			"is_mandatory": rule.is_mandatory,
			"limit_type": rule.limit_type,
			"min_percentage": rule.min_percentage,
			"max_percentage": rule.max_percentage,
			"sum_limit_type": rule.sum_limit_type,
			"sum_min_percentage": rule.sum_min_percentage,
			"sum_max_percentage": rule.sum_max_percentage,
			"ratio_value_1": rule.ratio_value_1,
			"ratio_value_2": rule.ratio_value_2,
			"ratio_value_3": rule.ratio_value_3,
			"remainder_min_percentage": rule.remainder_min_percentage,
			"notes": rule.notes,
		})

	return rules
