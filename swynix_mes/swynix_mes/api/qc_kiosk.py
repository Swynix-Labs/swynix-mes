# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

"""
QC Kiosk API - Quality Control integration with Alloy Chemical Composition Master

This module provides:
1. Helper functions for getting active composition masters
2. Sample creation with pre-populated elements from ACCM
3. QC evaluation logic for Normal Limit, Sum Limit, Ratio conditions
4. APIs for the QC Kiosk UI
5. Spectrometer integration API
"""

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, get_datetime, getdate


# ==================== ELEMENT CODE MAPPING ====================

# Common element symbol mappings
ELEMENT_SYMBOLS = {
    "silicon": "Si", "si": "Si",
    "iron": "Fe", "fe": "Fe",
    "copper": "Cu", "cu": "Cu",
    "manganese": "Mn", "mn": "Mn",
    "magnesium": "Mg", "mg": "Mg",
    "zinc": "Zn", "zn": "Zn",
    "titanium": "Ti", "ti": "Ti",
    "aluminium": "Al", "aluminum": "Al", "al": "Al",
    "chromium": "Cr", "cr": "Cr",
    "nickel": "Ni", "ni": "Ni",
    "lead": "Pb", "pb": "Pb",
    "tin": "Sn", "sn": "Sn",
    "vanadium": "V", "v": "V",
    "zirconium": "Zr", "zr": "Zr",
    "boron": "B", "b": "B",
    "calcium": "Ca", "ca": "Ca",
    "sodium": "Na", "na": "Na",
    "phosphorus": "P", "p": "P",
    "sulfur": "S", "s": "S",
    "beryllium": "Be", "be": "Be",
    "bismuth": "Bi", "bi": "Bi",
    "cadmium": "Cd", "cd": "Cd",
    "gallium": "Ga", "ga": "Ga",
    "lithium": "Li", "li": "Li",
    "strontium": "Sr", "sr": "Sr",
}


def get_element_code(item_name):
    """
    Extract element code from item name.
    E.g., "Si" from "Silicon", "Fe" from "Iron", etc.
    """
    if not item_name:
        return None
    
    item_lower = item_name.strip().lower()
    
    # Try direct match first
    if item_lower in ELEMENT_SYMBOLS:
        return ELEMENT_SYMBOLS[item_lower]
    
    # Check if it's already a valid symbol (1-2 chars)
    if len(item_name) <= 2:
        return item_name.capitalize()
    
    # Try partial match
    for key, symbol in ELEMENT_SYMBOLS.items():
        if key in item_lower:
            return symbol
    
    return item_name  # Return as-is if no match


# ==================== COMPOSITION MASTER HELPERS ====================

def get_active_composition_master(alloy):
    """
    Returns the active Alloy Chemical Composition Master doc for a given alloy.
    
    Logic:
    - Filter by alloy and is_active = 1
    - If multiple, pick the one with latest revision_date (or highest revision_no)
    
    Args:
        alloy: Item name/code for the alloy
        
    Returns:
        frappe.Document or None
    """
    if not alloy:
        return None
    
    # Find active composition masters for this alloy
    masters = frappe.get_all(
        "Alloy Chemical Composition Master",
        filters={
            "alloy": alloy,
            "is_active": 1
        },
        fields=["name", "revision_no", "revision_date"],
        order_by="revision_date desc, revision_no desc, creation desc",
        limit=1
    )
    
    if not masters:
        return None
    
    return frappe.get_doc("Alloy Chemical Composition Master", masters[0].name)


@frappe.whitelist()
def get_composition_master_for_alloy(alloy):
    """
    API wrapper for get_active_composition_master.
    Returns the composition master info for an alloy.
    """
    if not alloy:
        return None
    
    master = get_active_composition_master(alloy)
    if not master:
        return None
    
    return {
        "name": master.name,
        "alloy": master.alloy,
        "alloy_name": master.alloy_name,
        "standard_reference": master.standard_reference,
        "revision_no": master.revision_no,
        "revision_date": str(master.revision_date) if master.revision_date else None,
        "rules_count": len(master.composition_rules or [])
    }


# ==================== SAMPLE CREATION ====================

