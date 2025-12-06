# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

"""
Coil ID Generation Utilities

Coil ID Format: C{CasterNo}{YY}{MonthCode}{DD}{Seq3}

Where:
- CasterNo = numeric part of caster (Caster1 → 1)
- YY = last two digits of cast_date year (2025 → 25)
- MonthCode = A–L for Jan–Dec (1→A, …, 10→J, 11→K, 12→L)
- DD = 2-digit day (10 → 10)
- Seq3 = 3-digit sequence per (caster + cast_date) counting only Approved coils

Example:
- First approved coil on 10-10-2025 from Caster 1 → C125J10001
"""

import frappe
from frappe.utils import getdate


# Month codes: January=A, February=B, ..., October=J, November=K, December=L
MONTH_CODES = {
    1: 'A', 2: 'B', 3: 'C', 4: 'D', 5: 'E', 6: 'F',
    7: 'G', 8: 'H', 9: 'I', 10: 'J', 11: 'K', 12: 'L'
}


def get_month_code(date):
    """
    Get month code for a date.
    
    Args:
        date: Date string or date object
        
    Returns:
        str: Month code (A-L for Jan-Dec)
    """
    date_obj = getdate(date)
    month = date_obj.month
    return MONTH_CODES.get(month, 'X')


def generate_coil_id(caster_no, cast_date):
    """
    Generate final coil ID for an approved coil.
    
    Format: C{CasterNo}{YY}{MonthCode}{DD}{Seq3}
    
    Args:
        caster_no: int - Numeric part of caster ID (e.g., 1 for Caster1)
        cast_date: Date string or date object
        
    Returns:
        str: Generated coil ID (e.g., "C125J10001")
    """
    date_obj = getdate(cast_date)
    
    # Build components
    caster_str = str(caster_no)
    year_str = str(date_obj.year)[-2:]  # Last 2 digits
    month_code = get_month_code(date_obj)
    day_str = f"{date_obj.day:02d}"
    
    # Build prefix for this caster + date
    prefix = f"C{caster_str}{year_str}{month_code}{day_str}"
    
    # Find the next sequence number
    # Query for max existing coil_id with this prefix
    existing = frappe.db.sql("""
        SELECT coil_id FROM `tabMother Coil`
        WHERE coil_id LIKE %s
        AND qc_status = 'Approved'
        AND is_scrap = 0
        ORDER BY coil_id DESC
        LIMIT 1
    """, (prefix + "%",), as_dict=True)
    
    if existing and existing[0].coil_id:
        # Extract the sequence part (last 3 digits)
        existing_id = existing[0].coil_id
        try:
            # The sequence is after the prefix
            seq_str = existing_id[len(prefix):]
            last_seq = int(seq_str)
            next_seq = last_seq + 1
        except (ValueError, IndexError):
            next_seq = 1
    else:
        next_seq = 1
    
    # Check if sequence exceeds 999
    if next_seq > 999:
        frappe.throw(f"Coil ID sequence exceeded 999 for {prefix}. Please contact admin.")
    
    # Build final coil ID
    coil_id = f"{prefix}{next_seq:03d}"
    
    return coil_id


def validate_coil_id_unique(coil_id, exclude_name=None):
    """
    Validate that a coil ID is unique.
    
    Args:
        coil_id: str - Coil ID to validate
        exclude_name: str - Optional document name to exclude from check
        
    Returns:
        bool: True if unique, raises exception otherwise
    """
    if not coil_id:
        return True
    
    filters = {"coil_id": coil_id}
    if exclude_name:
        filters["name"] = ("!=", exclude_name)
    
    existing = frappe.db.exists("Mother Coil", filters)
    if existing:
        frappe.throw(f"Coil ID {coil_id} already exists")
    
    return True


def get_coil_id_prefix(caster_no, cast_date):
    """
    Get the prefix for a coil ID (without sequence).
    
    Args:
        caster_no: int - Numeric part of caster ID
        cast_date: Date string or date object
        
    Returns:
        str: Coil ID prefix (e.g., "C125J10")
    """
    date_obj = getdate(cast_date)
    
    caster_str = str(caster_no)
    year_str = str(date_obj.year)[-2:]
    month_code = get_month_code(date_obj)
    day_str = f"{date_obj.day:02d}"
    
    return f"C{caster_str}{year_str}{month_code}{day_str}"


def get_approved_coil_count_for_date(caster_no, cast_date):
    """
    Get count of approved coils for a caster on a specific date.
    
    Args:
        caster_no: int - Numeric part of caster ID
        cast_date: Date string or date object
        
    Returns:
        int: Count of approved coils
    """
    prefix = get_coil_id_prefix(caster_no, cast_date)
    
    count = frappe.db.sql("""
        SELECT COUNT(*) FROM `tabMother Coil`
        WHERE coil_id LIKE %s
        AND qc_status = 'Approved'
        AND is_scrap = 0
    """, (prefix + "%",))[0][0]
    
    return count or 0





