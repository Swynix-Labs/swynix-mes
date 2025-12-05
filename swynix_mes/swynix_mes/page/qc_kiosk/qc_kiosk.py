# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

"""
QC Kiosk Page Backend

Provides whitelisted methods for:
- Getting pending/recent samples for QC review
- Getting detailed sample information with spec comparison
- Updating sample results and triggering actions
"""

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, getdate, get_datetime


# Element field mapping in Melting Batch Spectro Sample
ELEMENT_FIELDS = {
    "Si": "si_percent",
    "Fe": "fe_percent",
    "Cu": "cu_percent",
    "Mn": "mn_percent",
    "Mg": "mg_percent",
    "Zn": "zn_percent",
    "Ti": "ti_percent",
    "Al": "al_percent",
}

# Reverse mapping
FIELD_TO_ELEMENT = {v: k for k, v in ELEMENT_FIELDS.items()}


def get_context(context):
    """Get context for page template."""
    context.no_cache = 1


def get_element_code_from_item(item_name):
    """Extract element symbol from item name."""
    if not item_name:
        return None
    
    symbols = {
        "silicon": "Si", "si": "Si",
        "iron": "Fe", "fe": "Fe",
        "copper": "Cu", "cu": "Cu",
        "manganese": "Mn", "mn": "Mn",
        "magnesium": "Mg", "mg": "Mg",
        "zinc": "Zn", "zn": "Zn",
        "titanium": "Ti", "ti": "Ti",
        "aluminium": "Al", "aluminum": "Al", "al": "Al",
    }
    
    item_lower = item_name.strip().lower()
    if item_lower in symbols:
        return symbols[item_lower]
    
    if len(item_name) <= 2:
        return item_name.capitalize()
    
    for key, symbol in symbols.items():
        if key in item_lower:
            return symbol
    
    return item_name