@frappe.whitelist()
def create_spectro_sample(melting_batch_name, sample_id=None):
    """
    Create a new spectro sample for a melting batch with pre-populated elements
    from the Alloy Chemical Composition Master.
    
    This function:
    1. Loads the Melting Batch
    2. Resolves alloy from batch
    3. Gets ACCM via get_active_composition_master(alloy)
    4. Creates a new child row in batch.spectro_samples with:
       - sample_id = next "S1", "S2", ...
       - sample_time = now_datetime()
       - status = "Pending"
       - spec_master = ACCM.name
       - overall_result = "Pending"
    5. For each composition rule in ACCM.composition_rules:
       - Creates a Melting Sample Element Result row with spec fields
    6. Saves batch
    7. Returns the created sample info
    
    Args:
        melting_batch_name: Name of the Melting Batch document
        sample_id: Optional custom sample ID (auto-generated if not provided)
        
    Returns:
        dict with sample info
    """
    if not melting_batch_name:
        frappe.throw(_("Melting Batch is required."))
    
    batch = frappe.get_doc("Melting Batch", melting_batch_name)
    alloy = batch.alloy
    
    # Determine next sample ID if not provided
    if not sample_id:
        existing_ids = [s.sample_id for s in batch.spectro_samples if s.sample_id]
        idx = len(existing_ids) + 1
        sample_id = f"S{idx}"
    
    # Get active composition master for the alloy
    accm = get_active_composition_master(alloy) if alloy else None
    
    # Create spectro sample row
    sample_row = batch.append("spectro_samples", {})
    sample_row.sample_id = sample_id
    sample_row.sample_time = now_datetime()
    sample_row.status = "Pending"
    sample_row.overall_result = "Pending"
    sample_row.result_status = "Pending"  # Legacy field
    
    if accm:
        sample_row.spec_master = accm.name
        
        # Check if the 'elements' child table field exists in the DocType
        # This handles the case where the migration hasn't been run yet
        has_elements_field = False
        try:
            sample_meta = frappe.get_meta("Melting Batch Spectro Sample")
            elements_field = sample_meta.get_field("elements")
            has_elements_field = elements_field is not None
        except Exception:
            has_elements_field = False
        
        if has_elements_field:
            # Pre-populate element rows from composition rules
            for rule in accm.composition_rules or []:
                condition_type = rule.condition_type
                
                # Skip Free Text rules - they don't have measurable elements
                if condition_type == "Free Text":
                    continue
                
                # Get element info
                element_1 = rule.element_1
                if not element_1:
                    continue
                
                element_code = get_element_code(element_1)
                
                # Build element result row
                el_row = sample_row.append("elements", {})
                el_row.element = element_1
                el_row.rule_row = rule.name
                el_row.condition_type = condition_type
                el_row.in_spec = 1  # Default to in-spec until evaluated
                
                if condition_type == "Normal Limit":
                    el_row.limit_type = rule.limit_type
                    el_row.spec_min_pct = rule.min_percentage
                    el_row.spec_max_pct = rule.max_percentage
                    
                    # Calculate target as midpoint if both min and max exist
                    if rule.min_percentage is not None and rule.max_percentage is not None:
                        el_row.spec_target_pct = (flt(rule.min_percentage) + flt(rule.max_percentage)) / 2
                    elif rule.min_percentage is not None:
                        el_row.spec_target_pct = rule.min_percentage
                    elif rule.max_percentage is not None:
                        el_row.spec_target_pct = rule.max_percentage
                        
                elif condition_type == "Sum Limit":
                    el_row.limit_type = rule.sum_limit_type
                    # For sum limit, max_pct stores the sum limit
                    if rule.sum_limit_type == "Maximum":
                        el_row.sum_limit_pct = rule.sum_max_percentage
                    elif rule.sum_limit_type == "Minimum":
                        el_row.sum_limit_pct = rule.sum_min_percentage
                    else:
                        # Range - store max
                        el_row.sum_limit_pct = rule.sum_max_percentage
                        el_row.spec_min_pct = rule.sum_min_percentage
                        el_row.spec_max_pct = rule.sum_max_percentage
                        
                elif condition_type == "Ratio":
                    # Store ratio values
                    if rule.ratio_value_1 and rule.ratio_value_2:
                        # Calculate expected ratio
                        el_row.ratio_value = flt(rule.ratio_value_1) / flt(rule.ratio_value_2) if rule.ratio_value_2 else 0
                        
                elif condition_type == "Remainder":
                    el_row.limit_type = "Minimum"
                    el_row.spec_min_pct = rule.remainder_min_percentage
    
    # Also log process event
    prow = batch.append("process_logs", {})
    prow.log_time = sample_row.sample_time
    prow.event_type = "Sample Taken"
    prow.sample_id = sample_id
    
    batch.save()
    frappe.db.commit()
    
    # Calculate elements count safely
    elements_count = 0
    try:
        if hasattr(sample_row, 'elements') and sample_row.elements:
            elements_count = len(sample_row.elements)
    except Exception:
        elements_count = 0
    
    return {
        "sample_id": sample_id,
        "sample_row_name": sample_row.name,
        "spec_master": accm.name if accm else None,
        "elements_count": elements_count,
        "batch_name": batch.name
    }


