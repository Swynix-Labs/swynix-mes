"""
Custom fields for ERPNext Workstation to support Casting MES
This adds workstation_type and caster_no fields
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def create_workstation_custom_fields():
    """
    Add custom fields to Workstation for MES
    - workstation_type: Furnace, Caster, Mill, Slitter
    - caster_no: Required only for Caster type
    """
    custom_fields = {
        "Workstation": [
            {
                "fieldname": "workstation_type",
                "label": "Workstation Type",
                "fieldtype": "Select",
                "options": "\nFurnace\nCaster\nMill\nSlitter",
                "insert_after": "workstation_name",
                "in_list_view": 1,
                "in_standard_filter": 1,
                "reqd": 0,
                "description": "Type of workstation for MES operations"
            },
            {
                "fieldname": "caster_no",
                "label": "Caster No",
                "fieldtype": "Int",
                "insert_after": "workstation_type",
                "depends_on": "eval:doc.workstation_type=='Caster'",
                "mandatory_depends_on": "eval:doc.workstation_type=='Caster'",
                "description": "Caster number (1, 2, 3, etc.) - used in coil numbering"
            }
        ]
    }
    
    create_custom_fields(custom_fields, update=True)
    print("✅ Workstation custom fields created successfully")


def execute():
    """Execute from bench console or setup"""
    create_workstation_custom_fields()