@frappe.whitelist()
def get_pending_samples(filters=None):
    """
    Get pending/recent spectro samples for QC review.
    
    Args:
        filters: JSON dict with optional keys:
            - from_date: Start date filter
            - to_date: End date filter
            - alloy: Filter by alloy
            - status: Filter by sample status (Pending, Approved, Rejected, Correction Required)
            - batch: Filter by specific Melting Batch name
            
    Returns:
        list of sample dicts with batch info and element readings
    """
    import json
    
    if isinstance(filters, str):
        filters = json.loads(filters)
    
    filters = frappe._dict(filters or {})
    
    # Build batch filters
    batch_filters = {
        "docstatus": ["<", 2]  # Not cancelled
    }
    
    if filters.get("alloy"):
        batch_filters["alloy"] = filters.alloy
    
    if filters.get("batch"):
        batch_filters["name"] = filters.batch
    
    # Get batches
    batches = frappe.get_all(
        "Melting Batch",
        filters=batch_filters,
        fields=[
            "name", "melting_batch_id", "alloy", "product_item", 
            "furnace", "temper", "charge_mix_recipe", "status",
            "ppc_casting_plan", "qc_status"
        ],
        order_by="creation desc",
        limit=100
    )
    
    if not batches:
        return []
    
    batch_names = [b.name for b in batches]
    batch_map = {b.name: b for b in batches}
    
    # Build sample filters
    sample_filters = {
        "parent": ["in", batch_names],
        "parenttype": "Melting Batch"
    }
    
    # Date filters on sample_time
    if filters.get("from_date"):
        from_dt = f"{filters.from_date} 00:00:00"
        sample_filters["sample_time"] = [">=", from_dt]
    
    if filters.get("to_date"):
        to_dt = f"{filters.to_date} 23:59:59"
        if "sample_time" in sample_filters:
            sample_filters["sample_time"] = ["between", [f"{filters.from_date} 00:00:00", to_dt]]
        else:
            sample_filters["sample_time"] = ["<=", to_dt]
    
    # Status filter - check both new 'status' field and legacy 'result_status'
    if filters.get("status") and filters.status != "All":
        status_val = filters.status
        # Map display status to field values
        status_map = {
            "Pending": ["Pending", "In Lab"],
            "Approved": ["Accepted", "Within Limit"],
            "Rejected": ["Rejected", "Out of Limit"],
            "Correction Required": ["Correction Required"]
        }
        if status_val in status_map:
            sample_filters["status"] = ["in", status_map[status_val]]
    
    # Get samples with all fields
    samples = frappe.db.sql("""
        SELECT
            s.name,
            s.parent,
            s.sample_id,
            s.sample_time,
            s.status,
            s.overall_result,
            s.result_status,
            s.correction_required,
            s.remarks,
            s.spec_master,
            s.si_percent,
            s.fe_percent,
            s.cu_percent,
            s.mn_percent,
            s.mg_percent,
            s.zn_percent,
            s.ti_percent,
            s.al_percent
        FROM `tabMelting Batch Spectro Sample` s
        WHERE s.parent IN %(batch_names)s
        AND s.parenttype = 'Melting Batch'
        ORDER BY s.sample_time DESC
    """, {"batch_names": batch_names}, as_dict=True)
    
    # Filter by date if needed (SQL didn't handle it)
    if filters.get("from_date") or filters.get("to_date"):
        filtered_samples = []
        from_dt = get_datetime(f"{filters.from_date} 00:00:00") if filters.get("from_date") else None
        to_dt = get_datetime(f"{filters.to_date} 23:59:59") if filters.get("to_date") else None
        
        for s in samples:
            if s.sample_time:
                sample_dt = get_datetime(s.sample_time)
                if from_dt and sample_dt < from_dt:
                    continue
                if to_dt and sample_dt > to_dt:
                    continue
            filtered_samples.append(s)
        samples = filtered_samples
    
    # Filter by status if needed
    if filters.get("status") and filters.status != "All":
        status_val = filters.status
        status_map = {
            "Pending": ["Pending", "In Lab", None, ""],
            "Approved": ["Accepted", "Within Limit", "Approved"],
            "Rejected": ["Rejected", "Out of Limit"],
            "Correction Required": ["Correction Required"]
        }
        if status_val in status_map:
            allowed = status_map[status_val]
            samples = [s for s in samples if (s.status in allowed or s.result_status in allowed)]
    
    # Build result
    result = []
    for s in samples:
        batch = batch_map.get(s.parent)
        if not batch:
            continue
        
        # Build elements dict
        elements = {}
        for elem, field in ELEMENT_FIELDS.items():
            val = s.get(field)
            if val is not None:
                elements[elem] = flt(val, 4)
        
        # Get ACCM name if available
        accm_name = None
        if batch.alloy:
            accm_name = frappe.db.get_value(
                "Alloy Chemical Composition Master",
                {"alloy": batch.alloy, "is_active": 1},
                "name"
            )
        
        # Determine display status
        display_status = s.status or s.result_status or "Pending"
        if display_status == "Within Limit":
            display_status = "Approved"
        elif display_status == "Out of Limit":
            display_status = "Rejected"
        elif display_status == "Accepted":
            display_status = "Approved"
        elif display_status == "In Lab":
            display_status = "Pending"
        
        result.append({
            "name": s.name,
            "melting_batch": s.parent,
            "batch_id": batch.melting_batch_id or s.parent,
            "sample_id": s.sample_id,
            "sample_time": str(s.sample_time) if s.sample_time else None,
            "alloy": batch.alloy,
            "product": batch.product_item,
            "furnace": batch.furnace,
            "status": display_status,
            "overall_result": s.overall_result,
            "correction_required": s.correction_required,
            "elements": elements,
            "accm_name": accm_name,
            "casting_plan": batch.ppc_casting_plan,
            "temper": batch.temper,
            "recipe": batch.charge_mix_recipe,
            "batch_status": batch.status,
            "batch_qc_status": batch.qc_status
        })
    
    return result