# ==================== QC EVALUATION LOGIC ====================

def evaluate_sample_qc(sample_doc, batch_doc=None):
    """
    Evaluate QC for a spectro sample based on ACCM rules.
    
    This function:
    1. Builds a dict of element values from the elements table
    2. For each element row, evaluates against its condition type:
       - Normal Limit: Check against min/max based on limit_type
       - Sum Limit: Calculate sum of participating elements and check
       - Ratio: Calculate ratio and check against expected value
       - Remainder: Check minimum percentage
    3. Sets in_spec, deviation_pct, condition_violated for each element
    4. Sets overall_result based on all elements
    
    Args:
        sample_doc: Melting Batch Spectro Sample row (dict-like or child doc)
        batch_doc: Optional parent Melting Batch document
        
    Returns:
        dict with evaluation results
    """
    if not sample_doc:
        return {"overall_result": "Pending", "errors": ["No sample provided"]}
    
    elements = getattr(sample_doc, 'elements', []) or []
    if not elements:
        return {"overall_result": "Pending", "errors": ["No elements to evaluate"]}
    
    # Build value dict: {element_code: sample_pct}
    val = {}
    element_map = {}  # Map element name to element row
    
    for el in elements:
        element_name = el.element
        element_code = get_element_code(element_name) if element_name else None
        
        if el.sample_pct is not None:
            if element_code:
                val[element_code] = flt(el.sample_pct)
            if element_name:
                val[element_name] = flt(el.sample_pct)
                element_map[element_name] = el
    
    # Track evaluation results
    out_of_spec_count = 0
    evaluated_count = 0
    pending_count = 0
    
    # Get ACCM for sum/ratio rule lookups
    spec_master = getattr(sample_doc, 'spec_master', None)
    accm = None
    if spec_master:
        try:
            accm = frappe.get_doc("Alloy Chemical Composition Master", spec_master)
        except Exception:
            pass
    
    # Build rule lookup by name
    rule_lookup = {}
    if accm:
        for rule in accm.composition_rules or []:
            rule_lookup[rule.name] = rule
    
    # Evaluate each element
    for el in elements:
        # Reset evaluation fields
        el.in_spec = 1
        el.condition_violated = ""
        el.deviation_pct = None
        
        # If no sample value, mark as pending
        if el.sample_pct is None:
            pending_count += 1
            continue
        
        evaluated_count += 1
        sample_pct = flt(el.sample_pct)
        condition_type = el.condition_type or "Normal Limit"
        limit_type = el.limit_type or ""
        
        # Calculate deviation from target
        if el.spec_target_pct is not None:
            el.deviation_pct = flt(sample_pct - flt(el.spec_target_pct), 4)
        
        if condition_type == "Normal Limit":
            # Evaluate based on limit_type
            is_ok = True
            violation = ""
            
            if limit_type == "Maximum":
                if el.spec_max_pct is not None and sample_pct > flt(el.spec_max_pct):
                    is_ok = False
                    violation = f"{get_element_code(el.element)} {sample_pct:.4f}% > {el.spec_max_pct:.4f}% (Max)"
                    
            elif limit_type == "Minimum":
                if el.spec_min_pct is not None and sample_pct < flt(el.spec_min_pct):
                    is_ok = False
                    violation = f"{get_element_code(el.element)} {sample_pct:.4f}% < {el.spec_min_pct:.4f}% (Min)"
                    
            elif limit_type == "Equal To":
                target = el.spec_target_pct or el.spec_min_pct or el.spec_max_pct
                if target is not None:
                    # Allow small tolerance (0.01%)
                    tolerance = 0.01
                    if abs(sample_pct - flt(target)) > tolerance:
                        is_ok = False
                        violation = f"{get_element_code(el.element)} {sample_pct:.4f}% ≠ {target:.4f}%"
                        
            else:  # Range or unspecified
                min_pct = el.spec_min_pct
                max_pct = el.spec_max_pct
                
                if min_pct is not None and sample_pct < flt(min_pct):
                    is_ok = False
                    violation = f"{get_element_code(el.element)} {sample_pct:.4f}% < {min_pct:.4f}% (Min)"
                elif max_pct is not None and sample_pct > flt(max_pct):
                    is_ok = False
                    violation = f"{get_element_code(el.element)} {sample_pct:.4f}% > {max_pct:.4f}% (Max)"
            
            if not is_ok:
                el.in_spec = 0
                el.condition_violated = violation
                out_of_spec_count += 1
                
        elif condition_type == "Sum Limit":
            # Get the original rule to find participating elements
            rule_name = el.rule_row
            rule = rule_lookup.get(rule_name) if rule_name else None
            
            if rule:
                # Get all participating elements
                sum_elements = []
                if rule.element_1:
                    sum_elements.append(rule.element_1)
                if rule.element_2:
                    sum_elements.append(rule.element_2)
                if rule.element_3:
                    sum_elements.append(rule.element_3)
                
                # Calculate sum
                sum_val = 0
                for elem in sum_elements:
                    elem_code = get_element_code(elem)
                    sum_val += val.get(elem_code, 0) or val.get(elem, 0)
                
                # Check against limit
                is_ok = True
                violation = ""
                sum_label = "+".join([get_element_code(e) for e in sum_elements])
                
                sum_limit_type = rule.sum_limit_type or limit_type
                
                if sum_limit_type == "Maximum":
                    sum_max = rule.sum_max_percentage
                    if sum_max is not None and sum_val > flt(sum_max):
                        is_ok = False
                        violation = f"{sum_label} = {sum_val:.4f}% > {sum_max:.4f}%"
                        
                elif sum_limit_type == "Minimum":
                    sum_min = rule.sum_min_percentage
                    if sum_min is not None and sum_val < flt(sum_min):
                        is_ok = False
                        violation = f"{sum_label} = {sum_val:.4f}% < {sum_min:.4f}%"
                        
                else:  # Range
                    sum_min = rule.sum_min_percentage
                    sum_max = rule.sum_max_percentage
                    if sum_min is not None and sum_val < flt(sum_min):
                        is_ok = False
                        violation = f"{sum_label} = {sum_val:.4f}% < {sum_min:.4f}%"
                    elif sum_max is not None and sum_val > flt(sum_max):
                        is_ok = False
                        violation = f"{sum_label} = {sum_val:.4f}% > {sum_max:.4f}%"
                
                if not is_ok:
                    el.in_spec = 0
                    el.condition_violated = violation
                    out_of_spec_count += 1
                    
        elif condition_type == "Ratio":
            # Get the original rule
            rule_name = el.rule_row
            rule = rule_lookup.get(rule_name) if rule_name else None
            
            if rule and rule.element_1 and rule.element_2:
                elem1_code = get_element_code(rule.element_1)
                elem2_code = get_element_code(rule.element_2)
                
                val1 = val.get(elem1_code, 0) or val.get(rule.element_1, 0)
                val2 = val.get(elem2_code, 0) or val.get(rule.element_2, 0)
                
                if val2 and val2 > 0:
                    actual_ratio = val1 / val2
                    expected_ratio = el.ratio_value or 0
                    
                    if expected_ratio:
                        # Allow 10% tolerance on ratio
                        tolerance = 0.1
                        ratio_diff = abs(actual_ratio - expected_ratio) / expected_ratio
                        
                        if ratio_diff > tolerance:
                            el.in_spec = 0
                            el.condition_violated = f"{elem1_code}/{elem2_code} = {actual_ratio:.2f} (expected ~{expected_ratio:.2f})"
                            out_of_spec_count += 1
                else:
                    if val1 > 0:
                        el.in_spec = 0
                        el.condition_violated = f"Cannot calculate ratio: {elem2_code} = 0"
                        out_of_spec_count += 1
                        
        elif condition_type == "Remainder":
            # Check minimum for remainder (usually Aluminium)
            min_pct = el.spec_min_pct
            if min_pct is not None and sample_pct < flt(min_pct):
                el.in_spec = 0
                el.condition_violated = f"{get_element_code(el.element)} {sample_pct:.4f}% < {min_pct:.4f}% (Min)"
                out_of_spec_count += 1
    
    # Determine overall result
    if pending_count == len(elements):
        overall_result = "Pending"
    elif out_of_spec_count > 0:
        overall_result = "Out of Spec"
    else:
        overall_result = "In Spec"
    
    # Update sample doc
    sample_doc.overall_result = overall_result
    
    # Update legacy result_status
    if overall_result == "In Spec":
        sample_doc.result_status = "Within Limit"
    elif overall_result == "Out of Spec":
        sample_doc.result_status = "Out of Limit"
        sample_doc.correction_required = 1
    else:
        sample_doc.result_status = "Pending"
    
    return {
        "overall_result": overall_result,
        "evaluated_count": evaluated_count,
        "out_of_spec_count": out_of_spec_count,
        "pending_count": pending_count,
        "total_elements": len(elements)
    }


