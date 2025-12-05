# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

"""
Composition Check Utility - Evaluate samples against Alloy Chemical Composition Master rules

This module provides comprehensive evaluation of:
- Normal Limit: Single element range checks
- Sum Limit: Sum of multiple elements against limit
- Ratio: Ratio between two elements
- Remainder: Aluminium minimum % or remainder conditions
"""

import frappe
from frappe import _
from frappe.utils import flt


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


def evaluate_sample_against_alloy(alloy_name, sample_elements):
    """
    Evaluate sample element readings against Alloy Chemical Composition Master rules.
    
    Args:
        alloy_name: Item name/code for the alloy (e.g., '1235')
        sample_elements: dict of element readings like {'Si': 0.18, 'Fe': 0.42, 'Cu': 0.01, ...}
        
    Returns:
        dict with:
        - per_element_results: List of individual element evaluations for Normal Limit rules
        - rule_results: List of all rule evaluations (Normal, Sum, Ratio, Remainder)
        - deviation_messages: Human-readable failure messages for UI
        - overall_pass: Boolean indicating if all rules pass
        - accm_name: Name of the ACCM document used
    """
    result = {
        "per_element_results": [],
        "rule_results": [],
        "deviation_messages": [],
        "overall_pass": True,
        "accm_name": None
    }
    
    # Get active composition master
    accm = get_active_composition_master(alloy_name)
    if not accm:
        return result
    
    result["accm_name"] = accm.name
    
    # Helper to get element value from sample
    def get_val(symbol):
        """Get element value from sample, handling different naming conventions."""
        if not symbol:
            return 0
        
        # Try direct lookup
        if symbol in sample_elements:
            return flt(sample_elements.get(symbol, 0) or 0)
        
        # Try element code conversion
        elem_code = get_element_code(symbol)
        if elem_code and elem_code in sample_elements:
            return flt(sample_elements.get(elem_code, 0) or 0)
        
        # Try lowercase
        if symbol.lower() in sample_elements:
            return flt(sample_elements.get(symbol.lower(), 0) or 0)
        
        return 0
    
    # Process each composition rule
    for rule in accm.composition_rules or []:
        ctype = rule.condition_type
        
        # Skip Free Text rules - they're informational only
        if ctype == "Free Text":
            continue
        
        # Gather elements from rule
        elems = []
        for field in ["element_1", "element_2", "element_3"]:
            elem = getattr(rule, field, None)
            if elem:
                elems.append(elem)
        
        if not elems:
            continue
        
        # Get element codes for display
        elem_codes = [get_element_code(e) for e in elems]
        
        value = None
        description = ""
        passed = True
        spec_min = None
        spec_max = None
        expected_text = ""
        
        if ctype == "Normal Limit":
            # Single element check
            symbol = elems[0]
            elem_code = elem_codes[0]
            value = get_val(symbol)
            description = elem_code
            
            limit_type = rule.limit_type
            spec_min = flt(rule.min_percentage) if rule.min_percentage is not None else None
            spec_max = flt(rule.max_percentage) if rule.max_percentage is not None else None
            
            passed, expected_text = evaluate_limit(value, spec_min, spec_max, limit_type, elem_code)
            
            # Add to per_element_results
            result["per_element_results"].append({
                "element": elem_code,
                "element_item": symbol,
                "spec_min": spec_min,
                "spec_max": spec_max,
                "limit_type": limit_type,
                "actual": value,
                "pass_fail": passed,
                "expected_text": expected_text
            })
            
        elif ctype == "Sum Limit":
            # Sum of multiple elements
            value = sum(get_val(e) for e in elems)
            sum_label = " + ".join(elem_codes)
            description = sum_label
            
            limit_type = rule.sum_limit_type
            spec_min = flt(rule.sum_min_percentage) if rule.sum_min_percentage is not None else None
            spec_max = flt(rule.sum_max_percentage) if rule.sum_max_percentage is not None else None
            
            passed, expected_text = evaluate_limit(value, spec_min, spec_max, limit_type, sum_label)
            
        elif ctype == "Ratio":
            # Ratio between two elements
            if len(elems) >= 2:
                elem1, elem2 = elems[0], elems[1]
                code1, code2 = elem_codes[0], elem_codes[1]
                
                val1 = get_val(elem1)
                val2 = get_val(elem2)
                
                ratio_label = f"{code1}/{code2}"
                description = ratio_label
                
                if val2 == 0:
                    # Division by zero
                    value = None
                    passed = False
                    expected_text = f"Cannot evaluate ratio {ratio_label} because {code2} is 0"
                    result["deviation_messages"].append(expected_text)
                else:
                    value = val1 / val2
                    
                    # Get expected ratio from rule
                    ratio_val_1 = flt(rule.ratio_value_1 or 0)
                    ratio_val_2 = flt(rule.ratio_value_2 or 1)
                    
                    if ratio_val_2 > 0:
                        expected_ratio = ratio_val_1 / ratio_val_2
                        
                        # Allow tolerance (typically ±10% or ±0.5)
                        tolerance = max(0.1 * expected_ratio, 0.3)
                        
                        if abs(value - expected_ratio) <= tolerance:
                            passed = True
                        else:
                            passed = False
                        
                        if expected_ratio == int(expected_ratio):
                            expected_text = f"{ratio_label} should be ~{int(expected_ratio)}:1; actual = {round(value, 2)}"
                        else:
                            expected_text = f"{ratio_label} should be ~{round(expected_ratio, 2)}; actual = {round(value, 2)}"
                        
                        spec_min = expected_ratio - tolerance
                        spec_max = expected_ratio + tolerance
                    else:
                        passed = True  # Cannot evaluate
                        expected_text = ""
                        
        elif ctype == "Remainder":
            # Remainder check (usually Aluminium)
            symbol = elems[0] if elems else "Al"
            elem_code = get_element_code(symbol) or "Al"
            value = get_val(symbol)
            description = f"{elem_code} (Remainder)"
            
            spec_min = flt(rule.remainder_min_percentage) if rule.remainder_min_percentage else None
            
            if spec_min is not None:
                if value >= spec_min:
                    passed = True
                else:
                    passed = False
                expected_text = f"{elem_code} should be ≥ {spec_min}%; actual = {round(value, 4)}%"
            else:
                # Just "Remainder" without specific min - always pass
                passed = True
                expected_text = f"{elem_code} = Remainder"
            
            # Add to per_element_results for Al
            result["per_element_results"].append({
                "element": elem_code,
                "element_item": symbol,
                "spec_min": spec_min,
                "spec_max": None,
                "limit_type": "Minimum",
                "actual": value,
                "pass_fail": passed,
                "expected_text": expected_text
            })
        
        # Build rule result entry
        rule_result = {
            "description": description,
            "condition_type": ctype,
            "limit_type": getattr(rule, "limit_type", None) or getattr(rule, "sum_limit_type", None),
            "value": round(value, 4) if value is not None else None,
            "min": spec_min,
            "max": spec_max,
            "pass_fail": passed,
            "expected_text": expected_text
        }
        result["rule_results"].append(rule_result)
        
        # Add to deviation messages if failed
        if not passed and expected_text:
            # Format message based on condition type
            if ctype == "Sum Limit":
                msg = f"{description} should be {format_limit_text(spec_min, spec_max, rule_result['limit_type'])}%; actual = {round(value, 4) if value else 'N/A'}%"
            elif ctype == "Ratio":
                msg = expected_text
            elif ctype == "Remainder":
                msg = expected_text
            else:
                msg = expected_text
            
            if msg not in result["deviation_messages"]:
                result["deviation_messages"].append(msg)
    
    # Determine overall pass
    result["overall_pass"] = all(r["pass_fail"] for r in result["rule_results"])
    
    return result