@frappe.whitelist()
def get_sample_details(batch, sample_id):
    """
    Get detailed sample information with spec comparison.
    
    Uses the composition_check utility for comprehensive evaluation of:
    - Normal Limit: Single element range checks
    - Sum Limit: Sum of multiple elements against limit
    - Ratio: Ratio between two elements
    - Remainder: Aluminium minimum % or remainder conditions
    
    Args:
        batch: Melting Batch name
        sample_id: Sample ID (e.g., "S1", "S2")
        
    Returns:
        dict with:
        - batch_info: Basic batch information
        - sample_info: Sample row data
        - spec_table: Element specifications from ACCM
        - element_results: Element readings with spec comparison
        - failed_rules: List of failed specification rules with human-readable messages
        - deviation_messages: List of deviation messages for UI display
        - overall_status: Pending / OK / Out of Spec
    """
    from swynix_mes.swynix_mes.utils.composition_check import (
        evaluate_sample_against_alloy,
        get_element_code,
        get_active_composition_master
    )
    
    if not batch or not sample_id:
        frappe.throw(_("Batch and Sample ID are required"))
    
    # Load batch
    try:
        batch_doc = frappe.get_doc("Melting Batch", batch)
    except frappe.DoesNotExistError:
        frappe.throw(_("Melting Batch {0} not found").format(batch))
    
    # Find sample row
    sample_row = None
    for s in batch_doc.spectro_samples:
        if s.sample_id == sample_id:
            sample_row = s
            break
    
    if not sample_row:
        frappe.throw(_("Sample {0} not found in batch {1}").format(sample_id, batch))
    
    # Build batch info
    batch_info = {
        "name": batch_doc.name,
        "batch_id": batch_doc.melting_batch_id or batch_doc.name,
        "alloy": batch_doc.alloy,
        "product": batch_doc.product_item,
        "furnace": batch_doc.furnace,
        "temper": batch_doc.temper,
        "recipe": batch_doc.charge_mix_recipe,
        "casting_plan": batch_doc.ppc_casting_plan,
        "status": batch_doc.status,
        "qc_status": batch_doc.qc_status
    }
    
    # Build sample info
    sample_info = {
        "name": sample_row.name,
        "sample_id": sample_row.sample_id,
        "sample_time": str(sample_row.sample_time) if sample_row.sample_time else None,
        "status": sample_row.status or sample_row.result_status or "Pending",
        "overall_result": getattr(sample_row, "overall_result", None),
        "correction_required": sample_row.correction_required,
        "remarks": sample_row.remarks,
        "spec_master": getattr(sample_row, "spec_master", None)
    }
    
    # Get current element readings
    current_readings = {}
    for elem, field in ELEMENT_FIELDS.items():
        val = getattr(sample_row, field, None)
        if val is not None:
            current_readings[elem] = flt(val, 4)
    
    # Load ACCM for spec
    accm = None
    accm_name = None
    spec_table = []
    
    if batch_doc.alloy:
        accm = get_active_composition_master(batch_doc.alloy)
        if accm:
            accm_name = accm.name
    
    # Use composition_check utility for comprehensive evaluation
    eval_result = evaluate_sample_against_alloy(batch_doc.alloy, current_readings)
    
    # Build spec table from ACCM rules
    element_specs = {}  # {element_code: {min, max, condition_text}}
    sum_rules = []
    ratio_rules = []
    
    if accm:
        for rule in accm.composition_rules or []:
            condition_type = rule.condition_type
            element_1 = rule.element_1
            element_2 = rule.element_2
            element_3 = getattr(rule, "element_3", None)
            
            elem_code = get_element_code(element_1) if element_1 else None
            elem2_code = get_element_code(element_2) if element_2 else None
            elem3_code = get_element_code(element_3) if element_3 else None
            
            if condition_type == "Normal Limit":
                spec_entry = {
                    "element": elem_code,
                    "element_item": element_1,
                    "condition_type": condition_type,
                    "limit_type": rule.limit_type,
                    "min_pct": rule.min_percentage,
                    "max_pct": rule.max_percentage,
                    "condition_text": build_condition_text(rule)
                }
                spec_table.append(spec_entry)
                
                if elem_code:
                    element_specs[elem_code] = {
                        "min": rule.min_percentage,
                        "max": rule.max_percentage,
                        "limit_type": rule.limit_type
                    }
                    
            elif condition_type == "Sum Limit":
                # Build element label for sum
                sum_elements = [e for e in [elem_code, elem2_code, elem3_code] if e]
                sum_label = "+".join(sum_elements)
                
                sum_entry = {
                    "element": sum_label,
                    "element_1": elem_code,
                    "element_2": elem2_code,
                    "element_3": elem3_code,
                    "elements": sum_elements,
                    "condition_type": condition_type,
                    "limit_type": rule.sum_limit_type,
                    "min_pct": rule.sum_min_percentage,
                    "max_pct": rule.sum_max_percentage,
                    "condition_text": build_sum_condition_text(rule)
                }
                spec_table.append(sum_entry)
                sum_rules.append(sum_entry)
                
            elif condition_type == "Ratio":
                ratio_entry = {
                    "element": f"{elem_code}/{elem2_code}" if elem2_code else elem_code,
                    "element_1": elem_code,
                    "element_2": elem2_code,
                    "condition_type": condition_type,
                    "ratio_1": rule.ratio_value_1,
                    "ratio_2": rule.ratio_value_2,
                    "condition_text": build_ratio_condition_text(rule)
                }
                spec_table.append(ratio_entry)
                ratio_rules.append(ratio_entry)
                
            elif condition_type == "Remainder":
                spec_entry = {
                    "element": elem_code,
                    "element_item": element_1,
                    "condition_type": condition_type,
                    "limit_type": "Minimum",
                    "min_pct": rule.remainder_min_percentage,
                    "max_pct": None,
                    "condition_text": f"Remainder ≥ {rule.remainder_min_percentage}%" if rule.remainder_min_percentage else "Remainder"
                }
                spec_table.append(spec_entry)
                
                if elem_code:
                    element_specs[elem_code] = {
                        "min": rule.remainder_min_percentage,
                        "max": None,
                        "limit_type": "Minimum"
                    }
    
    # Build element results with spec comparison (for Normal Limit rules only in the table)
    element_results = []
    failed_rules = []
    has_readings = False
    
    for elem in ["Si", "Fe", "Cu", "Mn", "Mg", "Zn", "Ti", "Al"]:
        actual = current_readings.get(elem)
        spec = element_specs.get(elem, {})
        
        lower_limit = spec.get("min")
        upper_limit = spec.get("max")
        limit_type = spec.get("limit_type", "Range")
        
        within_spec = None
        if actual is not None:
            has_readings = True
            within_spec = check_within_spec(actual, lower_limit, upper_limit, limit_type)
        
        # Build spec text
        spec_text = "-"
        if lower_limit is not None and upper_limit is not None:
            spec_text = f"{flt(lower_limit, 4)} – {flt(upper_limit, 4)}"
        elif lower_limit is not None:
            spec_text = f"≥ {flt(lower_limit, 4)}"
        elif upper_limit is not None:
            spec_text = f"≤ {flt(upper_limit, 4)}"
        
        element_results.append({
            "element": elem,
            "spec_text": spec_text,
            "lower_limit": lower_limit,
            "upper_limit": upper_limit,
            "actual": actual,
            "within_spec": within_spec
        })
    
    # Use evaluation results from composition_check for failed rules and deviation messages
    deviation_messages = eval_result.get("deviation_messages", [])
    
    # Build failed_rules from evaluation result
    for rule_result in eval_result.get("rule_results", []):
        if not rule_result.get("pass_fail"):
            failed_rules.append({
                "element": rule_result.get("description", ""),
                "condition_type": rule_result.get("condition_type", ""),
                "message": rule_result.get("expected_text", "")
            })
    
    # Determine overall status
    if not has_readings:
        overall_status = "Pending"
    elif eval_result.get("overall_pass", True):
        overall_status = "OK"
    else:
        overall_status = "Out of Spec"
    
    return {
        "batch_info": batch_info,
        "sample_info": sample_info,
        "spec_table": spec_table,
        "element_results": element_results,
        "sum_rules": sum_rules,
        "ratio_rules": ratio_rules,
        "failed_rules": failed_rules,
        "deviation_messages": deviation_messages,
        "overall_status": overall_status,
        "accm_name": accm_name,
        "has_spec": accm is not None,
        "evaluation": eval_result
    }