@frappe.whitelist()
def update_sample_readings(sample_name, readings):
    """
    Update sample element readings and re-evaluate QC.
    
    This is the main API called from QC Kiosk when lab enters values.
    
    Args:
        sample_name: Name of the Melting Batch Spectro Sample child row
        readings: dict of {element_code_or_name: sample_pct}
        
    Returns:
        dict with updated sample and element info
    """
    import json
    
    if isinstance(readings, str):
        readings = json.loads(readings)
    
    if not sample_name:
        frappe.throw(_("Sample name is required."))
    
    # Find the sample row and its parent batch
    sample_row = frappe.db.get_value(
        "Melting Batch Spectro Sample",
        sample_name,
        ["name", "parent", "parenttype"],
        as_dict=True
    )
    
    if not sample_row:
        frappe.throw(_("Sample not found: {0}").format(sample_name))
    
    batch = frappe.get_doc("Melting Batch", sample_row.parent)
    
    # Find the sample in the batch
    sample_doc = None
    sample_idx = None
    for idx, s in enumerate(batch.spectro_samples):
        if s.name == sample_name:
            sample_doc = s
            sample_idx = idx
            break
    
    if not sample_doc:
        frappe.throw(_("Sample not found in batch."))
    
    # Update readings in element rows
    readings = frappe._dict(readings or {})
    
    for el in sample_doc.elements:
        element_name = el.element
        element_code = get_element_code(element_name) if element_name else None
        
        # Check if reading provided for this element
        value = None
        if element_code and element_code in readings:
            value = readings[element_code]
        elif element_name and element_name in readings:
            value = readings[element_name]
        
        if value is not None:
            el.sample_pct = flt(value, 4)
    
    # Also update legacy element fields if present
    legacy_map = {
        "Si": "si_percent", "Fe": "fe_percent", "Cu": "cu_percent",
        "Mn": "mn_percent", "Mg": "mg_percent", "Zn": "zn_percent",
        "Ti": "ti_percent", "Al": "al_percent"
    }
    
    for code, field in legacy_map.items():
        if code in readings and hasattr(sample_doc, field):
            setattr(sample_doc, field, flt(readings[code], 4))
    
    # Update status to In Lab if was Pending
    if sample_doc.status == "Pending":
        sample_doc.status = "In Lab"
    
    # Evaluate QC
    eval_result = evaluate_sample_qc(sample_doc, batch)
    
    batch.save()
    frappe.db.commit()
    
    # Build response with element details
    element_results = []
    for el in sample_doc.elements:
        element_results.append({
            "name": el.name,
            "element": el.element,
            "element_code": get_element_code(el.element),
            "condition_type": el.condition_type,
            "spec_min_pct": el.spec_min_pct,
            "spec_max_pct": el.spec_max_pct,
            "spec_target_pct": el.spec_target_pct,
            "sample_pct": el.sample_pct,
            "deviation_pct": el.deviation_pct,
            "in_spec": el.in_spec,
            "condition_violated": el.condition_violated
        })
    
    return {
        "sample_name": sample_doc.name,
        "sample_id": sample_doc.sample_id,
        "status": sample_doc.status,
        "overall_result": sample_doc.overall_result,
        "correction_required": sample_doc.correction_required,
        "elements": element_results,
        "evaluation": eval_result
    }


