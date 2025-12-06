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


def _map_status_filter(status_val):
    """Map UI status filter to QC Sample status values.
    
    Important: Each status category is mutually exclusive to prevent
    samples from appearing in wrong filter results.
    """
    status_map = {
        "Pending": ["Pending", "In Lab"],
        "Approved": ["Approved", "Accepted", "Within Spec"],
        "Within Spec": ["Approved", "Accepted", "Within Spec"],
        "Rejected": ["Rejected"],  # Only Rejected, not Correction Required
        "Correction Required": ["Correction Required"],  # Only Correction Required, not Rejected
        "Hold": ["Hold"],  # Samples on hold
    }
    return status_map.get(status_val, [status_val])


def _map_display_status(status, overall=None):
    """Normalize status for display."""
    display_status = status or "Pending"
    # Map both "Approved" and "Within Spec" to approved display
    if display_status in ("Approved", "Accepted", "Within Spec") or overall == "In Spec":
        return "Within Spec"
    if display_status == "Rejected" or overall == "Out of Spec":
        return "Rejected"
    if display_status == "Correction Required":
        return "Correction Required"
    if display_status == "In Lab":
        return "Pending"
    return display_status


@frappe.whitelist()
def export_samples_to_excel(filters=None):
    """
    Export filtered samples to Excel with all required columns.
    
    Columns:
    - Sample No
    - Source Type
    - Melting Batch
    - Mother Coil
    - Caster
    - Elements (dynamic)
    - Deviation Summary
    - QC Decision
    - Remarks
    - Approved By
    - Approved At
    """
    import json
    from frappe.utils.xlsxutils import make_xlsx
    from frappe.utils import nowdate

    if isinstance(filters, str):
        filters = json.loads(filters)
    
    filters = frappe._dict(filters or {})
    
    sample_filters = {"docstatus": ["<", 2]}
    
    if filters.get("alloy"):
        sample_filters["alloy"] = filters.alloy
    
    if filters.get("source_type") and filters.source_type != "All":
        sample_filters["source_type"] = filters.source_type
    
    if filters.get("status") and filters.status != "All":
        sample_filters["status"] = ["in", _map_status_filter(filters.status)]
    
    # Date filters on sample_time
    if filters.get("from_date") and filters.get("to_date"):
        sample_filters["sample_time"] = ["between", [f"{filters.from_date} 00:00:00", f"{filters.to_date} 23:59:59"]]
    elif filters.get("from_date"):
        sample_filters["sample_time"] = [">=", f"{filters.from_date} 00:00:00"]
    elif filters.get("to_date"):
        sample_filters["sample_time"] = ["<=", f"{filters.to_date} 23:59:59"]
    
    # Fetch basic fields
    data = frappe.get_all(
        "QC Sample",
        filters=sample_filters,
        fields=[
            "name", "sample_id", "sample_no", "source_type", "source_document", 
            "melting_batch", "mother_coil", "caster", "furnace",
            "alloy", "product_item", "temper",
            "sample_time", "status", "overall_result", "qc_decision",
            "qc_comment", "correction_note", "remarks", "deviation_messages",
            "lab_technician", "qc_decision_time"
        ],
        order_by="sample_time desc"
    )
    
    # Fetch elements and get user full names
    for d in data:
        sample_doc = frappe.get_doc("QC Sample", d.name)
        d.elements = {}
        d.element_codes = {}
        for el in sample_doc.elements:
            if el.sample_pct is not None:
                elem_code = getattr(el, "element_code", None) or get_element_code_from_item(el.element)
                if elem_code:
                    d.element_codes[elem_code] = el.sample_pct
                d.elements[el.element or elem_code] = el.sample_pct
        
        # Get user full name for lab technician
        if d.lab_technician:
            d.approved_by_name = frappe.db.get_value("User", d.lab_technician, "full_name") or d.lab_technician
        else:
            d.approved_by_name = ""

    # Identify all unique element codes across samples
    all_elements = set()
    for d in data:
        if hasattr(d, "element_codes"):
            all_elements.update(d.element_codes.keys())
    sorted_elements = sorted(list(all_elements))

    # Prepare columns as per specification
    fixed_columns = [
        "Sample No",
        "Source Type", 
        "Melting Batch",
        "Mother Coil",
        "Caster",
        "Furnace",
        "Alloy",
        "Product",
        "Temper",
        "Sample Time"
    ]
    
    # Add element columns
    element_columns = sorted_elements
    
    # Add remaining columns
    tail_columns = [
        "Deviation Summary",
        "QC Decision",
        "Status",
        "Overall Result",
        "Remarks",
        "Approved By",
        "Approved At"
    ]
    
    columns = fixed_columns + element_columns + tail_columns
    rows = [columns]
    
    for d in data:
        row = [
            d.sample_no or d.sample_id,
            d.source_type,
            d.melting_batch or "",
            d.mother_coil or "",
            d.caster or "",
            d.furnace or "",
            d.alloy or "",
            d.product_item or "",
            d.temper or "",
            str(d.sample_time) if d.sample_time else ""
        ]
        
        # Add element values
        for el in sorted_elements:
            val = d.element_codes.get(el, "")
            row.append(val)
        
        # Add tail columns
        row.extend([
            d.deviation_messages or "",
            d.qc_decision or "",
            d.status or "",
            d.overall_result or "",
            d.qc_comment or d.correction_note or d.remarks or "",
            d.approved_by_name or "",
            str(d.qc_decision_time) if d.qc_decision_time else ""
        ])
        
        rows.append(row)
        
    xlsx_file = make_xlsx(rows, "QC Samples")
    file_name = f"QC_Samples_Export_{nowdate()}.xlsx"

    frappe.response["filename"] = file_name
    frappe.response["filecontent"] = xlsx_file.getvalue()
    frappe.response["type"] = "binary"