def build_condition_text(rule):
    """Build human-readable condition text for normal limit."""
    limit_type = rule.limit_type
    min_pct = rule.min_percentage
    max_pct = rule.max_percentage
    
    if limit_type == "Range" and min_pct is not None and max_pct is not None:
        return f"{flt(min_pct, 4)} – {flt(max_pct, 4)}%"
    elif limit_type == "Maximum" and max_pct is not None:
        return f"≤ {flt(max_pct, 4)}%"
    elif limit_type == "Minimum" and min_pct is not None:
        return f"≥ {flt(min_pct, 4)}%"
    elif limit_type == "Equal To":
        val = min_pct or max_pct
        return f"= {flt(val, 4)}%" if val else "-"
    elif max_pct is not None:
        return f"≤ {flt(max_pct, 4)}%"
    elif min_pct is not None:
        return f"≥ {flt(min_pct, 4)}%"
    return "-"


def build_sum_condition_text(rule):
    """Build human-readable condition text for sum limit."""
    elem1 = get_element_code_from_item(rule.element_1)
    elem2 = get_element_code_from_item(rule.element_2)
    elem3 = get_element_code_from_item(rule.element_3) if rule.element_3 else None
    
    elements = [e for e in [elem1, elem2, elem3] if e]
    sum_label = "+".join(elements)
    
    limit_type = rule.sum_limit_type
    min_pct = rule.sum_min_percentage
    max_pct = rule.sum_max_percentage
    
    if limit_type == "Maximum" and max_pct is not None:
        return f"{sum_label} ≤ {flt(max_pct, 4)}%"
    elif limit_type == "Minimum" and min_pct is not None:
        return f"{sum_label} ≥ {flt(min_pct, 4)}%"
    elif min_pct is not None and max_pct is not None:
        return f"{sum_label}: {flt(min_pct, 4)} – {flt(max_pct, 4)}%"
    return f"{sum_label}"