# ==================== QC KIOSK SAMPLE MANAGEMENT ====================

@frappe.whitelist()
def get_samples_for_qc(date=None, furnace=None, alloy=None, status_filter="pending"):
    """
    Get spectro samples for QC Kiosk list view.
    
    Args:
        date: Filter by sample date (defaults to today)
        furnace: Filter by furnace workstation
        alloy: Filter by alloy
        status_filter: "pending", "in_lab", "all"
        
    Returns:
        list of sample dicts with batch info
    """
    if not date:
        date = getdate()
    else:
        date = getdate(date)
    
    # Build date range
    start_of_day = f"{date} 00:00:00"
    end_of_day = f"{date} 23:59:59"
    
    # Build filters for batch
    batch_filters = {
        "docstatus": ["<", 2]  # Not cancelled
    }
    if furnace:
        batch_filters["furnace"] = furnace
    if alloy:
        batch_filters["alloy"] = alloy
    
    # Get batches matching filters
    batches = frappe.get_all(
        "Melting Batch",
        filters=batch_filters,
        fields=["name", "melting_batch_id", "furnace", "alloy", "product_item", "temper", "status", "qc_status"]
    )
    
    batch_names = [b.name for b in batches]
    batch_map = {b.name: b for b in batches}
    
    if not batch_names:
        return []
    
    # Build status filter for samples
    status_values = []
    if status_filter == "pending":
        status_values = ["Pending", "In Lab"]
    elif status_filter == "in_lab":
        status_values = ["In Lab"]
    elif status_filter == "correction":
        status_values = ["Correction Required"]
    # "all" - no status filter
    
    # Get samples from these batches
    sample_filters = {
        "parent": ["in", batch_names],
        "parenttype": "Melting Batch"
    }
    
    # Add date filter
    sample_filters["sample_time"] = ["between", [start_of_day, end_of_day]]
    
    if status_values:
        sample_filters["status"] = ["in", status_values]
    
    samples = frappe.get_all(
        "Melting Batch Spectro Sample",
        filters=sample_filters,
        fields=[
            "name", "parent", "sample_id", "sample_time", "status",
            "overall_result", "spec_master", "correction_required", "remarks"
        ],
        order_by="sample_time desc"
    )
    
    # Enrich with batch info
    result = []
    for s in samples:
        batch = batch_map.get(s.parent)
        if batch:
            result.append({
                "name": s.name,
                "sample_id": s.sample_id,
                "sample_time": str(s.sample_time) if s.sample_time else None,
                "status": s.status,
                "overall_result": s.overall_result,
                "spec_master": s.spec_master,
                "correction_required": s.correction_required,
                "remarks": s.remarks,
                "batch_name": batch.name,
                "batch_id": batch.melting_batch_id,
                "furnace": batch.furnace,
                "alloy": batch.alloy,
                "product_item": batch.product_item,
                "temper": batch.temper,
                "batch_status": batch.status,
                "batch_qc_status": batch.qc_status
            })
    
    return result


