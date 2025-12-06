# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe


def get_context(context):
    """Set page context for Casting Kiosk."""
    context.no_cache = 1


@frappe.whitelist()
def take_casting_sample(coil_name):
    """
    Create a QC Sample for a casting coil if none is pending.
    Uses source_type="Casting" for unified QC Kiosk.
    """
    if not coil_name:
        frappe.throw("Coil name is required.")
    
    coil = frappe.get_doc("Mother Coil", coil_name)
    
    # Check for pending or correction-required QC sample for this coil
    # Include both old and new source_type values for backward compatibility
    exists = frappe.db.exists(
        "QC Sample",
        {
            "source_type": ["in", ["Casting", "Casting Coil", "Coil"]],
            "mother_coil": coil_name,
            "status": ["in", ["Pending", "Correction Required"]],
        },
    )
    if exists:
        frappe.throw("QC sample already pending")
    
    # Determine next sample number for this coil
    existing_samples = frappe.get_all(
        "QC Sample",
        filters={
            "source_type": ["in", ["Casting", "Casting Coil", "Coil"]],
            "mother_coil": coil.name
        },
        fields=["sample_no", "sample_sequence_no"],
        order_by="sample_sequence_no desc",
        limit=1
    )
    
    sample_seq = 1
    if existing_samples and existing_samples[0].sample_sequence_no:
        sample_seq = existing_samples[0].sample_sequence_no + 1
    sample_no = f"S{sample_seq}"
    
    qc = frappe.new_doc("QC Sample")
    # Use the correct source_type value for unified QC
    qc.source_type = "Casting"
    qc.source_doctype = "Mother Coil"
    qc.source_document = coil.name
    qc.source_name = coil.name
    qc.mother_coil = coil.name
    qc.coil = coil.name  # Also set coil field
    qc.casting_run = coil.casting_run
    qc.melting_batch = coil.melting_batch
    qc.caster = coil.caster
    qc.furnace = coil.furnace
    qc.alloy = coil.alloy
    qc.product_item = coil.product_item
    qc.temper = coil.temper
    qc.casting_plan = coil.casting_plan
    qc.sample_time = frappe.utils.now_datetime()
    qc.sample_id = sample_no
    qc.sample_no = sample_no
    qc.sample_sequence_no = sample_seq
    qc.status = "Pending"
    qc.overall_result = "Pending"
    
    # Pre-create element rows with zero readings
    # Note: element field is a Link to Item, so we need to find actual Item names
    # For now, we skip element rows and let QC Kiosk populate them from spec
    # The composition_check logic will add proper element rows when readings are entered
    
    qc.insert(ignore_permissions=True)
    
    # Update coil flags - qc_status stays "Pending" (valid enum value)
    # Do NOT set qc_status = "Sample Taken" as it's not a valid option
    coil.coil_status = "QC Pending"
    coil.qc_last_sample = qc.name
    coil.qc_last_comment = qc.qc_comment or ""
    coil.coil_qc_sample = qc.name
    coil.save(ignore_permissions=True)
    
    frappe.db.commit()
    
    # Log process event
    from swynix_mes.swynix_mes.utils.coil_logging import log_coil_event
    log_coil_event(
        coil=coil.name,
        casting_run=coil.casting_run,
        event_type="SAMPLE_TAKEN",
        reference_doctype="QC Sample",
        reference_name=qc.name,
        details=f"QC Sample {qc.name} created for coil {coil.temp_coil_id}"
    )
    
    return {"qc_sample": qc.name}



