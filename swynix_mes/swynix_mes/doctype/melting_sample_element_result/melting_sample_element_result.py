# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class MeltingSampleElementResult(Document):
	"""
	Child table row for individual element QC results within a Spectro Sample.
	
	Each row represents one element's specification and measured value:
	- element: The element being measured (Link to Item, e.g., Si, Fe, Mn)
	- condition_type: Type of QC rule (Normal Limit, Sum Limit, Ratio, Remainder)
	- spec_min_pct / spec_max_pct: Specification limits from ACCM
	- sample_pct: Actual measured value from spectrometer/lab
	- in_spec: Whether the value passes the QC check
	- condition_violated: Description of any rule violation
	
	For Sum Limit rules:
	- sum_limit_pct stores the combined limit
	- Multiple elements participate in the sum calculation
	
	For Ratio rules:
	- ratio_value stores the expected ratio
	"""
	pass