@frappe.whitelist()
def get_sample_detail(sample_name):
    """
    Get full sample detail for QC Kiosk right panel.
    
    Args:
        sample_name: Name of the spectro sample child row
        
    Returns:
        dict with full sample and batch info
    """
    if not sample_name:
        frappe.throw(_("Sample name is required."))
    
    # Find sample row
    sample_row = frappe.db.get_value(
        "Melting Batch Spectro Sample",
        sample_name,
        ["name", "parent", "parenttype"],
        as_dict=True
    )
    
    if not sample_row:
        frappe.throw(_("Sample not found."))
    
    batch = frappe.get_doc("Melting Batch", sample_row.parent)
    
    # Find sample in batch
    sample_doc = None
    for s in batch.spectro_samples:
        if s.name == sample_name:
            sample_doc = s
            break
    
    if not sample_doc:
        frappe.throw(_("Sample not found in batch."))
    
    # Build element results
    element_results = []
    for el in sample_doc.elements:
        element_results.append({
            "name": el.name,
            "element": el.element,
            "element_name": el.element_name,
            "element_code": get_element_code(el.element),
            "condition_type": el.condition_type,
            "limit_type": el.limit_type,
            "spec_min_pct": el.spec_min_pct,
            "spec_max_pct": el.spec_max_pct,
            "spec_target_pct": el.spec_target_pct,
            "sum_limit_pct": el.sum_limit_pct,
            "ratio_value": el.ratio_value,
            "sample_pct": el.sample_pct,
            "deviation_pct": el.deviation_pct,
            "in_spec": el.in_spec,
            "condition_violated": el.condition_violated,
            "note": el.note
        })
    
    # Get ACCM info if available
    accm_info = None
    if sample_doc.spec_master:
        accm_info = get_composition_master_for_alloy(batch.alloy)
    
    return {
        "sample": {
            "name": sample_doc.name,
            "sample_id": sample_doc.sample_id,
            "sample_time": str(sample_doc.sample_time) if sample_doc.sample_time else None,
            "status": sample_doc.status,
            "overall_result": sample_doc.overall_result,
            "spec_master": sample_doc.spec_master,
            "lab_technician": sample_doc.lab_technician,
            "correction_required": sample_doc.correction_required,
            "correction_note": sample_doc.correction_note,
            "remarks": sample_doc.remarks
        },
        "elements": element_results,
        "batch": {
            "name": batch.name,
            "melting_batch_id": batch.melting_batch_id,
            "furnace": batch.furnace,
            "alloy": batch.alloy,
            "product_item": batch.product_item,
            "temper": batch.temper,
            "charge_mix_ratio": batch.charge_mix_ratio,
            "status": batch.status,
            "qc_status": batch.qc_status
        },
        "composition_master": accm_info
    }