def evaluate_limit(value, spec_min, spec_max, limit_type, label):
    """
    Evaluate a value against min/max limits based on limit type.
    
    Returns:
        tuple: (passed: bool, expected_text: str)
    """
    if value is None:
        return True, ""
    
    passed = True
    expected_text = ""
    
    if limit_type == "Maximum":
        if spec_max is not None:
            if value <= spec_max:
                passed = True
            else:
                passed = False
            expected_text = f"{label} should be ≤ {spec_max}%; actual = {round(value, 4)}%"
            
    elif limit_type == "Minimum":
        if spec_min is not None:
            if value >= spec_min:
                passed = True
            else:
                passed = False
            expected_text = f"{label} should be ≥ {spec_min}%; actual = {round(value, 4)}%"
            
    elif limit_type == "Equal To":
        target = spec_min or spec_max
        if target is not None:
            tolerance = 0.01
            if abs(value - target) <= tolerance:
                passed = True
            else:
                passed = False
            expected_text = f"{label} should be = {target}%; actual = {round(value, 4)}%"
            
    elif limit_type in ("Range", "Between") or (spec_min is not None and spec_max is not None):
        # Range check
        if spec_min is not None and value < spec_min:
            passed = False
            expected_text = f"{label} should be ≥ {spec_min}%; actual = {round(value, 4)}%"
        elif spec_max is not None and value > spec_max:
            passed = False
            expected_text = f"{label} should be ≤ {spec_max}%; actual = {round(value, 4)}%"
        else:
            passed = True
            expected_text = f"{label} is within {spec_min} – {spec_max}%"
            
    else:
        # Fallback - check min and max separately
        if spec_min is not None and value < spec_min:
            passed = False
            expected_text = f"{label} should be ≥ {spec_min}%; actual = {round(value, 4)}%"
        elif spec_max is not None and value > spec_max:
            passed = False
            expected_text = f"{label} should be ≤ {spec_max}%; actual = {round(value, 4)}%"
    
    return passed, expected_text


