# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

"""
Casting Run Document Controller

Handles:
- Run lifecycle (Planned → Casting → Completed/Aborted)
- Coil tracking and totals calculation
- Status synchronization with PPC Casting Plan
- Validation of single active run per caster
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime


class CastingRun(Document):
    def validate(self):
        self.validate_no_duplicate_active_run()
        self.set_furnace_from_batch()
        self.update_totals_from_coils()
    
    def on_update(self):
        if self.status == "Completed":
            self.trigger_final_coil_ids()
        self.sync_to_casting_plan()

    def trigger_final_coil_ids(self):
        """
        When run is completed, generate final IDs for all approved coils
        that were waiting for run completion.
        """
        coils = frappe.get_all(
            "Mother Coil",
            filters={
                "casting_run": self.name,
                "qc_status": "Approved",
                "is_scrap": 0,
                "coil_id": ["is", "not set"]
            },
            fields=["name"]
        )
        
        for c in coils:
            doc = frappe.get_doc("Mother Coil", c.name)
            # This save will trigger on_update in Mother Coil,
            # which will now pass the 'run_status == Completed' check
            # and generate the ID.
            doc.save()
    
    def after_insert(self):
        # Update plan status when run is created
        self.sync_to_casting_plan()
    
    def update_totals_from_coils(self):
        """Update totals from linked Mother Coils (not child table)"""
        coils = frappe.get_all(
            "Mother Coil",
            filters={"casting_run": self.name},
            fields=["actual_weight_mt", "is_scrap", "scrap_weight_mt"]
        )
        
        total_weight = 0
        scrap_weight = 0
        
        for c in coils:
            weight = flt(c.actual_weight_mt or 0)
            total_weight += weight
            if c.is_scrap:
                scrap_weight += flt(c.scrap_weight_mt or c.actual_weight_mt or 0)
        
        self.total_coils = len(coils)
        self.total_cast_weight = flt(total_weight, 3)
        self.total_scrap_weight = flt(scrap_weight, 3)
    
    def sync_to_casting_plan(self):
        """Sync run status to linked PPC Casting Plan"""
        if not self.casting_plan:
            return
        
        try:
            plan = frappe.get_doc("PPC Casting Plan", self.casting_plan)
            
            # Don't update cancelled plans
            if plan.docstatus == 2:
                return
            
            updates = {}
            
            if self.status == "Casting":
                if plan.status in ["Metal Ready", "Melting", "Planned", "Released"]:
                    updates["status"] = "Casting"
                if self.run_start_time and not plan.casting_start:
                    updates["casting_start"] = self.run_start_time
            
            elif self.status == "Completed":
                # Check for approved coils
                approved_count = frappe.db.count("Mother Coil", {
                    "casting_run": self.name,
                    "qc_status": "Approved",
                    "is_scrap": 0
                })
                
                if approved_count > 0 or self.total_coils > 0:
                    updates["status"] = "Coils Complete"
                
                if self.run_end_time:
                    updates["casting_end"] = self.run_end_time
                    updates["actual_end"] = self.run_end_time
                
                # Update final weight
                if self.total_cast_weight:
                    updates["final_weight_mt"] = flt(self.total_cast_weight - self.total_scrap_weight, 3)
            
            elif self.status == "Aborted":
                updates["status"] = "Not Produced"
                if self.run_end_time:
                    updates["casting_end"] = self.run_end_time
            
            if updates:
                for field, value in updates.items():
                    plan.db_set(field, value, update_modified=True)
                    
        except Exception as e:
            frappe.log_error(
                title="Casting Run → Plan Sync Error",
                message=f"Error syncing run {self.name} to plan {self.casting_plan}: {str(e)}"
            )
    
    def validate_no_duplicate_active_run(self):
        """Ensure only one active casting run per caster"""
        if self.status == "Casting":
            existing = frappe.db.exists("Casting Run", {
                "caster": self.caster,
                "status": "Casting",
                "name": ("!=", self.name)
            })
            if existing:
                frappe.throw(_(
                    "There is already an active casting run ({0}) on caster {1}. "
                    "Please complete or abort that run first."
                ).format(existing, self.caster))
    
    def set_furnace_from_batch(self):
        """Set furnace from melting batch if not set"""
        if self.melting_batch and not self.furnace:
            self.furnace = frappe.db.get_value("Melting Batch", self.melting_batch, "furnace")
    
    def update_totals(self):
        """
        Update total coils and weights from child table.
        Legacy method - now also calls update_totals_from_coils for direct Mother Coil lookup.
        """
        total_coils = 0
        total_cast_weight = 0
        total_scrap_weight = 0
        
        for row in self.coils or []:
            total_coils += 1
            if row.mother_coil:
                coil_data = frappe.db.get_value("Mother Coil", row.mother_coil, 
                    ["actual_weight_mt", "is_scrap", "scrap_weight_mt"], as_dict=True)
                if coil_data:
                    if coil_data.is_scrap:
                        total_scrap_weight += flt(coil_data.scrap_weight_mt or coil_data.actual_weight_mt)
                    else:
                        total_cast_weight += flt(coil_data.actual_weight_mt)
        
        # If child table is empty, also check direct links
        if total_coils == 0:
            self.update_totals_from_coils()
        else:
            self.total_coils = total_coils
            self.total_cast_weight = flt(total_cast_weight, 3)
            self.total_scrap_weight = flt(total_scrap_weight, 3)
    
    def update_casting_plan_status(self):
        """
        Legacy method - now calls sync_to_casting_plan.
        """
        self.sync_to_casting_plan()
    
    def add_coil(self, mother_coil_name):
        """Add a mother coil to this run"""
        # Check if coil already exists in run
        existing = [c for c in self.coils if c.mother_coil == mother_coil_name]
        if existing:
            return existing[0]
        
        # Get next sequence
        next_seq = len(self.coils) + 1 if self.coils else 1
        
        # Add to child table
        row = self.append("coils", {
            "sequence": next_seq,
            "mother_coil": mother_coil_name
        })
        
        self.save()
        return row
    
    def start_casting(self):
        """Start the casting run"""
        if self.status != "Planned":
            frappe.throw(_("Cannot start casting - run is not in Planned status"))
        
        self.status = "Casting"
        self.run_start_time = frappe.utils.now_datetime()
        self.save()
        
        return self
    
    def complete_run(self):
        """Complete the casting run"""
        if self.status != "Casting":
            frappe.throw(_("Cannot complete - run is not in Casting status"))
        
        # Check for pending QC coils
        pending_coils = [c for c in self.coils if c.qc_status == "Pending"]
        if pending_coils:
            frappe.msgprint(_(
                "Warning: {0} coil(s) still have pending QC status"
            ).format(len(pending_coils)), indicator="orange")
        
        self.status = "Completed"
        self.run_end_time = frappe.utils.now_datetime()
        self.save()
        
        return self
    
    def abort_run(self, reason=None):
        """Abort the casting run"""
        self.status = "Aborted"
        self.run_end_time = frappe.utils.now_datetime()
        if reason:
            self.remarks = (self.remarks or "") + f"\nAborted: {reason}"
        self.save()
        
        return self