@frappe.whitelist()
def mark_sample_accepted(sample_name):
    """
    Mark a sample as Accepted (QC passed).
    Updates batch qc_status to OK.
    
    Args:
        sample_name: Name of the spectro sample
        
    Returns:
        dict with updated status
    """
    if not sample_name:
        frappe.throw(_("Sample name is required."))
    
    # Find sample
    sample_row = frappe.db.get_value(
        "Melting Batch Spectro Sample",
        sample_name,
        ["name", "parent"],
        as_dict=True
    )
    
    if not sample_row:
        frappe.throw(_("Sample not found."))
    
    batch = frappe.get_doc("Melting Batch", sample_row.parent)
    
    # Find and update sample
    for s in batch.spectro_samples:
        if s.name == sample_name:
            # Re-evaluate to ensure it's actually in spec
            eval_result = evaluate_sample_qc(s, batch)
            
            if s.overall_result != "In Spec":
                frappe.throw(_(
                    "Cannot accept sample - it is not In Spec. "
                    "Overall result: {0}, Out of spec count: {1}"
                ).format(s.overall_result, eval_result.get("out_of_spec_count", 0)))
            
            s.status = "Accepted"
            s.lab_technician = frappe.session.user
            break
    
    # Update batch QC status
    batch.qc_status = "OK"
    batch.lab_signed_by = frappe.session.user
    
    batch.save()
    frappe.db.commit()
    
    return {
        "sample_status": "Accepted",
        "batch_qc_status": "OK",
        "message": _("Sample accepted. Batch is now QC OK.")
    }


@frappe.whitelist()
def mark_sample_correction_required(sample_name, correction_note):
    """
    Mark a sample as Correction Required.
    Updates batch qc_status to Correction Required.
    
    Args:
        sample_name: Name of the spectro sample
        correction_note: Required note explaining what correction is needed
        
    Returns:
        dict with updated status
    """
    if not sample_name:
        frappe.throw(_("Sample name is required."))
    
    if not correction_note:
        frappe.throw(_("Correction note is required."))
    
    # Find sample
    sample_row = frappe.db.get_value(
        "Melting Batch Spectro Sample",
        sample_name,
        ["name", "parent"],
        as_dict=True
    )
    
    if not sample_row:
        frappe.throw(_("Sample not found."))
    
    batch = frappe.get_doc("Melting Batch", sample_row.parent)
    
    # Find and update sample
    for s in batch.spectro_samples:
        if s.name == sample_name:
            s.status = "Correction Required"
            s.overall_result = "Out of Spec"
            s.correction_required = 1
            s.correction_note = correction_note
            s.lab_technician = frappe.session.user
            break
    
    # Update batch QC status
    batch.qc_status = "Correction Required"
    
    # Add process log entry
    prow = batch.append("process_logs", {})
    prow.log_time = now_datetime()
    prow.event_type = "Correction"
    prow.note = f"QC Correction Required: {correction_note}"
    
    batch.save()
    frappe.db.commit()
    
    return {
        "sample_status": "Correction Required",
        "batch_qc_status": "Correction Required",
        "message": _("Sample marked for correction. Batch QC status updated.")
    }


@frappe.whitelist()
def create_resample(sample_name):
    """
    Create a new sample (re-sample) for the same batch.
    Marks the current sample as Rejected.
    
    Args:
        sample_name: Name of the current spectro sample
        
    Returns:
        dict with new sample info
    """
    if not sample_name:
        frappe.throw(_("Sample name is required."))
    
    # Find current sample
    sample_row = frappe.db.get_value(
        "Melting Batch Spectro Sample",
        sample_name,
        ["name", "parent", "sample_id"],
        as_dict=True
    )
    
    if not sample_row:
        frappe.throw(_("Sample not found."))
    
    batch = frappe.get_doc("Melting Batch", sample_row.parent)
    
    # Mark current sample as Rejected
    for s in batch.spectro_samples:
        if s.name == sample_name:
            s.status = "Rejected"
            break
    
    batch.save()
    
    # Create new sample
    result = create_spectro_sample(batch.name)
    
    return {
        "old_sample": sample_row.sample_id,
        "old_sample_status": "Rejected",
        "new_sample": result,
        "message": _("New sample {0} created. Previous sample marked as Rejected.").format(
            result.get("sample_id")
        )
    }


# ==================== SPECTROMETER INTEGRATION API ====================

