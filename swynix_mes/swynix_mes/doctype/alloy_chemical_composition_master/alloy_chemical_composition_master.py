# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _


class AlloyChemicalCompositionMaster(Document):
	def validate(self):
		# Ensure only one active record per alloy
		if self.is_active:
			existing_active = frappe.db.exists(
				"Alloy Chemical Composition Master",
				{
					"alloy": self.alloy,
					"is_active": 1,
					"name": ["!=", self.name]
				}
			)
			if existing_active:
				frappe.throw(
					_("An active composition record already exists for alloy {0}. Please deactivate it first.").format(
						frappe.bold(self.alloy)
					)
				)
		
		# Validate composition details
		if not self.composition_details:
			frappe.throw(_("At least one composition rule is required."))
		
		# Track seen rules for duplicate prevention
		seen_rules = []
		
		# Validate each composition detail based on condition type
		for idx, detail in enumerate(self.composition_details, start=1):
			self.validate_composition_detail(detail, idx)
			
			# Check for duplicate rules
			rule_signature = self.get_rule_signature(detail)
			if rule_signature in seen_rules:
				frappe.throw(
					_("Row {0}: Duplicate rule detected. The same combination of elements and condition type already exists in another row.").format(idx)
				)
			seen_rules.append(rule_signature)
	
	def get_rule_signature(self, detail):
		"""Create a unique signature for a rule to detect duplicates"""
		# Normalize element list (sort and filter empty)
		elements = sorted([e for e in [detail.element_1, detail.element_2, detail.element_3] if e])
		return (
			tuple(elements),
			detail.condition_type,
			detail.limit_type if detail.condition_type == "Normal Limit" else None
		)
	
	def validate_composition_detail(self, detail, row_num):
		"""Validate composition detail based on condition type"""
		row_prefix = _("Row {0}").format(row_num)
		
		# General validations
		if not detail.element_1:
			frappe.throw(_("{0}: Element 1 is mandatory.").format(row_prefix))
		
		# Count elements
		element_count = len([e for e in [detail.element_1, detail.element_2, detail.element_3] if e])
		
		# Validate numeric values are non-negative
		numeric_fields = [
			("min_percentage", detail.min_percentage),
			("max_percentage", detail.max_percentage),
			("sum_min_percentage", detail.sum_min_percentage),
			("sum_max_percentage", detail.sum_max_percentage),
			("ratio_value_1", detail.ratio_value_1),
			("ratio_value_2", detail.ratio_value_2),
			("ratio_value_3", detail.ratio_value_3)
		]
		
		for field_name, field_value in numeric_fields:
			if field_value is not None and field_value < 0:
				frappe.throw(_("{0}: {1} cannot be negative.").format(row_prefix, field_name.replace("_", " ").title()))
		
		# Condition-specific validations
		if detail.condition_type == "Normal Limit":
			self.validate_normal_limit(detail, row_prefix, element_count)
		
		elif detail.condition_type == "Sum Limit":
			self.validate_sum_limit(detail, row_prefix, element_count)
		
		elif detail.condition_type == "Ratio":
			self.validate_ratio(detail, row_prefix, element_count)
		
		elif detail.condition_type == "Remainder":
			self.validate_remainder(detail, row_prefix, element_count)
		
		elif detail.condition_type == "Free Text":
			self.validate_free_text(detail, row_prefix, element_count)
		
		else:
			frappe.throw(_("{0}: Invalid condition type '{1}'.").format(row_prefix, detail.condition_type))
	
	def validate_normal_limit(self, detail, row_prefix, element_count):
		"""Validate Normal Limit condition"""
		# Normal Limit must have only Element 1
		if element_count > 1:
			frappe.throw(_("{0}: Normal Limit condition requires only Element 1. Element 2 and Element 3 must be empty.").format(row_prefix))
		
		if detail.element_2 or detail.element_3:
			frappe.throw(_("{0}: Element 2 and Element 3 must be empty for Normal Limit condition.").format(row_prefix))
		
		if not detail.limit_type:
			frappe.throw(_("{0}: Limit Type is required when Condition Type is 'Normal Limit'.").format(row_prefix))
		
		# Validate sum and ratio fields are empty
		if detail.sum_limit_type:
			frappe.throw(_("{0}: Sum Limit Type must be empty for Normal Limit condition.").format(row_prefix))
		
		if detail.sum_min_percentage or detail.sum_max_percentage:
			frappe.throw(_("{0}: Sum Min and Sum Max Percentage must be empty for Normal Limit condition.").format(row_prefix))
		
		if detail.ratio_value_1 or detail.ratio_value_2 or detail.ratio_value_3:
			frappe.throw(_("{0}: Ratio values must be empty for Normal Limit condition.").format(row_prefix))
		
		# Validate based on limit type
		if detail.limit_type == "Minimum":
			if not detail.min_percentage:
				frappe.throw(_("{0}: Min Percentage is required when Limit Type is 'Minimum'.").format(row_prefix))
			if detail.max_percentage:
				frappe.throw(_("{0}: Max Percentage must be empty when Limit Type is 'Minimum'.").format(row_prefix))
		
		elif detail.limit_type == "Maximum":
			if not detail.max_percentage:
				frappe.throw(_("{0}: Max Percentage is required when Limit Type is 'Maximum'.").format(row_prefix))
			if detail.min_percentage:
				frappe.throw(_("{0}: Min Percentage must be empty when Limit Type is 'Maximum'.").format(row_prefix))
		
		elif detail.limit_type == "Range":
			if not detail.min_percentage or not detail.max_percentage:
				frappe.throw(_("{0}: Both Min and Max Percentage are required when Limit Type is 'Range'.").format(row_prefix))
			
			if detail.min_percentage >= detail.max_percentage:
				frappe.throw(_("{0}: Min Percentage ({1}%) must be less than Max Percentage ({2}%).").format(
					row_prefix, detail.min_percentage, detail.max_percentage
				))
		
		else:
			frappe.throw(_("{0}: Invalid Limit Type '{1}' for Normal Limit condition.").format(row_prefix, detail.limit_type))
	
	def validate_sum_limit(self, detail, row_prefix, element_count):
		"""Validate Sum Limit condition"""
		# Sum Limit requires at least 2 elements
		if element_count < 2:
			frappe.throw(_("{0}: Sum Limit condition requires at least Element 1 and Element 2.").format(row_prefix))
		
		if not detail.element_2:
			frappe.throw(_("{0}: Element 2 is required when Condition Type is 'Sum Limit'.").format(row_prefix))
		
		if not detail.sum_limit_type:
			frappe.throw(_("{0}: Sum Limit Type is required when Condition Type is 'Sum Limit'.").format(row_prefix))
		
		# Validate based on sum_limit_type
		if detail.sum_limit_type == "Minimum":
			if not detail.sum_min_percentage:
				frappe.throw(_("{0}: Sum Min Percentage is required when Sum Limit Type is 'Minimum'.").format(row_prefix))
			if detail.sum_max_percentage:
				frappe.throw(_("{0}: Sum Max Percentage must be empty when Sum Limit Type is 'Minimum'.").format(row_prefix))
		
		elif detail.sum_limit_type == "Maximum":
			if not detail.sum_max_percentage:
				frappe.throw(_("{0}: Sum Max Percentage is required when Sum Limit Type is 'Maximum'.").format(row_prefix))
			if detail.sum_min_percentage:
				frappe.throw(_("{0}: Sum Min Percentage must be empty when Sum Limit Type is 'Maximum'.").format(row_prefix))
		
		elif detail.sum_limit_type == "Range":
			if not detail.sum_min_percentage or not detail.sum_max_percentage:
				frappe.throw(_("{0}: Both Sum Min and Sum Max Percentage are required when Sum Limit Type is 'Range'.").format(row_prefix))
			
			if detail.sum_min_percentage >= detail.sum_max_percentage:
				frappe.throw(_("{0}: Sum Min Percentage ({1}%) must be less than Sum Max Percentage ({2}%).").format(
					row_prefix, detail.sum_min_percentage, detail.sum_max_percentage
				))
		
		else:
			frappe.throw(_("{0}: Invalid Sum Limit Type '{1}' for Sum Limit condition.").format(row_prefix, detail.sum_limit_type))
		
		# Validate limit type and min/max are empty
		if detail.limit_type:
			frappe.throw(_("{0}: Limit Type must be empty for Sum Limit condition.").format(row_prefix))
		
		if detail.min_percentage or detail.max_percentage:
			frappe.throw(_("{0}: Min and Max Percentage must be empty for Sum Limit condition.").format(row_prefix))
		
		# Validate ratio fields are empty
		if detail.ratio_value_1 or detail.ratio_value_2 or detail.ratio_value_3:
			frappe.throw(_("{0}: Ratio values must be empty for Sum Limit condition.").format(row_prefix))
	
	def validate_ratio(self, detail, row_prefix, element_count):
		"""Validate Ratio condition"""
		# Ratio requires at least 2 elements
		if element_count < 2:
			frappe.throw(_("{0}: Ratio condition requires at least Element 1 and Element 2.").format(row_prefix))
		
		if not detail.element_2:
			frappe.throw(_("{0}: Element 2 is required when Condition Type is 'Ratio'.").format(row_prefix))
		
		# Validate ratio values match element count
		if not detail.ratio_value_1:
			frappe.throw(_("{0}: Ratio Value 1 is required when Condition Type is 'Ratio'.").format(row_prefix))
		
		if element_count >= 2 and not detail.ratio_value_2:
			frappe.throw(_("{0}: Ratio Value 2 is required when Element 2 is specified.").format(row_prefix))
		
		if element_count >= 3:
			if not detail.ratio_value_3:
				frappe.throw(_("{0}: Ratio Value 3 is required when Element 3 is specified.").format(row_prefix))
		else:
			if detail.ratio_value_3:
				frappe.throw(_("{0}: Ratio Value 3 must be empty when Element 3 is not specified.").format(row_prefix))
		
		# Validate no zero denominators
		if detail.ratio_value_2 == 0:
			frappe.throw(_("{0}: Ratio Value 2 (Denominator) cannot be zero.").format(row_prefix))
		
		if detail.ratio_value_3 == 0:
			frappe.throw(_("{0}: Ratio Value 3 cannot be zero.").format(row_prefix))
		
		# Validate limit type and min/max are empty
		if detail.limit_type:
			frappe.throw(_("{0}: Limit Type must be empty for Ratio condition.").format(row_prefix))
		
		if detail.min_percentage or detail.max_percentage:
			frappe.throw(_("{0}: Min and Max Percentage must be empty for Ratio condition.").format(row_prefix))
		
		# Validate sum limit fields are empty
		if detail.sum_limit_type:
			frappe.throw(_("{0}: Sum Limit Type must be empty for Ratio condition.").format(row_prefix))
		
		if detail.sum_min_percentage or detail.sum_max_percentage:
			frappe.throw(_("{0}: Sum Min and Sum Max Percentage must be empty for Ratio condition.").format(row_prefix))
	
	def validate_remainder(self, detail, row_prefix, element_count):
		"""Validate Remainder condition"""
		# Remainder requires only Element 1
		if element_count > 1:
			frappe.throw(_("{0}: Remainder condition requires only Element 1. Element 2 and Element 3 must be empty.").format(row_prefix))
		
		if detail.element_2 or detail.element_3:
			frappe.throw(_("{0}: Element 2 and Element 3 must be empty for Remainder condition.").format(row_prefix))
		
		# Validate other fields are empty
		if detail.limit_type:
			frappe.throw(_("{0}: Limit Type must be empty for Remainder condition.").format(row_prefix))
		
		if detail.max_percentage:
			frappe.throw(_("{0}: Max Percentage must be empty for Remainder condition.").format(row_prefix))
		
		if detail.sum_limit_type:
			frappe.throw(_("{0}: Sum Limit Type must be empty for Remainder condition.").format(row_prefix))
		
		if detail.sum_min_percentage or detail.sum_max_percentage:
			frappe.throw(_("{0}: Sum Min and Sum Max Percentage must be empty for Remainder condition.").format(row_prefix))
		
		if detail.ratio_value_1 or detail.ratio_value_2 or detail.ratio_value_3:
			frappe.throw(_("{0}: Ratio values must be empty for Remainder condition.").format(row_prefix))
		
		# min_percentage is optional for Remainder, so no validation needed
	
	def validate_free_text(self, detail, row_prefix, element_count):
		"""Validate Free Text condition"""
		# Free Text requires only Element 1
		if element_count > 1:
			frappe.throw(_("{0}: Free Text condition requires only Element 1. Element 2 and Element 3 must be empty.").format(row_prefix))
		
		if detail.element_2 or detail.element_3:
			frappe.throw(_("{0}: Element 2 and Element 3 must be empty for Free Text condition.").format(row_prefix))
		
		if not detail.notes:
			frappe.throw(_("{0}: Notes are required when Condition Type is 'Free Text'.").format(row_prefix))
		
		# Validate all numeric fields are empty
		if detail.limit_type:
			frappe.throw(_("{0}: Limit Type must be empty for Free Text condition.").format(row_prefix))
		
		if detail.min_percentage or detail.max_percentage:
			frappe.throw(_("{0}: Min and Max Percentage must be empty for Free Text condition.").format(row_prefix))
		
		if detail.sum_limit_type:
			frappe.throw(_("{0}: Sum Limit Type must be empty for Free Text condition.").format(row_prefix))
		
		if detail.sum_min_percentage or detail.sum_max_percentage:
			frappe.throw(_("{0}: Sum Min and Sum Max Percentage must be empty for Free Text condition.").format(row_prefix))
		
		if detail.ratio_value_1 or detail.ratio_value_2 or detail.ratio_value_3:
			frappe.throw(_("{0}: Ratio values must be empty for Free Text condition.").format(row_prefix))