def build_ratio_condition_text(rule):
    """Build human-readable condition text for ratio."""
    elem1 = get_element_code_from_item(rule.element_1)
    elem2 = get_element_code_from_item(rule.element_2)
    
    r1 = rule.ratio_value_1 or 1
    r2 = rule.ratio_value_2 or 1
    
    return f"{elem1}:{elem2} = {flt(r1, 2)}:{flt(r2, 2)}"


def check_within_spec(actual, lower, upper, limit_type):
    """Check if actual value is within spec limits."""
    if actual is None:
        return None
    
    actual = flt(actual)
    
    if limit_type == "Maximum":
        if upper is not None:
            return actual <= flt(upper)
    elif limit_type == "Minimum":
        if lower is not None:
            return actual >= flt(lower)
    elif limit_type == "Equal To":
        target = lower or upper
        if target is not None:
            return abs(actual - flt(target)) < 0.01  # 0.01% tolerance
    else:  # Range
        ok = True
        if lower is not None and actual < flt(lower):
            ok = False
        if upper is not None and actual > flt(upper):
            ok = False
        return ok
    
    return True  # No limits defined


def build_failure_message(elem, actual, lower, upper, limit_type):
    """Build human-readable failure message."""
    actual_str = flt(actual, 4)
    
    if limit_type == "Maximum" and upper is not None:
        return f"{elem} should be ≤ {flt(upper, 4)}%, actual {actual_str}%"
    elif limit_type == "Minimum" and lower is not None:
        return f"{elem} should be ≥ {flt(lower, 4)}%, actual {actual_str}%"
    elif lower is not None and actual < flt(lower):
        return f"{elem} should be ≥ {flt(lower, 4)}%, actual {actual_str}%"
    elif upper is not None and actual > flt(upper):
        return f"{elem} should be ≤ {flt(upper, 4)}%, actual {actual_str}%"
    
    return f"{elem} out of spec: {actual_str}%"