@frappe.whitelist(allow_guest=True)
def ingest_spectro_payload(sample_name, payload):
    """
    API for direct spectrometer integration.
    Accepts element readings from spectrometer and updates the sample.
    
    This endpoint can be called by:
    - Spectrometer software sending results directly
    - LIMS systems pushing results
    - Manual import tools
    
    Args:
        sample_name: Name of the spectro sample to update
        payload: dict of element readings, e.g.:
            {
                "Fe": 0.25,
                "Si": 0.12,
                "Mn": 1.05,
                "Cu": 0.01,
                ...
            }
            
    Returns:
        dict with evaluation results
    """
    import json
    
    if isinstance(payload, str):
        payload = json.loads(payload)
    
    if not sample_name:
        return {"success": False, "error": "sample_name is required"}
    
    if not payload:
        return {"success": False, "error": "payload is required"}
    
    try:
        # Update readings using existing function
        result = update_sample_readings(sample_name, payload)
        
        # Find the sample and update status to In Lab
        sample_row = frappe.db.get_value(
            "Melting Batch Spectro Sample",
            sample_name,
            ["name", "parent"],
            as_dict=True
        )
        
        if sample_row:
            batch = frappe.get_doc("Melting Batch", sample_row.parent)
            for s in batch.spectro_samples:
                if s.name == sample_name:
                    if s.status == "Pending":
                        s.status = "In Lab"
                    break
            batch.save()
            frappe.db.commit()
        
        return {
            "success": True,
            "sample_name": sample_name,
            "overall_result": result.get("overall_result"),
            "status": result.get("status"),
            "elements": result.get("elements"),
            "evaluation": result.get("evaluation")
        }
        
    except Exception as e:
        frappe.log_error(
            title="Spectro Payload Ingestion Error",
            message=f"Sample: {sample_name}\nPayload: {payload}\nError: {str(e)}"
        )
        return {
            "success": False,
            "error": str(e)
        }


# ==================== MELTING KIOSK INTEGRATION ====================

@frappe.whitelist()
def check_qc_for_transfer(batch_name):
    """
    Check if a batch is QC-cleared for transfer.
    
    Returns:
        dict with:
        - can_transfer: bool
        - qc_status: current QC status
        - message: explanation
        - accepted_samples: list of accepted sample IDs
    """
    if not batch_name:
        return {
            "can_transfer": False,
            "qc_status": "Pending",
            "message": _("Batch name is required.")
        }
    
    batch = frappe.get_doc("Melting Batch", batch_name)
    
    # Check for accepted samples
    accepted_samples = []
    pending_samples = []
    correction_samples = []
    
    for s in batch.spectro_samples:
        if s.status == "Accepted" and s.overall_result == "In Spec":
            accepted_samples.append(s.sample_id)
        elif s.status in ("Pending", "In Lab"):
            pending_samples.append(s.sample_id)
        elif s.status == "Correction Required":
            correction_samples.append(s.sample_id)
    
    if accepted_samples:
        return {
            "can_transfer": True,
            "qc_status": "OK",
            "message": _("QC OK - {0} accepted sample(s).").format(len(accepted_samples)),
            "accepted_samples": accepted_samples
        }
    elif correction_samples:
        return {
            "can_transfer": False,
            "qc_status": "Correction Required",
            "message": _("QC out of spec - correction required. Samples: {0}").format(
                ", ".join(correction_samples)
            ),
            "correction_samples": correction_samples
        }
    elif pending_samples:
        return {
            "can_transfer": False,
            "qc_status": "Pending",
            "message": _("QC pending - samples awaiting analysis: {0}").format(
                ", ".join(pending_samples)
            ),
            "pending_samples": pending_samples
        }
    else:
        return {
            "can_transfer": False,
            "qc_status": "Pending",
            "message": _("No spectro samples taken. Take a sample before transfer."),
            "accepted_samples": []
        }


@frappe.whitelist()
def get_qc_summary_for_batch(batch_name):
    """
    Get QC summary for a batch (used by Melting Kiosk spectro tab).
    
    Returns:
        dict with samples list and QC status
    """
    if not batch_name:
        return {"samples": [], "qc_status": "Pending"}
    
    batch = frappe.get_doc("Melting Batch", batch_name)
    
    samples = []
    for s in batch.spectro_samples:
        samples.append({
            "name": s.name,
            "sample_id": s.sample_id,
            "sample_time": str(s.sample_time) if s.sample_time else None,
            "status": s.status,
            "overall_result": s.overall_result,
            "correction_required": s.correction_required,
            "spec_master": s.spec_master
        })
    
    return {
        "samples": samples,
        "qc_status": batch.qc_status or "Pending",
        "batch_status": batch.status
    }

