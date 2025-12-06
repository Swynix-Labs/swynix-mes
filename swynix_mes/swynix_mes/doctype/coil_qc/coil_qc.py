# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

"""
Coil QC Document Controller

Handles dimensional and surface quality control for Mother Coils.
Syncs QC status back to Mother Coil and triggers final coil ID generation.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class CoilQC(Document):
    def validate(self):
        self.validate_mother_coil()
        self.set_casting_run_from_coil()
        self.validate_dimensions()
        self.check_defect_severity()
    
    def on_update(self):
        # Sync status to mother coil even before submit
        self.sync_to_mother_coil()
    
    def on_submit(self):
        self.update_mother_coil_qc_status()
    
    def on_cancel(self):
        self.revert_mother_coil_qc_status()
    
    def validate_mother_coil(self):
        """Validate mother coil exists"""
        if not self.mother_coil:
            frappe.throw(_("Mother Coil is required"))
        
        # Check if mother coil exists
        if not frappe.db.exists("Mother Coil", self.mother_coil):
            frappe.throw(_("Mother Coil {0} does not exist").format(self.mother_coil))
    
    def set_casting_run_from_coil(self):
        """Set casting run from mother coil if not set"""
        if not self.casting_run and self.mother_coil:
            self.casting_run = frappe.db.get_value("Mother Coil", self.mother_coil, "casting_run")
    
    def validate_dimensions(self):
        """Validate measured dimensions are positive"""
        for field in ["width_mm_measured", "gauge_mm_measured", "coil_weight_mt_measured"]:
            val = getattr(self, field, None)
            if val is not None and val < 0:
                frappe.throw(_("{0} cannot be negative").format(self.meta.get_label(field)))
    
    def check_defect_severity(self):
        """Check if any critical defects exist - auto-set status to Hold or Scrap"""
        if not self.surface_defects:
            return
        
        has_critical = any(d.severity == "Critical" for d in self.surface_defects)
        has_major = any(d.severity == "Major" for d in self.surface_defects)
        
        # Auto-suggestion based on defects (can be overridden by user)
        if has_critical and self.qc_status == "Pending":
            frappe.msgprint(
                _("Critical defects found. Consider marking as Scrap or Hold."),
                indicator="red"
            )
        elif has_major and self.qc_status == "Pending":
            frappe.msgprint(
                _("Major defects found. Review carefully before approval."),
                indicator="orange"
            )
    
    def sync_to_mother_coil(self):
        """
        Sync measured dimensions to mother coil.
        Called on save (before submit) to keep dimensions in sync.
        """
        if not self.mother_coil:
            return
        
        updates = {}
        
        # Sync measured dimensions
        if self.width_mm_measured:
            updates["actual_width_mm"] = self.width_mm_measured
        if self.gauge_mm_measured:
            updates["actual_gauge_mm"] = self.gauge_mm_measured
        if self.coil_weight_mt_measured:
            updates["actual_weight_mt"] = self.coil_weight_mt_measured
        
        if updates:
            frappe.db.set_value("Mother Coil", self.mother_coil, updates, update_modified=False)
    
    def update_mother_coil_qc_status(self):
        """
        Update mother coil QC status based on this QC result.
        This is the main logic for connecting Coil QC to Mother Coil.
        """
        if not self.mother_coil:
            return
        
        coil = frappe.get_doc("Mother Coil", self.mother_coil)
        
        # Map Coil QC status to Mother Coil qc_status
        status_map = {
            "Approved": "Approved",
            "Rework": "Correction Required",
            "Scrap": "Rejected",
            "Hold": "Hold",
            "Pending": "Pending"
        }
        
        new_status = status_map.get(self.qc_status, "Pending")
        
        # Handle scrap case
        if self.qc_status == "Scrap":
            coil.is_scrap = 1
            coil.scrap_reason = self.qc_remarks or "Marked as scrap during Coil QC"
            coil.scrap_weight_mt = self.coil_weight_mt_measured or coil.actual_weight_mt or coil.planned_weight_mt
            coil.coil_id = None  # Clear any existing final coil ID
        
        # Update actual dimensions if measured
        if self.width_mm_measured:
            coil.actual_width_mm = self.width_mm_measured
        if self.gauge_mm_measured:
            coil.actual_gauge_mm = self.gauge_mm_measured
        if self.coil_weight_mt_measured:
            coil.actual_weight_mt = self.coil_weight_mt_measured
        
        # Update QC status
        coil.qc_status = new_status
        
        # Append QC remarks to comments
        if self.qc_remarks:
            existing_comments = coil.qc_comments or ""
            separator = "\n" if existing_comments else ""
            coil.qc_comments = f"{existing_comments}{separator}[Coil QC] {self.qc_remarks}"
        
        # Build deviation summary from defects
        if self.surface_defects:
            defect_summary = self._build_defect_summary()
            if defect_summary:
                existing_dev = coil.qc_deviation_summary or ""
                separator = "\n" if existing_dev else ""
                coil.qc_deviation_summary = f"{existing_dev}{separator}{defect_summary}"
        
        coil.flags.ignore_validate = True
        coil.save()
        
        # If approved and not scrap, this will trigger coil_id generation
        if self.qc_status == "Approved" and not coil.is_scrap:
            coil.reload()
            if coil.coil_id:
                frappe.msgprint(
                    _("Final Coil ID generated: {0}").format(coil.coil_id), 
                    indicator="green"
                )
    
    def _build_defect_summary(self):
        """Build a summary string from surface defects"""
        if not self.surface_defects:
            return ""
        
        defects = []
        for d in self.surface_defects:
            parts = [d.defect_type]
            if d.location:
                parts.append(f"at {d.location}")
            if d.severity:
                parts.append(f"({d.severity})")
            defects.append(" ".join(parts))
        
        return "Surface defects: " + ", ".join(defects)
    
    def revert_mother_coil_qc_status(self):
        """Revert mother coil QC status when this QC is cancelled"""
        if not self.mother_coil:
            return
        
        # Check if there are other submitted Coil QC records for this coil
        other_qc = frappe.db.exists("Coil QC", {
            "mother_coil": self.mother_coil,
            "docstatus": 1,
            "name": ("!=", self.name)
        })
        
        if not other_qc:
            # Revert to pending - but don't change scrap status if already scrap
            coil = frappe.get_doc("Mother Coil", self.mother_coil)
            if not coil.is_scrap:
                coil.qc_status = "Pending"
                coil.flags.ignore_validate = True
                coil.save()


# ==================== API Functions ====================

@frappe.whitelist()
def quick_approve(coil_qc_name):
    """
    Quick approve a Coil QC - sets status to Approved and submits.
    
    Args:
        coil_qc_name: Name of the Coil QC document
        
    Returns:
        dict with coil_id if generated
    """
    if not coil_qc_name:
        frappe.throw(_("Coil QC name is required"))
    
    qc = frappe.get_doc("Coil QC", coil_qc_name)
    
    if qc.docstatus == 1:
        frappe.throw(_("Coil QC is already submitted"))
    
    qc.qc_status = "Approved"
    qc.submit()
    
    # Get the updated mother coil
    coil = frappe.get_doc("Mother Coil", qc.mother_coil)
    
    return {
        "name": qc.name,
        "qc_status": qc.qc_status,
        "mother_coil": qc.mother_coil,
        "coil_id": coil.coil_id
    }


@frappe.whitelist()
def quick_scrap(coil_qc_name, reason=None):
    """
    Quick mark as scrap - sets status to Scrap and submits.
    
    Args:
        coil_qc_name: Name of the Coil QC document
        reason: Scrap reason
        
    Returns:
        dict with updated info
    """
    if not coil_qc_name:
        frappe.throw(_("Coil QC name is required"))
    
    qc = frappe.get_doc("Coil QC", coil_qc_name)
    
    if qc.docstatus == 1:
        frappe.throw(_("Coil QC is already submitted"))
    
    qc.qc_status = "Scrap"
    qc.qc_remarks = reason or "Marked as scrap"
    qc.submit()
    
    return {
        "name": qc.name,
        "qc_status": qc.qc_status,
        "mother_coil": qc.mother_coil
    }


@frappe.whitelist()
def get_coil_qc_summary(mother_coil):
    """
    Get QC summary for a mother coil.
    
    Args:
        mother_coil: Name of the Mother Coil
        
    Returns:
        dict with QC info
    """
    if not mother_coil:
        return None
    
    # Get latest Coil QC for this coil
    qc = frappe.db.get_value(
        "Coil QC",
        {"mother_coil": mother_coil},
        ["name", "qc_status", "qc_remarks", "docstatus",
         "width_mm_measured", "gauge_mm_measured", "coil_weight_mt_measured"],
        as_dict=True,
        order_by="creation desc"
    )
    
    if not qc:
        return {"exists": False}
    
    # Get defect count
    defect_count = frappe.db.count("Coil Surface Defect", {"parent": qc.name})
    
    return {
        "exists": True,
        "name": qc.name,
        "qc_status": qc.qc_status,
        "qc_remarks": qc.qc_remarks,
        "is_submitted": qc.docstatus == 1,
        "defect_count": defect_count,
        "width_mm_measured": qc.width_mm_measured,
        "gauge_mm_measured": qc.gauge_mm_measured,
        "coil_weight_mt_measured": qc.coil_weight_mt_measured
    }