@frappe.whitelist()
def get_pending_samples(filters=None):
    """
    Get pending/recent QC samples across all sources.
    
    Supports QC Sample DocType (Melting Batch, Casting Run, Coil) and
    keeps backward compatibility with the existing filter object.
    """
    import json
    if isinstance(filters, str):
        filters = json.loads(filters)
    
    filters = frappe._dict(filters or {})
    
    sample_filters = {"docstatus": ["<", 2]}
    
    if filters.get("alloy"):
        sample_filters["alloy"] = filters.alloy
    
    if filters.get("source_type") and filters.source_type != "All":
        sample_filters["source_type"] = filters.source_type
    
    if filters.get("status") and filters.status != "All":
        sample_filters["status"] = ["in", _map_status_filter(filters.status)]
    
    # Date filters on sample_time
    if filters.get("from_date") and filters.get("to_date"):
        sample_filters["sample_time"] = ["between", [f"{filters.from_date} 00:00:00", f"{filters.to_date} 23:59:59"]]
    elif filters.get("from_date"):
        sample_filters["sample_time"] = [">=", f"{filters.from_date} 00:00:00"]
    elif filters.get("to_date"):
        sample_filters["sample_time"] = ["<=", f"{filters.to_date} 23:59:59"]
    
    samples = frappe.get_all(
        "QC Sample",
        filters=sample_filters,
        fields=[
            "name", "sample_id", "sample_sequence_no", "sample_time",
            "source_type", "source_document", "melting_batch", "casting_run", "mother_coil",
            "alloy", "furnace", "caster", "product_item", "temper",
            "status", "overall_result", "correction_required", "spec_master"
        ],
        order_by="sample_time desc, creation desc",
        limit=200
    )
    
    result = []
    for s in samples:
        display_status = _map_display_status(s.status, s.overall_result)
        
        result.append({
            "name": s.name,
            "sample_id": s.sample_id,
            "sample_sequence_no": s.sample_sequence_no,
            "sample_time": str(s.sample_time) if s.sample_time else None,
            "source_type": s.source_type,
            "source_document": s.source_document,
            "melting_batch": s.melting_batch,
            "casting_run": s.casting_run,
            "mother_coil": s.mother_coil,
            "alloy": s.alloy,
            "product": s.product_item,
            "furnace": s.furnace,
            "caster": s.caster,
            "status": display_status,
            "overall_result": s.overall_result,
            "correction_required": s.correction_required,
            "spec_master": s.spec_master
        })
    
    return result