def format_limit_text(spec_min, spec_max, limit_type):
    """Format limit as human-readable text."""
    if limit_type == "Maximum" and spec_max is not None:
        return f"≤ {spec_max}"
    elif limit_type == "Minimum" and spec_min is not None:
        return f"≥ {spec_min}"
    elif spec_min is not None and spec_max is not None:
        return f"between {spec_min} and {spec_max}"
    elif spec_max is not None:
        return f"≤ {spec_max}"
    elif spec_min is not None:
        return f"≥ {spec_min}"
    return ""


def evaluate_sample_against_alloy_spec(alloy, spec_docname, sample_row):
    """
    Centralized evaluation function that returns structured results.
    
    Args:
        alloy: Alloy code (e.g., '1235')
        spec_docname: ACCM document name (e.g., 'ACCM-1235-0009') or None to auto-find
        sample_row: dict with element values like {'si': 0.18, 'fe': 0.42, 'cu': 0.01, ...}
                   or can use field names like si_percent, fe_percent, etc.
    
    Returns:
        dict with:
        - per_element_results: List of element evaluations
        - sum_limits: List of sum limit rule evaluations
        - ratios: List of ratio rule evaluations
        - deviation_messages: List of human-readable deviation messages
        - deviation_count: Integer count of failed rules
        - overall_status: "Within Spec" or "Out of Spec"
    """
    # Convert sample_row to element code dict
    sample_elements = {}
    ELEMENT_FIELD_MAP = {
        "si": "Si", "si_percent": "Si",
        "fe": "Fe", "fe_percent": "Fe",
        "cu": "Cu", "cu_percent": "Cu",
        "mn": "Mn", "mn_percent": "Mn",
        "mg": "Mg", "mg_percent": "Mg",
        "zn": "Zn", "zn_percent": "Zn",
        "ti": "Ti", "ti_percent": "Ti",
        "al": "Al", "al_percent": "Al",
        "s": "S", "s_pct": "S"
    }
    
    for key, value in sample_row.items():
        if value is not None:
            elem_code = ELEMENT_FIELD_MAP.get(key.lower())
            if elem_code:
                sample_elements[elem_code] = flt(value, 4)
    
    # Evaluate using existing function
    eval_result = evaluate_sample_against_alloy(alloy, sample_elements)
    
    # Structure the results as required
    per_element_results = []
    sum_limits = []
    ratios = []
    deviation_messages = eval_result.get("deviation_messages", [])
    
    # Categorize rule results
    for rule in eval_result.get("rule_results", []):
        ctype = rule.get("condition_type", "")
        
        if ctype == "Normal Limit":
            per_element_results.append({
                "element": rule.get("description", ""),
                "spec_min": rule.get("min"),
                "spec_max": rule.get("max"),
                "actual": rule.get("value"),
                "pass": rule.get("pass_fail", True)
            })
        elif ctype == "Sum Limit":
            sum_limits.append({
                "rule_label": rule.get("description", ""),
                "spec_text": rule.get("expected_text", ""),
                "actual_value": rule.get("value"),
                "pass": rule.get("pass_fail", True)
            })
        elif ctype == "Ratio":
            ratios.append({
                "rule_label": rule.get("description", ""),
                "spec_text": rule.get("expected_text", ""),
                "actual_value": rule.get("value"),
                "pass": rule.get("pass_fail", True)
            })
    
    # Determine overall status
    overall_pass = eval_result.get("overall_pass", True)
    overall_status = "Within Spec" if overall_pass else "Out of Spec"
    
    deviation_count = len(deviation_messages)
    
    return {
        "per_element_results": per_element_results,
        "sum_limits": sum_limits,
        "ratios": ratios,
        "deviation_messages": deviation_messages,
        "deviation_count": deviation_count,
        "overall_status": overall_status
    }