@frappe.whitelist()
def update_sample_result(batch, sample_id, readings=None, action="save", comment=None):
    """
    Update sample readings and perform action.
    
    Args:
        batch: Melting Batch name
        sample_id: Sample ID (e.g., "S1")
        readings: JSON dict of element readings {"Fe": 0.25, "Si": 0.12, ...}
        action: One of "save", "approve", "reject", "correction_required"
        comment: Optional QC comment
        
    Returns:
        dict with updated sample data
    """
    import json
    
    if isinstance(readings, str):
        readings = json.loads(readings)
    
    readings = frappe._dict(readings or {})
    
    if not batch or not sample_id:
        frappe.throw(_("Batch and Sample ID are required"))
    
    if action not in ["save", "approve", "reject", "correction_required"]:
        frappe.throw(_("Invalid action: {0}").format(action))
    
    # Load batch
    batch_doc = frappe.get_doc("Melting Batch", batch)
    
    # Find sample row
    sample_row = None
    sample_idx = None
    for idx, s in enumerate(batch_doc.spectro_samples):
        if s.sample_id == sample_id:
            sample_row = s
            sample_idx = idx
            break
    
    if not sample_row:
        frappe.throw(_("Sample {0} not found in batch {1}").format(sample_id, batch))
    
    # Update element readings
    for elem, field in ELEMENT_FIELDS.items():
        if elem in readings:
            setattr(sample_row, field, flt(readings[elem], 4))
    
    # Update status based on action
    if action == "save":
        if sample_row.status == "Pending":
            sample_row.status = "In Lab"
    elif action == "approve":
        sample_row.status = "Accepted"
        if hasattr(sample_row, "overall_result"):
            sample_row.overall_result = "In Spec"
        sample_row.result_status = "Within Limit"
    elif action == "reject":
        sample_row.status = "Rejected"
        if hasattr(sample_row, "overall_result"):
            sample_row.overall_result = "Out of Spec"
        sample_row.result_status = "Out of Limit"
    elif action == "correction_required":
        sample_row.status = "Correction Required"
        if hasattr(sample_row, "overall_result"):
            sample_row.overall_result = "Out of Spec"
        sample_row.result_status = "Out of Limit"
        sample_row.correction_required = 1
    
    # Update comment/remarks
    if comment:
        sample_row.remarks = comment
        if hasattr(sample_row, "correction_note"):
            sample_row.correction_note = comment
    
    # Update lab technician
    if hasattr(sample_row, "lab_technician"):
        sample_row.lab_technician = frappe.session.user
    
    # Evaluate sample and save QC feedback
    from swynix_mes.swynix_mes.utils.composition_check import (
        evaluate_sample_against_alloy,
        format_deviations_for_storage
    )
    
    # Build sample_elements dict from readings (prefer readings dict, fallback to sample_row fields)
    sample_elements = {}
    for elem, field in ELEMENT_FIELDS.items():
        # First check readings dict (user input)
        if elem in readings:
            sample_elements[elem] = flt(readings[elem], 4)
        # Fallback to sample_row field
        else:
            value = getattr(sample_row, field, None)
            if value is not None:
                sample_elements[elem] = flt(value, 4)
    
    # Also add S if present
    if hasattr(sample_row, "s_pct") and sample_row.s_pct is not None:
        sample_elements["S"] = flt(sample_row.s_pct, 4)
    
    # Evaluate against alloy spec
    eval_result = evaluate_sample_against_alloy(batch_doc.alloy, sample_elements)
    
    # Format deviations for storage
    deviation_summary, deviation_detail = format_deviations_for_storage(eval_result)
    
    # Build deviation summary as line-by-line text
    deviation_messages = eval_result.get("deviation_messages", [])
    deviation_summary_text = "\n".join(deviation_messages) if deviation_messages else ""
    deviation_count = len(deviation_messages)
    
    # Determine QC status based on action and evaluation
    if action == "approve":
        qc_status = "Within Spec"
    elif action == "reject":
        qc_status = "Rejected"
    elif action == "correction_required":
        qc_status = "Correction Required"
    else:
        # For "save", determine from evaluation
        if eval_result.get("overall_pass", False):
            qc_status = "Within Spec"
        else:
            qc_status = "Out of Spec"
    
    # Save QC feedback fields to sample row
    if hasattr(sample_row, "qc_status"):
        sample_row.qc_status = qc_status
    if hasattr(sample_row, "qc_comment"):
        sample_row.qc_comment = comment or ""
    if hasattr(sample_row, "qc_deviation_summary"):
        sample_row.qc_deviation_summary = deviation_summary_text
    if hasattr(sample_row, "qc_deviation_count"):
        sample_row.qc_deviation_count = deviation_count
    if hasattr(sample_row, "qc_deviation_detail"):
        sample_row.qc_deviation_detail = deviation_detail
    if hasattr(sample_row, "qc_last_updated_by"):
        sample_row.qc_last_updated_by = frappe.session.user
    if hasattr(sample_row, "qc_last_updated_on"):
        sample_row.qc_last_updated_on = frappe.utils.now_datetime()
    
    # Handle batch-level updates
    if action == "correction_required":
        # Set batch QC status
        if hasattr(batch_doc, "qc_status"):
            batch_doc.qc_status = "Correction Required"
        
        # Add process log entry
        plog = batch_doc.append("process_logs", {})
        plog.log_time = now_datetime()
        plog.event_type = "Correction"
        plog.sample_id = sample_id
        plog.note = f"QC Correction Required: {comment}" if comment else "QC Correction Required"
        
    elif action == "approve":
        # Check if all elements are within spec
        details = get_sample_details(batch, sample_id)
        if details.get("overall_status") == "OK":
            # Update batch QC status
            if hasattr(batch_doc, "qc_status"):
                batch_doc.qc_status = "OK"
            
            # Set lab signed by
            if hasattr(batch_doc, "lab_signed_by"):
                batch_doc.lab_signed_by = frappe.session.user
    
    elif action == "reject":
        # Update batch QC status if needed
        if hasattr(batch_doc, "qc_status"):
            batch_doc.qc_status = "Rejected"
    
    batch_doc.save()
    frappe.db.commit()
    
    # Build response
    return {
        "success": True,
        "sample_id": sample_id,
        "status": sample_row.status,
        "batch_status": batch_doc.status,
        "batch_qc_status": getattr(batch_doc, "qc_status", None),
        "message": get_action_message(action, sample_id)
    }