@frappe.whitelist()
def get_sample_details(batch=None, sample_id=None, sample_name=None):
    """
    Get detailed QC Sample information with spec comparison.
    
    Supports QC samples from Melting Batch, Casting Run, and Coil.
    """
    from swynix_mes.swynix_mes.utils.composition_check import (
        evaluate_sample_against_alloy,
        get_element_code,
        get_active_composition_master
    )
    
    # Resolve QC Sample
    if not sample_name and sample_id:
        lookup_filters = {"sample_id": sample_id}
        if batch:
            lookup_filters["source_document"] = batch
        sample_name = frappe.db.get_value("QC Sample", lookup_filters, "name")
    
    if not sample_name:
        frappe.throw(_("Sample is required"))
    
    # Check if sample exists before trying to load
    if not frappe.db.exists("QC Sample", sample_name):
        frappe.throw(
            _("QC Sample '{0}' not found. The sample may have been deleted. Please refresh the page.").format(sample_name),
            title=_("Sample Not Found")
        )
    
    sample_doc = frappe.get_doc("QC Sample", sample_name)
    
    # Source info (kept under batch_info key for UI compatibility)
    source_info = {
        "name": sample_doc.source_document,
        "batch_id": sample_doc.source_document,
        "alloy": sample_doc.alloy,
        "product": sample_doc.product_item,
        "furnace": sample_doc.furnace,
        "caster": sample_doc.caster,
        "temper": sample_doc.temper,
        "recipe": None,
        "casting_plan": sample_doc.casting_plan,
        "status": sample_doc.status,
        "qc_status": sample_doc.status,
        "source_type": sample_doc.source_type,
        "melting_batch": sample_doc.melting_batch,
        "casting_run": sample_doc.casting_run,
        "mother_coil": sample_doc.mother_coil,
        "sample_sequence_no": sample_doc.sample_sequence_no,
    }
    
    sample_info = {
        "name": sample_doc.name,
        "sample_id": sample_doc.sample_id,
        "sample_time": str(sample_doc.sample_time) if sample_doc.sample_time else None,
        "status": sample_doc.status or "Pending",
        "overall_result": sample_doc.overall_result,
        "correction_required": sample_doc.correction_required,
        "remarks": sample_doc.qc_comment or sample_doc.remarks,
        "spec_master": sample_doc.spec_master,
        "source_type": sample_doc.source_type,
        "source_document": sample_doc.source_document,
    }
    
    # Build current readings
    current_readings = {}
    for el in sample_doc.elements:
        elem_code = getattr(el, "element_code", None) or get_element_code(el.element)
        if el.sample_pct is not None and elem_code:
            current_readings[elem_code] = flt(el.sample_pct, 4)
    
    # Load ACCM
    accm = None
    accm_name = None
    spec_table = []
    element_specs = {}
    sum_rules = []
    ratio_rules = []
    
    if sample_doc.alloy:
        accm = get_active_composition_master(sample_doc.alloy)
        if accm:
            accm_name = accm.name
    
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
    
    eval_result = evaluate_sample_against_alloy(sample_doc.alloy, current_readings)
    
    element_results = []
    failed_rules = []
    has_readings = False
    
    for el in sample_doc.elements:
        elem_code = getattr(el, "element_code", None) or get_element_code(el.element)
        spec = element_specs.get(elem_code, {})
        lower_limit = spec.get("min")
        upper_limit = spec.get("max")
        limit_type = spec.get("limit_type", el.limit_type or "Range")
        
        actual = el.sample_pct
        within_spec = None
        if actual is not None:
            has_readings = True
            within_spec = check_within_spec(actual, lower_limit, upper_limit, limit_type)
        
        spec_text = "-"
        if lower_limit is not None and upper_limit is not None:
            spec_text = f"{flt(lower_limit, 4)} – {flt(upper_limit, 4)}"
        elif lower_limit is not None:
            spec_text = f"≥ {flt(lower_limit, 4)}"
        elif upper_limit is not None:
            spec_text = f"≤ {flt(upper_limit, 4)}"
        
        element_results.append({
            "element": elem_code or el.element,
            "spec_text": spec_text,
            "lower_limit": lower_limit,
            "upper_limit": upper_limit,
            "actual": flt(actual, 4) if actual is not None else None,
            "within_spec": within_spec
        })
    
    deviation_messages = eval_result.get("deviation_messages", [])
    for rule_result in eval_result.get("rule_results", []):
        if not rule_result.get("pass_fail"):
            failed_rules.append({
                "element": rule_result.get("description", ""),
                "condition_type": rule_result.get("condition_type", ""),
                "message": rule_result.get("expected_text", "")
            })
    
    if not has_readings:
        overall_status = "Pending"
    elif eval_result.get("overall_pass", True):
        overall_status = "OK"
    else:
        overall_status = "Out of Spec"
    
    return {
        "batch_info": source_info,
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
def update_sample_result(batch=None, sample_id=None, sample_name=None, readings=None, action="save", comment=None):
    """
    Update QC Sample readings and perform QC actions.
    Supports multi-source QC Sample DocType.
    
    Actions:
    - save: Save readings without decision
    - approve: Mark as Within Spec / Approved
    - reject: Mark as Rejected
    - correction_required: Request correction from operator
    - hold: Put sample on hold for further review
    """
    from swynix_mes.swynix_mes.doctype.qc_sample.qc_sample import get_element_code as qc_element_code
    import json
    
    if isinstance(readings, str):
        readings = json.loads(readings)
    
    readings = frappe._dict(readings or {})
    
    if action not in ["save", "approve", "reject", "correction_required", "hold"]:
        frappe.throw(_("Invalid action: {0}").format(action))
    
    if not sample_name and sample_id:
        lookup_filters = {"sample_id": sample_id}
        if batch:
            lookup_filters["source_document"] = batch
        sample_name = frappe.db.get_value("QC Sample", lookup_filters, "name")
    
    if not sample_name:
        frappe.throw(_("Sample is required"))
    
    # Check if sample exists before trying to load
    if not frappe.db.exists("QC Sample", sample_name):
        frappe.throw(
            _("QC Sample '{0}' not found. The sample may have been deleted. Please refresh the page.").format(sample_name),
            title=_("Sample Not Found")
        )
    
    sample_doc = frappe.get_doc("QC Sample", sample_name)
    
    if sample_doc.docstatus == 1:
        frappe.throw(_("QC Sample is already submitted."))
    
    # Update element readings
    for el in sample_doc.elements:
        elem_code = getattr(el, "element_code", None) or qc_element_code(el.element)
        if elem_code and elem_code in readings:
            el.sample_pct = flt(readings[elem_code], 4)
        elif el.element and el.element in readings:
            el.sample_pct = flt(readings[el.element], 4)
    
    # Default status bump for save
    if action == "save" and sample_doc.status == "Pending":
        sample_doc.status = "In Lab"
    
    # Evaluate QC
    sample_doc.evaluate_qc()
    
    # Map actions to QC Sample workflow
    if action == "approve":
        if sample_doc.overall_result != "In Spec":
            frappe.throw(_("Cannot approve a sample that is out of spec."))
        sample_doc.qc_action = "Approve"
        sample_doc.qc_comment = comment or ""
        sample_doc.status = "Within Spec"  # Use "Within Spec" per spec
        sample_doc.qc_decision = "Within Spec"
    elif action == "reject":
        sample_doc.qc_action = "Reject"
        sample_doc.qc_comment = comment or ""
        sample_doc.status = "Rejected"
        sample_doc.qc_decision = "Rejected"
    elif action == "correction_required":
        sample_doc.qc_action = "Request Correction"
        sample_doc.correction_note = comment or ""
        sample_doc.qc_comment = comment or ""
        sample_doc.correction_required = 1
        sample_doc.status = "Correction Required"
        sample_doc.qc_decision = "Correction Required"
    elif action == "hold":
        sample_doc.qc_action = "Hold"
        sample_doc.qc_comment = comment or ""
        sample_doc.status = "Hold"
        sample_doc.qc_decision = "Hold"
    
    # Persist changes
    sample_doc.lab_technician = frappe.session.user
    if action != "save":
        sample_doc.qc_decision_time = now_datetime()
    
    if action in ["approve", "reject", "correction_required", "hold"]:
        sample_doc.flags.from_kiosk = True
        sample_doc.save()
        sample_doc.submit()
        sample_doc.reload()
        
        # Propagate status to source
        propagate_qc_status(sample_doc)
    else:
        sample_doc.save()
    
    frappe.db.commit()
    
    # Build response with stock entry info if applicable
    result = {
        "success": True,
        "sample_id": sample_doc.sample_id,
        "sample_name": sample_doc.name,
        "status": sample_doc.status,
        "batch_status": sample_doc.status,
        "batch_qc_status": sample_doc.status,
        "message": get_action_message(action, sample_doc.sample_id)
    }
    
    # Include stock entry info for approved casting coils
    if action == "approve" and sample_doc.source_type == "Casting" and sample_doc.mother_coil:
        coil = frappe.get_doc("Mother Coil", sample_doc.mother_coil)
        if coil.stock_entry:
            result["stock_entry"] = coil.stock_entry
            result["message"] = f"Sample {sample_doc.sample_id} approved. Stock Entry {coil.stock_entry} created."
    
    return result


def propagate_qc_status(qc_sample):
    """Propagate QC status back to source documents (Melting Batch / Coil)."""
    if not qc_sample:
        return

    source_type = qc_sample.source_type
    
    # Melting Propagation (handle both old and new source_type values)
    if source_type in ("Melting", "Melting Batch") and qc_sample.melting_batch:
        # Find the row in melting batch spectro samples and update it
        batch = frappe.get_doc("Melting Batch", qc_sample.melting_batch)
        updated = False
        for s in batch.spectro_samples:
            if s.sample_id == qc_sample.sample_id:
                s.status = qc_sample.status
                s.overall_result = qc_sample.overall_result
                s.correction_required = qc_sample.correction_required
                s.qc_status = qc_sample.overall_result  # Sync local status
                s.qc_comment = qc_sample.qc_comment
                # Accept both "Approved" and "Within Spec" as approval
                if qc_sample.status in ("Approved", "Within Spec"):
                    s.status = "Accepted"  # Legacy mapping
                updated = True
                break
        
        if updated:
            # Also update batch level QC status if this is the latest
            # Accept both "Approved" and "Within Spec" as approval
            if qc_sample.status in ("Approved", "Within Spec"):
                batch.qc_status = "OK"
            elif qc_sample.status == "Correction Required":
                batch.qc_status = "Correction Required"
            elif qc_sample.status == "Rejected":
                batch.qc_status = "Rejected"
            # Hold status - keep batch status unchanged, just note the hold
            
            batch.flags.ignore_validate = True  # Avoid re-triggering heavy validations
            batch.save(ignore_permissions=True)

    # Casting Propagation (handle both old and new source_type values)
    elif source_type in ("Casting", "Casting Coil", "Coil", "Casting Run") and qc_sample.mother_coil:
        # The QC Sample's handle_approval already handles coil updates and stock entry
        # This function is only called for backward compatibility with kiosk direct updates
        # Check if the QC Sample's own handle methods already ran
        if getattr(qc_sample.flags, 'from_kiosk', False):
            # QC Sample was submitted via kiosk - handle_approval() was already called
            # Just ensure coil reflects latest status
            coil = frappe.get_doc("Mother Coil", qc_sample.mother_coil)
            
            # Update fields that might not have been set by handle_approval
            if qc_sample.status not in ("Approved", "Within Spec"):
                # For non-approval statuses, update coil status
                coil.qc_status = qc_sample.status
                coil.qc_comments = qc_sample.qc_comment
                coil.qc_deviation_summary = qc_sample.deviation_messages
                coil.coil_qc_sample = qc_sample.name
                coil.qc_last_sample = qc_sample.name
                coil.qc_last_comment = qc_sample.qc_comment
                
                # Handle Hold status
                if qc_sample.status == "Hold":
                    coil.qc_status = "Hold"
                    coil.coil_status = "Hold"
                
                coil.flags.ignore_validate = True
                coil.save(ignore_permissions=True)
        else:
            # Direct call - perform full propagation
            coil = frappe.get_doc("Mother Coil", qc_sample.mother_coil)
            coil.qc_status = qc_sample.status
            coil.qc_comments = qc_sample.qc_comment
            coil.qc_deviation_summary = qc_sample.deviation_messages
            coil.coil_qc_sample = qc_sample.name
            coil.qc_last_sample = qc_sample.name
            coil.qc_last_comment = qc_sample.qc_comment
            
            # Generate final ID on approval (accept both "Approved" and "Within Spec")
            from swynix_mes.swynix_mes.api.casting_kiosk import generate_final_coil_id
            if qc_sample.status in ("Approved", "Within Spec") and not coil.is_scrap and not coil.coil_id:
                coil.coil_id = generate_final_coil_id(coil)
                
            # Handle rejection
            if qc_sample.status == "Rejected":
                coil.qc_status = "Rejected"
                coil.coil_status = "Rejected"
            
            # Handle Hold
            if qc_sample.status == "Hold":
                coil.qc_status = "Hold"
                coil.coil_status = "Hold"
            
            coil.flags.ignore_validate = True
            coil.save(ignore_permissions=True)


def get_action_message(action, sample_id):
    """Get success message for action."""
    messages = {
        "save": f"Sample {sample_id} saved",
        "approve": f"Sample {sample_id} approved - QC OK",
        "reject": f"Sample {sample_id} rejected",
        "correction_required": f"Correction request sent for sample {sample_id}",
        "hold": f"Sample {sample_id} placed on hold"
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
def get_qc_history_for_sample(batch=None, sample_id=None, sample_name=None):
    """
    Charge & correction history for a QC Sample (any source).
    Shows all charge entries before this sample, melt corrections, and previous decisions.
    """
    if not sample_name and sample_id:
        lookup_filters = {"sample_id": sample_id}
        if batch:
            lookup_filters["source_document"] = batch
        sample_name = frappe.db.get_value("QC Sample", lookup_filters, "name")
    
    if not sample_name:
        frappe.throw(_("Sample is required"))
    
    sample_doc = frappe.get_doc("QC Sample", sample_name)
    curr_time = get_datetime(sample_doc.sample_time) if sample_doc.sample_time else None
    
    # Charges and corrections pulled from melting batch context when available
    charges = []
    corrections = []
    correction_charges = []
    
    if sample_doc.melting_batch:
        batch_doc = frappe.get_doc("Melting Batch", sample_doc.melting_batch)
        
        for rm in batch_doc.raw_materials:
            rm_time = None
            if hasattr(rm, "posting_datetime") and rm.posting_datetime:
                rm_time = get_datetime(rm.posting_datetime)
            
            include = True
            if rm_time and curr_time:
                include = rm_time <= curr_time
            
            if include:
                entry = {
                    "idx": rm.idx,
                    "posting_datetime": str(rm.posting_datetime) if hasattr(rm, "posting_datetime") and rm.posting_datetime else None,
                    "item_code": rm.item_code,
                    "item_name": rm.item_name,
                    "ingredient_type": rm.ingredient_type,
                    "qty_kg": rm.qty_kg,
                    "source_bin": rm.source_bin,
                    "batch_no": rm.batch_no,
                    "is_correction": rm.is_correction
                }
                charges.append(entry)
                if rm.is_correction:
                    correction_charges.append(entry)
        
        for log in batch_doc.process_logs:
            if log.event_type != "Correction":
                continue
            log_time = get_datetime(log.log_time) if log.log_time else None
            include = True
            if log_time and curr_time:
                include = log_time <= curr_time
            if include:
                corrections.append({
                    "idx": log.idx,
                    "log_time": str(log.log_time) if log.log_time else None,
                    "event_type": log.event_type,
                    "sample_id": log.sample_id,
                    "note": log.note,
                    "temp_c": log.temp_c
                })
    
    # Previous QC samples for the same source
    samples_raw = frappe.get_all(
        "QC Sample",
        filters={
            "source_type": sample_doc.source_type,
            "source_document": sample_doc.source_document,
            "docstatus": ["<=", 1]
        },
        fields=["name", "sample_id", "sample_time", "status", "overall_result"],
        order_by="sample_time asc, creation asc"
    )
    
    samples_display = []
    current_idx = 0
    
    for idx, s in enumerate(samples_raw):
        status = s.status or "Pending"
        overall = s.overall_result
        
        if status in ("Approved", "Accepted") or overall == "In Spec":
            display_status = "Within Spec"
        elif status == "Rejected" or overall == "Out of Spec":
            display_status = "Out of Spec"
        elif status == "Correction Required":
            display_status = "Correction Asked"
        else:
            display_status = "Pending"
        
        is_current = s.name == sample_doc.name
        if is_current:
            current_idx = idx
        
        samples_display.append({
            "sample_id": s.sample_id,
            "sample_time": str(s.sample_time) if s.sample_time else None,
            "status": display_status,
            "is_current": is_current
        })
    
    return {
        "samples": samples_display,
        "charges": charges,
        "corrections": corrections,
        "correction_charges": correction_charges,
        "window": {
            "from": None,
            "to": str(curr_time) if curr_time else None
        },
        "current_sample": {
            "sample_id": sample_doc.sample_id,
            "sample_time": str(sample_doc.sample_time) if sample_doc.sample_time else None,
            "index": current_idx + 1,
            "total": len(samples_display)
        },
        "batch_info": {
            "name": sample_doc.melting_batch,
            "batch_id": sample_doc.melting_batch,
            "batch_start": None
        }
    }