def format_deviations_for_storage(evaluation_result):
    """
    Format evaluation result deviations into a structured format for storage.
    
    Args:
        evaluation_result: Result dict from evaluate_sample_against_alloy
        
    Returns:
        tuple: (deviation_summary: str, deviation_detail: str (JSON))
    """
    import json
    
    deviations = []
    summary_parts = []
    
    for rule in evaluation_result.get("rule_results", []):
        if not rule.get("pass_fail", True):
            # Failed rule - format for storage
            ctype = rule.get("condition_type", "")
            desc = rule.get("description", "")
            expected = rule.get("expected_text", "")
            actual = rule.get("value")
            
            # Determine severity
            severity = "high"  # Default to high for any failure
            
            # Determine code
            if ctype == "Sum Limit":
                code = desc.replace(" + ", "_").replace(" ", "_").upper()
                summary_parts.append(desc)
            elif ctype == "Ratio":
                code = desc.replace("/", "_").replace(" ", "_").upper()
                summary_parts.append(desc)
            elif ctype == "Remainder":
                code = "AL_REMAINDER"
                summary_parts.append("Al")
            else:
                code = desc.replace(" ", "_").upper()
                summary_parts.append(desc)
            
            # Extract expected text from expected_text
            expected_clean = ""
            if expected:
                if "should be" in expected:
                    # Extract part after "should be"
                    parts = expected.split("should be", 1)
                    if len(parts) > 1:
                        expected_clean = parts[1].strip()
                        # Remove "actual = X" part if present
                        if "actual" in expected_clean:
                            expected_clean = expected_clean.split("actual")[0].strip()
                else:
                    expected_clean = expected
            
            deviation = {
                "code": code,
                "label": desc,
                "expected": expected_clean,
                "actual": str(round(actual, 4)) if actual is not None else "N/A",
                "severity": severity,
                "type": ctype.lower().replace(" ", "_")
            }
            deviations.append(deviation)
    
    # Create summary
    if summary_parts:
        summary = ", ".join(summary_parts[:5])  # Limit to 5 items
        if len(summary_parts) > 5:
            summary += f" (+{len(summary_parts) - 5} more)"
    else:
        summary = "No deviations"
    
    # Format detail as JSON
    detail_json = json.dumps(deviations, indent=2) if deviations else "[]"
    
    return summary, detail_json


@frappe.whitelist()
def evaluate_sample_api(alloy_name, sample_elements):
    """
    API wrapper for evaluate_sample_against_alloy.
    
    Args:
        alloy_name: Alloy item name
        sample_elements: JSON string or dict of element readings
        
    Returns:
        Evaluation result dict
    """
    import json
    
    if isinstance(sample_elements, str):
        sample_elements = json.loads(sample_elements)
    
    return evaluate_sample_against_alloy(alloy_name, sample_elements or {})