def get_action_message(action, sample_id):
    """Get success message for action."""
    messages = {
        "save": f"Sample {sample_id} saved",
        "approve": f"Sample {sample_id} approved - QC OK",
        "reject": f"Sample {sample_id} rejected",
        "correction_required": f"Correction request sent for sample {sample_id}"
    }
    return messages.get(action, "Action completed")


@frappe.whitelist()
def get_alloys():
    """Get list of alloys for filter dropdown."""
    return frappe.get_all(
        "Item",
        filters={"item_group": "Alloy"},
        fields=["name", "item_name"],
        order_by="name asc",
        limit=100
    )


@frappe.whitelist()
def get_furnaces():
    """Get list of furnaces for filter dropdown."""
    return frappe.get_all(
        "Workstation",
        filters={"workstation_type": "Foundry"},
        fields=["name", "workstation_name"],
        order_by="name asc"
    )


@frappe.whitelist()
def get_qc_history_for_sample(batch, sample_id):
    """
    Get charge and correction history for a specific sample.
    
    Determines the time window between the previous sample and current sample,
    then retrieves all charges and corrections in that window.
    
    Args:
        batch: Melting Batch name
        sample_id: Sample ID (e.g., "S1", "S2")
        
    Returns:
        dict with:
        - samples: All samples in the batch with their status
        - charges: Raw material charges in the time window
        - corrections: Correction entries in the time window
        - window: Time window (from, to) used for the query
        - current_sample: Current sample info
    """
    if not batch or not sample_id:
        frappe.throw(_("Batch and Sample ID are required"))
    
    # Load batch
    try:
        batch_doc = frappe.get_doc("Melting Batch", batch)
    except frappe.DoesNotExistError:
        frappe.throw(_("Melting Batch {0} not found").format(batch))
    
    # Get all samples of this batch ordered by time
    samples_list = []
    for s in batch_doc.spectro_samples:
        samples_list.append({
            "name": s.name,
            "sample_id": s.sample_id,
            "sample_time": s.sample_time,
            "status": s.status or s.result_status or "Pending",
            "overall_result": getattr(s, "overall_result", None)
        })
    
    # Sort by sample_time
    samples_sorted = sorted(samples_list, key=lambda x: x["sample_time"] or "")
    
    # Find current sample index
    current_idx = None
    current_sample = None
    for idx, s in enumerate(samples_sorted):
        if s["sample_id"] == sample_id:
            current_idx = idx
            current_sample = s
            break
    
    if current_idx is None:
        frappe.throw(_("Sample {0} not found in batch {1}").format(sample_id, batch))
    
    # Determine time window
    curr_time = samples_sorted[current_idx]["sample_time"]
    
    if current_idx > 0:
        prev_time = samples_sorted[current_idx - 1]["sample_time"]
    else:
        # First sample - use batch start time or creation
        prev_time = batch_doc.batch_start_datetime or batch_doc.creation
    
    # Convert times for comparison
    if curr_time:
        curr_time = get_datetime(curr_time)
    if prev_time:
        prev_time = get_datetime(prev_time)
    
    # Get charges in the time window
    charges = []
    for rm in batch_doc.raw_materials:
        rm_time = None
        
        # Try posting_datetime first
        if hasattr(rm, "posting_datetime") and rm.posting_datetime:
            rm_time = get_datetime(rm.posting_datetime)
        
        # If no posting_datetime, we can only use idx ordering
        # Include all charges if we can't determine time
        include = True
        
        if rm_time and prev_time and curr_time:
            # Time-based filtering
            include = (prev_time < rm_time <= curr_time)
        elif rm_time and curr_time:
            include = (rm_time <= curr_time)
        
        if include:
            charges.append({
                "idx": rm.idx,
                "posting_datetime": str(rm.posting_datetime) if hasattr(rm, "posting_datetime") and rm.posting_datetime else None,
                "item_code": rm.item_code,
                "item_name": rm.item_name,
                "ingredient_type": rm.ingredient_type,
                "qty_kg": rm.qty_kg,
                "source_bin": rm.source_bin,
                "batch_no": rm.batch_no,
                "is_correction": rm.is_correction
            })
    
    # Get corrections from process logs
    corrections = []
    for log in batch_doc.process_logs:
        if log.event_type != "Correction":
            continue
        
        log_time = get_datetime(log.log_time) if log.log_time else None
        
        include = True
        if log_time and prev_time and curr_time:
            include = (prev_time < log_time <= curr_time)
        elif log_time and curr_time:
            include = (log_time <= curr_time)
        
        if include:
            corrections.append({
                "idx": log.idx,
                "log_time": str(log.log_time) if log.log_time else None,
                "event_type": log.event_type,
                "sample_id": log.sample_id,
                "note": log.note,
                "temp_c": log.temp_c
            })
    
    # Also get correction charges (raw materials marked as correction)
    correction_charges = [c for c in charges if c.get("is_correction")]
    
    # Format samples for display
    samples_display = []
    for s in samples_sorted:
        # Map status to display text
        status = s.get("status", "Pending")
        overall = s.get("overall_result")
        
        if status == "Accepted" or overall == "In Spec":
            display_status = "Within Spec"
        elif status == "Rejected" or overall == "Out of Spec":
            display_status = "Out of Spec"
        elif status == "Correction Required":
            display_status = "Correction Asked"
        else:
            display_status = "Pending"
        
        samples_display.append({
            "sample_id": s["sample_id"],
            "sample_time": str(s["sample_time"]) if s["sample_time"] else None,
            "status": display_status,
            "is_current": s["sample_id"] == sample_id
        })
    
    return {
        "samples": samples_display,
        "charges": charges,
        "corrections": corrections,
        "correction_charges": correction_charges,
        "window": {
            "from": str(prev_time) if prev_time else None,
            "to": str(curr_time) if curr_time else None
        },
        "current_sample": {
            "sample_id": current_sample["sample_id"],
            "sample_time": str(current_sample["sample_time"]) if current_sample["sample_time"] else None,
            "index": current_idx + 1,
            "total": len(samples_sorted)
        },
        "batch_info": {
            "name": batch_doc.name,
            "batch_id": batch_doc.melting_batch_id,
            "batch_start": str(batch_doc.batch_start_datetime) if batch_doc.batch_start_datetime else None
        }
    }
