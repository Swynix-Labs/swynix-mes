# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

"""
Mother Coil Document Controller

Handles:
- Temp coil ID generation
- Final coil ID generation (only for approved, non-scrap coils)
- QC status synchronization
- Scrap marking
- Casting run totals updates
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate, now_datetime, getdate, flt
import re


class MotherCoil(Document):
    def validate(self):
        self.set_furnace_from_batch()
        self.generate_temp_coil_id()
        self.validate_dimensions()
    
    def on_update(self):
        self.generate_final_coil_id_if_approved()
        self.update_casting_run_totals()
    
    def before_submit(self):
        self.generate_final_coil_id_if_approved()
    
    def after_insert(self):
        self.update_casting_run_totals()
    
    def on_trash(self):
        # Update run totals when coil is deleted
        if self.casting_run:
            frappe.enqueue(
                "swynix_mes.swynix_mes.doctype.mother_coil.mother_coil.update_run_totals_async",
                run_name=self.casting_run,
                enqueue_after_commit=True
            )
    
    def set_furnace_from_batch(self):
        """Set furnace from melting batch if not set"""
        if self.melting_batch and not self.furnace:
            self.furnace = frappe.db.get_value("Melting Batch", self.melting_batch, "furnace")
    
    def validate_dimensions(self):
        """Validate dimension values are positive"""
        for field in ["planned_width_mm", "planned_gauge_mm", "planned_weight_mt",
                      "actual_width_mm", "actual_gauge_mm", "actual_weight_mt"]:
            val = getattr(self, field, None)
            if val is not None and val < 0:
                frappe.throw(_("{0} cannot be negative").format(field))
    
    def generate_temp_coil_id(self):
        """Generate temporary coil ID for shop floor use"""
        if not self.temp_coil_id:
            # Format: TMP-{caster}-{YYMMDD}-{seq}
            caster_id = self.caster or "X"
            # Extract just the caster number/code
            caster_code = re.sub(r'[^a-zA-Z0-9]', '', str(caster_id))[:8]
            date_part = getdate(self.cast_date or nowdate()).strftime("%y%m%d")
            
            # Get next sequence for this caster and date
            prefix = f"TMP-{caster_code}-{date_part}-"
            existing = frappe.db.sql("""
                SELECT temp_coil_id FROM `tabMother Coil`
                WHERE temp_coil_id LIKE %s
                ORDER BY temp_coil_id DESC
                LIMIT 1
            """, (prefix + "%",), as_dict=True)
            
            if existing and existing[0].temp_coil_id:
                try:
                    last_seq = int(existing[0].temp_coil_id.split("-")[-1])
                    next_seq = last_seq + 1
                except (ValueError, IndexError):
                    next_seq = 1
            else:
                next_seq = 1
            
            self.temp_coil_id = f"{prefix}{next_seq:03d}"
    
    def generate_final_coil_id_if_approved(self):
        """
        Generate final coil ID only for approved, non-scrap coils.
        
        Format: C{CasterNo}{YY}{MonthCode}{DD}{Seq3}
        Example: C125J10001 = Caster 1, 2025, October, Day 10, Sequence 001
        """
        if (
            self.qc_status == "Approved" 
            and not self.coil_id 
            and not self.is_scrap
            and self.caster 
            and self.cast_date
        ):
            from swynix_mes.swynix_mes.utils.coil_utils import (
                generate_coil_id, 
                validate_coil_id_unique
            )
            
            # Get caster number from caster_id
            caster_no = get_caster_number(self.caster)
            
            # Generate the coil ID
            new_coil_id = generate_coil_id(caster_no, self.cast_date)
            
            # Validate uniqueness
            validate_coil_id_unique(new_coil_id, exclude_name=self.name)
            
            self.coil_id = new_coil_id
            
            # Also update in database immediately
            if self.name and not self.flags.in_insert:
                frappe.db.set_value(
                    "Mother Coil", 
                    self.name, 
                    "coil_id", 
                    self.coil_id, 
                    update_modified=False
                )
    
    def update_casting_run_totals(self):
        """Update the totals on the parent Casting Run"""
        if self.casting_run:
            try:
                update_run_totals(self.casting_run)
            except Exception as e:
                frappe.log_error(
                    title="Casting Run Totals Update Error",
                    message=f"Error updating totals for run {self.casting_run}: {str(e)}"
                )
    
    def mark_as_scrap(self, reason=None, weight=None):
        """
        Mark coil as scrap.
        
        Args:
            reason: Scrap reason text
            weight: Scrap weight in MT (defaults to actual or planned weight)
        """
        self.is_scrap = 1
        self.scrap_reason = reason or "Marked as scrap"
        self.scrap_weight_mt = weight or self.actual_weight_mt or self.planned_weight_mt
        self.qc_status = "Rejected"
        self.coil_id = None  # Clear final coil ID
        self.save()
    
    def approve_qc(self, comments=None):
        """
        Approve the coil QC.
        
        This will trigger final coil ID generation.
        
        Args:
            comments: Optional QC comments
        """
        self.qc_status = "Approved"
        if comments:
            self.qc_comments = comments
        self.save()
    
    def reject_qc(self, reason=None, mark_scrap=False):
        """
        Reject the coil QC.
        
        Args:
            reason: Rejection reason
            mark_scrap: If True, also mark the coil as scrap
        """
        self.qc_status = "Rejected"
        if reason:
            self.qc_comments = reason
        
        if mark_scrap:
            self.is_scrap = 1
            self.scrap_reason = reason or "Rejected by QC"
            self.coil_id = None
        
        self.save()
    
    def set_qc_deviation_summary(self, summary):
        """
        Set the QC deviation summary from QC kiosk.
        
        Args:
            summary: Deviation summary text
        """
        self.qc_deviation_summary = summary
        frappe.db.set_value(
            "Mother Coil", 
            self.name, 
            "qc_deviation_summary", 
            summary, 
            update_modified=False
        )


def get_caster_number(caster_id):
    """
    Extract numeric part from caster ID.
    
    Examples:
        'Caster1' -> 1
        'Caster 2' -> 2
        'C3' -> 3
        '1' -> 1
    
    Args:
        caster_id: Caster identifier string
        
    Returns:
        int: Numeric part of caster ID, defaults to 1 if not found
    """
    if not caster_id:
        return 1
    
    # Try to extract digits from the caster ID
    match = re.search(r'\d+', str(caster_id))
    if match:
        return int(match.group())
    
    # Fallback: return 1
    return 1


def update_run_totals(run_name):
    """
    Update the totals on a Casting Run based on its coils.
    
    Calculates:
    - total_coils: Count of all coils
    - total_cast_weight: Sum of actual weights
    - total_scrap_weight: Sum of scrap coil weights
    
    Args:
        run_name: Name of the Casting Run document
    """
    if not run_name:
        return
    
    coils = frappe.get_all(
        "Mother Coil",
        filters={"casting_run": run_name},
        fields=["actual_weight_mt", "is_scrap", "scrap_weight_mt"]
    )
    
    total_weight = 0
    scrap_weight = 0
    
    for c in coils:
        weight = flt(c.actual_weight_mt or 0)
        total_weight += weight
        if c.is_scrap:
            scrap_weight += flt(c.scrap_weight_mt or c.actual_weight_mt or 0)
    
    frappe.db.set_value("Casting Run", run_name, {
        "total_coils": len(coils),
        "total_cast_weight": flt(total_weight, 3),
        "total_scrap_weight": flt(scrap_weight, 3)
    }, update_modified=False)


def update_run_totals_async(run_name):
    """Async wrapper for update_run_totals"""
    update_run_totals(run_name)
    frappe.db.commit()


@frappe.whitelist()
def approve_mother_coil(coil_name, comments=None):
    """
    API to approve a mother coil.
    
    Args:
        coil_name: Name of the Mother Coil
        comments: Optional QC comments
        
    Returns:
        dict with coil_id if generated
    """
    if not coil_name:
        frappe.throw(_("Coil name is required"))
    
    coil = frappe.get_doc("Mother Coil", coil_name)
    coil.approve_qc(comments)
    
    return {
        "name": coil.name,
        "qc_status": coil.qc_status,
        "coil_id": coil.coil_id
    }


@frappe.whitelist()
def mark_mother_coil_scrap(coil_name, reason=None, weight=None):
    """
    API to mark a mother coil as scrap.
    
    Args:
        coil_name: Name of the Mother Coil
        reason: Scrap reason
        weight: Scrap weight in MT
        
    Returns:
        dict with updated coil info
    """
    if not coil_name:
        frappe.throw(_("Coil name is required"))
    
    coil = frappe.get_doc("Mother Coil", coil_name)
    coil.mark_as_scrap(reason, weight)
    
    return {
        "name": coil.name,
        "is_scrap": coil.is_scrap,
        "qc_status": coil.qc_status
    }
