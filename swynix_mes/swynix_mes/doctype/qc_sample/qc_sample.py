# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

"""
QC Sample Document Controller

Handles:
- Multi-source QC samples (Melting Batch, Casting Run, Coil)
- Auto-populate context fields from source
- Element spec pre-population from ACCM
- QC evaluation and deviation tracking
- Final Coil generation on Casting Run approval
- Status synchronization with source documents
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime, nowdate, getdate, get_datetime
from swynix_mes.swynix_mes.api.casting_kiosk import generate_final_coil_id, sync_coil_qc_from_sample
from swynix_mes.swynix_mes.utils.coil_logging import log_coil_event
import json


class QCSample(Document):
    def validate(self):
        self.set_source_document()
        self.populate_context_from_source()
        self.generate_sample_id_if_needed()
        self.set_spec_master()
        self.populate_elements_from_spec()
        self.evaluate_qc()
    
    def on_submit(self):
        self.validate_qc_decision()
        self.apply_qc_decision()
    
    def set_source_document(self):
        """Set source_document, source_doctype, and source_name fields based on source_type and link field."""
        # Handle Melting source type
        if self.source_type == "Melting" and self.melting_batch:
            self.source_document = self.melting_batch
            self.source_document_link = self.melting_batch
            self.source_doctype = "Melting Batch"
            self.source_name = self.melting_batch
        # Handle Casting source type (from Mother Coil or Casting Run)
        elif self.source_type == "Casting":
            if self.mother_coil or self.coil:
                coil_name = self.mother_coil or self.coil
                self.source_document = coil_name
                self.source_document_link = coil_name
                self.source_doctype = "Mother Coil"
                self.source_name = coil_name
                # Also set mother_coil if using coil field
                if self.coil and not self.mother_coil:
                    self.mother_coil = self.coil
            elif self.casting_run:
                self.source_document = self.casting_run
                self.source_document_link = self.casting_run
                self.source_doctype = "Casting Run"
                self.source_name = self.casting_run
        # Legacy compatibility: handle old source_type values during migration
        elif self.source_type == "Melting Batch" and self.melting_batch:
            self.source_type = "Melting"  # Correct to new value
            self.source_document = self.melting_batch
            self.source_document_link = self.melting_batch
            self.source_doctype = "Melting Batch"
            self.source_name = self.melting_batch
        elif self.source_type in ("Coil", "Casting Coil", "Casting Run"):
            self.source_type = "Casting"  # Correct to new value
            if self.mother_coil or self.coil:
                coil_name = self.mother_coil or self.coil
                self.source_document = coil_name
                self.source_document_link = coil_name
                self.source_doctype = "Mother Coil"
                self.source_name = coil_name
                if self.coil and not self.mother_coil:
                    self.mother_coil = self.coil
            elif self.casting_run:
                self.source_document = self.casting_run
                self.source_document_link = self.casting_run
                self.source_doctype = "Casting Run"
                self.source_name = self.casting_run
    
    def populate_context_from_source(self):
        """Auto-populate alloy, furnace, caster, product, temper from source."""
        # Melting source - from Melting Batch
        if self.source_type == "Melting" and self.melting_batch:
            batch = frappe.get_doc("Melting Batch", self.melting_batch)
            self.alloy = self.alloy or batch.alloy
            self.furnace = self.furnace or batch.furnace
            self.product_item = self.product_item or batch.product_item
            self.temper = self.temper or batch.temper
            self.casting_plan = self.casting_plan or batch.ppc_casting_plan
            # Get caster from casting plan if available
            if batch.ppc_casting_plan and not self.caster:
                self.caster = frappe.db.get_value("PPC Casting Plan", batch.ppc_casting_plan, "caster")
        
        # Casting source - from Mother Coil (preferred) or Casting Run
        elif self.source_type == "Casting":
            # Prefer Mother Coil for context
            if self.mother_coil:
                coil = frappe.get_doc("Mother Coil", self.mother_coil)
                self.alloy = self.alloy or coil.alloy
                self.furnace = self.furnace or coil.furnace
                self.caster = self.caster or coil.caster
                self.product_item = self.product_item or coil.product_item
                self.temper = self.temper or coil.temper
                self.casting_plan = self.casting_plan or coil.casting_plan
                self.casting_run = self.casting_run or coil.casting_run
                self.melting_batch = self.melting_batch or coil.melting_batch
            elif self.casting_run:
                run = frappe.get_doc("Casting Run", self.casting_run)
                # Get melting batch for alloy/furnace
                if run.melting_batch:
                    self.melting_batch = run.melting_batch
                    batch = frappe.get_doc("Melting Batch", run.melting_batch)
                    self.alloy = self.alloy or batch.alloy
                    self.furnace = self.furnace or batch.furnace
                    self.product_item = self.product_item or batch.product_item
                    self.temper = self.temper or batch.temper
                # Get caster from casting plan
                if run.casting_plan:
                    self.casting_plan = run.casting_plan
                    self.caster = self.caster or frappe.db.get_value("PPC Casting Plan", run.casting_plan, "caster")
    
    def generate_sample_id_if_needed(self):
        """Generate sample_id and sample_no like S1, S2, S3 based on source."""
        if self.sample_id:
            # Ensure sample_no is set if sample_id exists
            if not self.sample_no:
                self.sample_no = self.sample_id
            return
        
        # Count existing samples for this source
        existing_count = frappe.db.count("QC Sample", {
            "source_type": self.source_type,
            "source_document": self.source_document,
            "name": ["!=", self.name or ""]
        })
        
        self.sample_sequence_no = existing_count + 1
        self.sample_id = f"S{self.sample_sequence_no}"
        self.sample_no = self.sample_id  # Also set sample_no
    
    def set_spec_master(self):
        """Set composition master from alloy if not already set."""
        if self.spec_master or not self.alloy:
            return
        
        # Find active ACCM for this alloy
        accm = frappe.db.get_value(
            "Alloy Chemical Composition Master",
            {"alloy": self.alloy, "is_active": 1},
            "name",
            order_by="revision_date desc, revision_no desc"
        )
        
        if accm:
            self.spec_master = accm
    
    def populate_elements_from_spec(self):
        """Pre-populate element rows from ACCM if not already populated."""
        if not self.spec_master:
            return
        
        # Only populate if elements table is empty
        if self.elements and len(self.elements) > 0:
            return
        
        accm = frappe.get_doc("Alloy Chemical Composition Master", self.spec_master)
        
        for rule in accm.composition_rules or []:
            condition_type = rule.condition_type
            
            # Skip Free Text rules
            if condition_type == "Free Text":
                continue
            
            element_1 = rule.element_1
            if not element_1:
                continue
            
            element_code = get_element_code(element_1)
            
            el_row = self.append("elements", {})
            el_row.element = element_1
            el_row.element_code = element_code
            el_row.condition_type = condition_type
            el_row.in_spec = 1  # Default
            
            if condition_type == "Normal Limit":
                el_row.limit_type = rule.limit_type
                el_row.spec_min_pct = rule.min_percentage
                el_row.spec_max_pct = rule.max_percentage
                # Target as midpoint
                if rule.min_percentage is not None and rule.max_percentage is not None:
                    el_row.spec_target_pct = (flt(rule.min_percentage) + flt(rule.max_percentage)) / 2
                    
            elif condition_type == "Sum Limit":
                el_row.limit_type = rule.sum_limit_type
                if rule.sum_limit_type == "Maximum":
                    el_row.sum_limit_pct = rule.sum_max_percentage
                else:
                    el_row.sum_limit_pct = rule.sum_min_percentage
                    
            elif condition_type == "Ratio":
                if rule.ratio_value_1 and rule.ratio_value_2:
                    el_row.ratio_value = flt(rule.ratio_value_1) / flt(rule.ratio_value_2) if rule.ratio_value_2 else 0
                    
            elif condition_type == "Remainder":
                el_row.limit_type = "Minimum"
                el_row.spec_min_pct = rule.remainder_min_percentage
    
    def evaluate_qc(self):
        """Evaluate sample readings against spec and update deviations."""
        if not self.elements:
            return
        
        deviation_msgs = []
        out_of_spec_count = 0
        has_readings = False
        
        # Build value dict for sum/ratio checks
        val = {}
        for el in self.elements:
            if el.sample_pct is not None:
                has_readings = True
                code = el.element_code or get_element_code(el.element)
                if code:
                    val[code] = flt(el.sample_pct)
        
        if not has_readings:
            self.overall_result = "Pending"
            return
        
        # Evaluate each element
        for el in self.elements:
            el.in_spec = 1
            el.violation_message = ""
            el.deviation_pct = None
            
            if el.sample_pct is None:
                continue
            
            sample_pct = flt(el.sample_pct)
            code = el.element_code or get_element_code(el.element)
            condition_type = el.condition_type or "Normal Limit"
            limit_type = el.limit_type or ""
            
            # Calculate deviation from target
            if el.spec_target_pct is not None:
                el.deviation_pct = flt(sample_pct - flt(el.spec_target_pct), 4)
            
            if condition_type == "Normal Limit":
                is_ok, msg = check_normal_limit(code, sample_pct, el.spec_min_pct, el.spec_max_pct, limit_type)
                if not is_ok:
                    el.in_spec = 0
                    el.violation_message = msg
                    deviation_msgs.append(msg)
                    out_of_spec_count += 1
                    
            elif condition_type == "Sum Limit":
                # Get sum elements from ACCM rule if needed
                is_ok, msg = check_sum_limit(el, val, self.spec_master)
                if not is_ok:
                    el.in_spec = 0
                    el.violation_message = msg
                    deviation_msgs.append(msg)
                    out_of_spec_count += 1
                    
            elif condition_type == "Ratio":
                is_ok, msg = check_ratio(el, val, self.spec_master)
                if not is_ok:
                    el.in_spec = 0
                    el.violation_message = msg
                    deviation_msgs.append(msg)
                    out_of_spec_count += 1
                    
            elif condition_type == "Remainder":
                is_ok, msg = check_remainder(code, sample_pct, el.spec_min_pct)
                if not is_ok:
                    el.in_spec = 0
                    el.violation_message = msg
                    deviation_msgs.append(msg)
                    out_of_spec_count += 1
        
        # Update deviation fields
        self.deviation_messages = "\n".join(deviation_msgs)
        self.deviation_count = out_of_spec_count
        
        # Update overall result
        if out_of_spec_count > 0:
            self.overall_result = "Out of Spec"
        else:
            self.overall_result = "In Spec"
    
    def validate_qc_decision(self):
        """Ensure QC decision is made before submit."""
        if not self.qc_action:
            frappe.throw(_("QC Action is required before submitting. Please Approve, Reject, or Request Correction."))
        
        if self.qc_action == "Request Correction" and not self.correction_note:
            frappe.throw(_("Correction Note is required when requesting correction."))
    
    def apply_qc_decision(self):
        """Apply QC decision to source documents and generate final coils if needed."""
        self.qc_decision_time = now_datetime()
        self.lab_technician = self.lab_technician or frappe.session.user
        
        if self.qc_action == "Approve":
            self.status = "Approved"
            self.handle_approval()
        elif self.qc_action == "Reject":
            self.status = "Rejected"
            self.handle_rejection()
        elif self.qc_action == "Request Correction":
            self.status = "Correction Required"
            self.correction_required = 1
            self.handle_correction_request()
    
    def handle_approval(self):
        """Handle QC approval - sync to source and generate final coils for Casting Run."""
        if self.source_type == "Melting" and self.melting_batch:
            # Update melting batch QC status
            frappe.db.set_value("Melting Batch", self.melting_batch, {
                "qc_status": "OK",
                "lab_signed_by": frappe.session.user
            })
            
        elif self.source_type == "Casting" and self.casting_run and not self.mother_coil:
            # Casting Run level sample (rare case)
            frappe.db.set_value("Casting Run", self.casting_run, "qc_status", "Approved")
            self.generate_final_coils_for_run()
            
        elif self.source_type == "Casting" and self.mother_coil:
            coil = frappe.get_doc("Mother Coil", self.mother_coil)
            coil.qc_status = "Approved"
            coil.coil_status = "Approved"
            coil.chem_status = "Within Spec"
            coil.coil_qc_sample = self.name
            coil.qc_comments = self.qc_comment or ""
            coil.qc_deviation_summary = self.deviation_messages
            coil.qc_last_sample = self.name
            coil.qc_last_comment = self.qc_comment or ""
            coil.ready_for_stock_entry = 1
            if not coil.coil_id and not coil.is_scrap:
                coil.coil_id = generate_final_coil_id(coil)
                coil.flags.skip_final_id_log = True
                log_coil_event(
                    coil=coil.name,
                    casting_run=coil.casting_run,
                    event_type="FINAL_COIL_ID_ASSIGNED",
                    reference_doctype="Mother Coil",
                    reference_name=coil.name,
                    details=f"{coil.temp_coil_id} → {coil.coil_id}"
                )
            coil.flags.qc_approved = True
            coil.save(ignore_permissions=True)
            log_coil_event(
                coil=coil.name,
                casting_run=coil.casting_run,
                event_type="QC_RESULT_RECEIVED",
                reference_doctype="QC Sample",
                reference_name=self.name,
                details=f"Approved - {self.qc_comment or 'Within Spec'}"
            )
    
    def handle_rejection(self):
        """Handle QC rejection - mark coils as scrap/recast."""
        if self.source_type == "Melting" and self.melting_batch:
            frappe.db.set_value("Melting Batch", self.melting_batch, "qc_status", "Rejected")
            
        elif self.source_type == "Casting" and self.casting_run and not self.mother_coil:
            # Casting Run level rejection (rare case)
            frappe.db.set_value("Casting Run", self.casting_run, "qc_status", "Rejected")
            
            # Mark all temp coils as scrap
            coils = frappe.get_all("Mother Coil", {
                "casting_run": self.casting_run,
                "is_scrap": 0,
                "coil_id": ["is", "not set"]
            })
            
            scrap_ids = []
            for c in coils:
                frappe.db.set_value("Mother Coil", c.name, {
                    "is_scrap": 1,
                    "scrap_reason": f"QC Rejected: {self.qc_comment or 'Sample rejected'}",
                    "qc_status": "Rejected",
                    "qc_sample": self.name
                })
                coil_doc = frappe.get_doc("Mother Coil", c.name)
                scrap_ids.append(coil_doc.temp_coil_id or c.name)
            
            if scrap_ids:
                self.coils_affected = ", ".join(scrap_ids)
                
        elif self.source_type == "Casting" and self.mother_coil:
            frappe.db.set_value("Mother Coil", self.mother_coil, {
                "is_scrap": 1,
                "scrap_reason": f"QC Rejected: {self.qc_comment or 'Sample rejected'}",
                "qc_status": "Rejected",
                "coil_status": "Rejected",
                "chem_status": "Out of Spec",
                "qc_sample": self.name
            })
            coil = frappe.get_doc("Mother Coil", self.mother_coil)
            coil.coil_qc_sample = self.name
            coil.qc_deviation_summary = self.deviation_messages
            coil.qc_comments = self.qc_comment
            coil.qc_last_sample = self.name
            coil.qc_last_comment = self.qc_comment
            coil.save(ignore_permissions=True)
            log_coil_event(
                coil=coil.name,
                casting_run=coil.casting_run,
                event_type="QC_RESULT_RECEIVED",
                reference_doctype="QC Sample",
                reference_name=self.name,
                details=f"Rejected - {self.qc_comment or 'Out of Spec'}"
            )
            log_coil_event(
                coil=coil.name,
                casting_run=coil.casting_run,
                event_type="COIL_MARKED_SCRAP",
                reference_doctype="Mother Coil",
                reference_name=coil.name,
                remarks=coil.scrap_reason
            )
    
    def handle_correction_request(self):
        """Handle correction request - update source with deviation info."""
        if self.source_type == "Melting" and self.melting_batch:
            frappe.db.set_value("Melting Batch", self.melting_batch, {
                "qc_status": "Correction Required"
            })
            # Add process log
            batch = frappe.get_doc("Melting Batch", self.melting_batch)
            plog = batch.append("process_logs", {})
            plog.log_time = now_datetime()
            plog.event_type = "Correction"
            plog.sample_id = self.sample_id
            plog.note = f"QC Correction Required: {self.correction_note}"
            batch.save()
            
        elif self.source_type == "Casting" and self.casting_run and not self.mother_coil:
            # Casting Run level correction (rare case)
            frappe.db.set_value("Casting Run", self.casting_run, "qc_status", "Correction Required")
            
            # Update all temp coils with correction status
            coils = frappe.get_all("Mother Coil", {
                "casting_run": self.casting_run,
                "is_scrap": 0
            })
            
            affected_ids = []
            for c in coils:
                frappe.db.set_value("Mother Coil", c.name, {
                    "qc_status": "Correction Required",
                    "qc_comments": self.correction_note,
                    "qc_deviation_summary": self.deviation_messages,
                    "qc_sample": self.name
                })
                coil_doc = frappe.get_doc("Mother Coil", c.name)
                affected_ids.append(coil_doc.temp_coil_id or c.name)
            
            if affected_ids:
                self.coils_affected = ", ".join(affected_ids)
                
        elif self.source_type == "Casting" and self.mother_coil:
            frappe.db.set_value("Mother Coil", self.mother_coil, {
                "qc_status": "Correction Required",
                "coil_status": "Correction Required",
                "chem_status": "Correction Required",
                "qc_comments": self.correction_note,
                "qc_deviation_summary": self.deviation_messages,
                "qc_sample": self.name
            })
            coil = frappe.get_doc("Mother Coil", self.mother_coil)
            coil.coil_qc_sample = self.name
            coil.qc_last_sample = self.name
            coil.qc_last_comment = self.correction_note
            coil.save(ignore_permissions=True)
            log_coil_event(
                coil=coil.name,
                casting_run=coil.casting_run,
                event_type="QC_RESULT_RECEIVED",
                reference_doctype="QC Sample",
                reference_name=self.name,
                details=f"Correction Required - {self.correction_note or ''}"
            )
    
    def generate_final_coils_for_run(self):
        """Generate final coil IDs for all approved temp coils in the casting run."""
        if not self.casting_run:
            return
        
        # Get all temp coils without final IDs that are not scrap
        coils = frappe.get_all("Mother Coil", {
            "casting_run": self.casting_run,
            "is_scrap": 0,
            "coil_id": ["is", "not set"]
        }, ["name", "temp_coil_id"])
        
        if not coils:
            return
        
        generated_ids = []
        for c in coils:
            coil_doc = frappe.get_doc("Mother Coil", c.name)
            coil_doc.qc_status = "Approved"
            coil_doc.qc_sample = self.name
            coil_doc.flags.qc_approved = True
            coil_doc.save()
            
            if coil_doc.coil_id:
                generated_ids.append(coil_doc.coil_id)
            else:
                generated_ids.append(c.temp_coil_id or c.name)
        
        self.coils_affected = ", ".join(generated_ids)
        self.final_coil_generated = 1


# ==================== HELPER FUNCTIONS ====================

def get_element_code(item_name):
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
        "chromium": "Cr", "cr": "Cr",
        "nickel": "Ni", "ni": "Ni",
        "lead": "Pb", "pb": "Pb",
        "tin": "Sn", "sn": "Sn",
        "vanadium": "V", "v": "V",
        "boron": "B", "b": "B",
        "calcium": "Ca", "ca": "Ca",
        "sodium": "Na", "na": "Na",
        "phosphorus": "P", "p": "P",
        "sulfur": "S", "s": "S",
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


def check_normal_limit(element_code, sample_pct, spec_min, spec_max, limit_type):
    """Check normal limit and return (is_ok, message)."""
    is_ok = True
    msg = ""
    
    if limit_type == "Maximum":
        if spec_max is not None and sample_pct > flt(spec_max):
            is_ok = False
            msg = f"{element_code} {sample_pct:.4f}% > {spec_max:.4f}% (Max)"
    elif limit_type == "Minimum":
        if spec_min is not None and sample_pct < flt(spec_min):
            is_ok = False
            msg = f"{element_code} {sample_pct:.4f}% < {spec_min:.4f}% (Min)"
    elif limit_type == "Equal To":
        target = spec_min or spec_max
        if target is not None and abs(sample_pct - flt(target)) > 0.01:
            is_ok = False
            msg = f"{element_code} {sample_pct:.4f}% ≠ {target:.4f}%"
    else:  # Range
        if spec_min is not None and sample_pct < flt(spec_min):
            is_ok = False
            msg = f"{element_code} {sample_pct:.4f}% < {spec_min:.4f}% (Min)"
        elif spec_max is not None and sample_pct > flt(spec_max):
            is_ok = False
            msg = f"{element_code} {sample_pct:.4f}% > {spec_max:.4f}% (Max)"
    
    return is_ok, msg


def check_sum_limit(el, val, spec_master):
    """Check sum limit rule and return (is_ok, message)."""
    # TODO: Need to get participating elements from ACCM rule
    # For now, common sum is Fe+Si
    code = el.element_code
    
    if code == "Fe" and "Si" in val:
        sum_val = flt(val.get("Fe", 0)) + flt(val.get("Si", 0))
        sum_limit = el.sum_limit_pct
        
        if sum_limit and sum_val > flt(sum_limit):
            return False, f"Fe+Si = {sum_val:.4f}% > {sum_limit:.4f}% (Sum Limit)"
    
    return True, ""


def check_ratio(el, val, spec_master):
    """Check ratio rule and return (is_ok, message)."""
    # TODO: Get ratio elements from ACCM rule
    # Common ratio is Fe/Si
    code = el.element_code
    
    if code == "Fe" and "Si" in val and val.get("Si", 0) > 0:
        ratio = flt(val.get("Fe", 0)) / flt(val.get("Si"))
        expected = el.ratio_value
        
        if expected and expected > 0:
            tolerance = 0.1  # 10% tolerance
            if abs(ratio - expected) / expected > tolerance:
                return False, f"Fe/Si = {ratio:.2f} (expected ~{expected:.2f})"
    
    return True, ""


def check_remainder(element_code, sample_pct, spec_min):
    """Check remainder (Al) minimum and return (is_ok, message)."""
    if spec_min is not None and sample_pct < flt(spec_min):
        return False, f"{element_code} {sample_pct:.4f}% < {spec_min:.4f}% (Remainder Min)"
    return True, ""


# ==================== API FUNCTIONS ====================

@frappe.whitelist()
def create_qc_sample(source_type, source_document, sample_id=None):
    """
    Create a new QC Sample for a source document.
    
    Args:
        source_type: "Melting" or "Casting"
        source_document: Name of the source document (Melting Batch, Mother Coil, or Casting Run)
        sample_id: Optional custom sample ID (auto-generated if not provided)
        
    Returns:
        dict with new sample info
    """
    doc = frappe.new_doc("QC Sample")
    doc.sample_time = now_datetime()
    
    # Normalize legacy source_type values
    if source_type in ("Melting Batch", "Melting"):
        doc.source_type = "Melting"
        doc.melting_batch = source_document
    elif source_type in ("Casting Run", "Coil", "Casting Coil", "Mother Coil", "Casting"):
        doc.source_type = "Casting"
        # Determine which field to set based on doctype
        if frappe.db.exists("Mother Coil", source_document):
            doc.mother_coil = source_document
        elif frappe.db.exists("Casting Run", source_document):
            doc.casting_run = source_document
        else:
            doc.mother_coil = source_document  # Default to mother_coil
    else:
        doc.source_type = source_type
    
    if sample_id:
        doc.sample_id = sample_id
    
    doc.insert()
    
    return {
        "name": doc.name,
        "sample_id": doc.sample_id,
        "source_type": doc.source_type,
        "source_document": doc.source_document,
        "alloy": doc.alloy,
        "spec_master": doc.spec_master,
        "elements_count": len(doc.elements or [])
    }


@frappe.whitelist()
def get_sample_history_for_source(source_type, source_document):
    """
    Get QC sample history for a source document.
    
    Returns list of samples with their status and key info.
    """
    return frappe.get_all(
        "QC Sample",
        filters={
            "source_type": source_type,
            "source_document": source_document
        },
        fields=[
            "name", "sample_id", "sample_time", "status", 
            "overall_result", "deviation_count", "qc_action"
        ],
        order_by="sample_time desc"
    )


