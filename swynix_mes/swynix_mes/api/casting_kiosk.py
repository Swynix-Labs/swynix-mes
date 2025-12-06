# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

"""
Casting Kiosk API

Provides backend operations for the Casting Kiosk page:
- Get casters
- Get casting plans for caster/date
- Start/stop casting runs
- Create/finish coils
- Update coil dimensions
- Mark coil as scrap
- QC integration
"""

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, flt, nowdate
from swynix_mes.swynix_mes.utils.coil_logging import log_coil_event


# ==================== HELPERS ====================

def generate_final_coil_id(coil_doc):
    """
    Generate a final coil ID only after QC approval.
    
    Pattern: C<caster_code><YY><MM><DD><4-digit-seq>
    """
    caster_code = ""
    if coil_doc.caster:
        caster_code = "".join([c for c in coil_doc.caster if c.isalnum()])[:3].upper()
    dt = now_datetime()
    prefix = f"C{caster_code}{dt.strftime('%y%m%d')}"
    
    last = frappe.db.sql(
        """
        SELECT coil_id FROM `tabMother Coil`
        WHERE coil_id LIKE %s
        ORDER BY coil_id DESC
        LIMIT 1
        """,
        (prefix + "%",),
    )
    last_num = 0
    if last:
        try:
            last_num = int(last[0][0].replace(prefix, "") or 0)
        except Exception:
            last_num = 0
    
    return f"{prefix}{last_num + 1:04d}"


def sync_coil_qc_from_sample(sample_doc):
    """
    Copy QC status/comments/deviations from QC Sample to Mother Coil.
    """
    if not sample_doc.mother_coil:
        return
    
    coil = frappe.get_doc("Mother Coil", sample_doc.mother_coil)
    
    # Status
    coil.qc_status = sample_doc.status or sample_doc.overall_result or "Pending"
    coil.qc_comments = sample_doc.qc_comment or sample_doc.correction_note or sample_doc.remarks
    coil.qc_deviation_summary = sample_doc.deviation_messages
    coil.coil_qc_sample = sample_doc.name
    
    # Final coil id only on approve
    if sample_doc.status == "Approved" and not coil.is_scrap and not coil.coil_id:
        coil.coil_id = generate_final_coil_id(coil)
    
    # Scrap / recast handling on reject
    if sample_doc.status == "Rejected":
        coil.is_scrap = 1
        coil.scrap_reason = coil.scrap_reason or f"QC Rejected: {sample_doc.qc_comment or 'Out of Spec'}"
        coil.coil_id = None
    
    coil.save(ignore_permissions=True)


# ==================== CASTER & PLAN DATA ====================

@frappe.whitelist()
def get_casters():
    """
    Return list of casters (Workstations with workstation_type = 'Casting').
    
    This ensures caster selection in Casting Kiosk is consistent with
    PPC Caster Kiosk and PPC Casting Plan form, all filtering by
    Workstation type.
    """
    return frappe.get_all(
        "Workstation",
        filters={"workstation_type": "Casting"},
        fields=["name", "workstation_name"],
        order_by="name asc"
    )


@frappe.whitelist()
def get_casting_plans(caster, for_date=None):
    """
    Get casting plans for a caster (Workstation) on a given date.
    
    Args:
        caster: Workstation name (workstation_type = 'Casting')
        for_date: Date to filter (defaults to today)
        
    Returns:
        List of PPC Casting Plan records with relevant fields
    """
    if not caster:
        return []
    
    if not for_date:
        for_date = getdate()
    else:
        for_date = getdate(for_date)
    
    # Build date range for the day
    start_of_day = f"{for_date} 00:00:00"
    end_of_day = f"{for_date} 23:59:59"
    
    # Query plans - caster is directly the Workstation name
    plans = frappe.db.sql("""
        SELECT
            name,
            cast_no,
            plan_type,
            caster,
            furnace,
            start_datetime,
            end_datetime,
            duration_minutes,
            product_item,
            alloy,
            temper,
            planned_width_mm,
            planned_gauge_mm,
            planned_weight_mt,
            status,
            melting_batch,
            customer
        FROM `tabPPC Casting Plan`
        WHERE plan_type = 'Casting'
          AND caster = %(caster)s
          AND (
              (start_datetime BETWEEN %(start)s AND %(end)s)
              OR plan_date = %(date)s
          )
          AND docstatus < 2
        ORDER BY start_datetime ASC
    """, {
        "caster": caster,
        "start": start_of_day,
        "end": end_of_day,
        "date": for_date
    }, as_dict=True)
    
    return plans


# ==================== CASTING RUN OPERATIONS ====================

@frappe.whitelist()
def get_active_run(caster, for_date=None):
    """
    Get the active casting run for a caster on a given date.
    
    Returns:
        dict with:
        - run: Casting Run document
        - coils: List of Mother Coils
        - plan: Linked PPC Casting Plan
    """
    if not caster:
        return None
    
    if not for_date:
        for_date = getdate()
    else:
        for_date = getdate(for_date)
    
    # Find active run (status = Casting) or any run for today
    run = frappe.db.sql("""
        SELECT name, casting_plan, melting_batch, caster, furnace,
               status, run_start_time, run_end_time, run_date,
               planned_coils, total_coils, total_cast_weight, total_scrap_weight
        FROM `tabCasting Run`
        WHERE caster = %(caster)s
          AND run_date = %(date)s
          AND status IN ('Casting', 'Completed')
        ORDER BY 
            CASE WHEN status = 'Casting' THEN 0 ELSE 1 END,
            run_start_time DESC
        LIMIT 1
    """, {"caster": caster, "date": for_date}, as_dict=True)
    
    if not run:
        return None
    
    run = run[0]
    
    # Get coils for this run
    coils = get_coils_for_run(run.name)
    
    # Get plan details
    plan = {}
    if run.casting_plan:
        plan = frappe.db.get_value(
            "PPC Casting Plan", 
            run.casting_plan,
            ["name", "alloy", "product_item", "temper", "planned_width_mm", 
             "planned_gauge_mm", "planned_weight_mt"],
            as_dict=True
        ) or {}
    
    return {
        "run": run,
        "coils": coils,
        "plan": plan
    }


@frappe.whitelist()
def get_run_for_plan(plan_name):
    """
    Get the casting run for a specific plan.
    """
    if not plan_name:
        return None
    
    run = frappe.db.sql("""
        SELECT name, casting_plan, melting_batch, caster, furnace,
               status, run_start_time, run_end_time, run_date,
               planned_coils, total_coils, total_cast_weight, total_scrap_weight
        FROM `tabCasting Run`
        WHERE casting_plan = %(plan)s
        ORDER BY creation DESC
        LIMIT 1
    """, {"plan": plan_name}, as_dict=True)
    
    if not run:
        return None
    
    run = run[0]
    
    # Get coils
    coils = get_coils_for_run(run.name)
    
    # Get plan details
    plan = frappe.db.get_value(
        "PPC Casting Plan", 
        plan_name,
        ["name", "alloy", "product_item", "temper", "planned_width_mm", 
         "planned_gauge_mm", "planned_weight_mt"],
        as_dict=True
    ) or {}
    
    return {
        "run": run,
        "coils": coils,
        "plan": plan
    }


def get_coils_for_run(run_name):
    """
    Get all Mother Coils for a casting run.
    """
    coils = frappe.db.sql("""
        SELECT 
            name, temp_coil_id, coil_id, casting_run, casting_plan,
            melting_batch, caster, alloy, temper,
            cast_date, cast_start_time, cast_end_time,
            planned_width_mm, planned_gauge_mm, planned_weight_mt,
            actual_width_mm, actual_gauge_mm, actual_weight_mt,
            qc_status, qc_deviation_summary, qc_comments, coil_qc_sample,
            is_scrap, scrap_reason
        FROM `tabMother Coil`
        WHERE casting_run = %(run)s
        ORDER BY cast_start_time ASC, creation ASC
    """, {"run": run_name}, as_dict=True)
    
    return coils


@frappe.whitelist()
def start_casting(plan_name):
    """
    Start a casting run for a plan.
    
    Validates:
    - Plan exists and is in Metal Ready status
    - No other active casting run on this caster
    - Linked melting batch is Ready for Transfer
    
    Creates:
    - Casting Run document
    - Updates PPC Casting Plan status to Casting
    """
    if not plan_name:
        frappe.throw(_("Casting Plan is required."))
    
    plan = frappe.get_doc("PPC Casting Plan", plan_name)
    
    # Validate status
    if plan.status != "Metal Ready":
        frappe.throw(
            _("Cannot start casting. Plan status must be 'Metal Ready'. Current: {0}").format(plan.status)
        )
    
    # Get caster from plan
    caster = plan.caster
    if not caster:
        frappe.throw(_("Plan does not have a caster assigned."))
    
    # Check for existing active run on this caster
    existing_run = frappe.db.exists(
        "Casting Run",
        {"caster": caster, "status": "Casting"}
    )
    if existing_run:
        frappe.throw(
            _("Caster {0} already has an active casting run: {1}. Complete it first.").format(
                caster, existing_run
            )
        )
    
    # Get linked melting batch
    melting_batch = plan.melting_batch
    if melting_batch:
        batch_status = frappe.db.get_value("Melting Batch", melting_batch, "status")
        if batch_status not in ["Ready for Transfer", "Transferred"]:
            frappe.throw(
                _("Melting Batch {0} is not ready for transfer. Status: {1}").format(
                    melting_batch, batch_status
                )
            )
    
    # Get furnace from melting batch
    furnace = None
    if melting_batch:
        furnace = frappe.db.get_value("Melting Batch", melting_batch, "furnace")
    
    # Create Casting Run
    run = frappe.new_doc("Casting Run")
    run.casting_plan = plan_name
    run.melting_batch = melting_batch
    run.caster = caster
    run.furnace = furnace
    run.run_date = getdate()
    run.run_start_time = now_datetime()
    run.status = "Casting"
    run.insert()
    log_coil_event(
        coil=None,
        casting_run=run.name,
        event_type="CASTING_RUN_STARTED",
        reference_doctype="Casting Run",
        reference_name=run.name,
        details=f"Casting run started for plan {plan_name}"
    )
    
    # Update plan status
    frappe.db.set_value("PPC Casting Plan", plan_name, {
        "status": "Casting",
        "casting_start": now_datetime()
    })
    
    frappe.db.commit()
    
    return {
        "run_name": run.name,
        "plan_name": plan_name,
        "caster": caster
    }


@frappe.whitelist()
def stop_run(run_name):
    """
    Stop/complete a casting run.
    
    Updates:
    - Casting Run status to Completed
    - Run end time
    - Totals (cast weight, scrap weight)
    - PPC Casting Plan status to Coils Complete
    """
    if not run_name:
        frappe.throw(_("Casting Run is required."))
    
    run = frappe.get_doc("Casting Run", run_name)
    
    if run.status != "Casting":
        frappe.throw(
            _("Can only stop a run with status 'Casting'. Current: {0}").format(run.status)
        )
    
    # Calculate totals from coils
    coils = frappe.get_all(
        "Mother Coil",
        filters={"casting_run": run_name},
        fields=["actual_weight_mt", "is_scrap", "qc_status"]
    )
    
    total_weight = 0
    scrap_weight = 0
    approved_count = 0
    
    for c in coils:
        weight = flt(c.actual_weight_mt or 0)
        total_weight += weight
        if c.is_scrap:
            scrap_weight += weight
        if c.qc_status == "Approved":
            approved_count += 1
    
    # Update run
    run.status = "Completed"
    run.run_end_time = now_datetime()
    run.total_coils = len(coils)
    run.total_cast_weight = flt(total_weight, 3)
    run.total_scrap_weight = flt(scrap_weight, 3)
    run.save()
    log_coil_event(
        coil=None,
        casting_run=run.name,
        event_type="CASTING_RUN_STOPPED",
        reference_doctype="Casting Run",
        reference_name=run.name,
        details="Casting run stopped/completed"
    )
    
    # Update PPC Casting Plan status (tightened rule)
    if run.casting_plan:
        update_fields = {
            "casting_end": now_datetime()
        }

        plan = frappe.get_doc("PPC Casting Plan", run.casting_plan)
        planned_weight = flt(plan.planned_weight_mt or 0)

        # Fetch coils with needed fields
        coil_rows = frappe.get_all(
            "Mother Coil",
            filters={"casting_run": run_name},
            fields=["name", "qc_status", "coil_id", "is_scrap", "actual_weight_mt"]
        )

        no_pending = all(c.qc_status not in ["Pending", "Sample Taken"] for c in coil_rows)
        has_approved_final = any((c.qc_status == "Approved" and c.coil_id) for c in coil_rows)
        approved_scrap_weight = sum(flt(c.actual_weight_mt or 0) for c in coil_rows if c.qc_status in ["Approved"] or c.is_scrap)

        if no_pending and has_approved_final and (planned_weight == 0 or approved_scrap_weight >= planned_weight):
            update_fields["status"] = "Coils Complete"
        else:
            update_fields["status"] = "Casting"

        # Calculate final weight from coils
        final_weight = flt(total_weight - scrap_weight, 3)
        if final_weight > 0:
            update_fields["final_weight_mt"] = final_weight
        
        frappe.db.set_value("PPC Casting Plan", run.casting_plan, update_fields)
    
    frappe.db.commit()
    
    return {
        "status": run.status,
        "total_coils": len(coils),
        "total_cast_weight": total_weight,
        "approved_count": approved_count
    }


# ==================== COIL OPERATIONS ====================

@frappe.whitelist()
def create_coil(run_name):
    """
    Create a new Mother Coil for a casting run.
    
    Copies planned dimensions from the casting plan.
    Generates temp_coil_id automatically.
    Creates Coil QC record with Pending status.
    """
    if not run_name:
        frappe.throw(_("Casting Run is required."))
    
    run = frappe.get_doc("Casting Run", run_name)
    
    if run.status != "Casting":
        frappe.throw(
            _("Can only create coils for an active run. Status: {0}").format(run.status)
        )
    
    # Get plan details
    plan = None
    if run.casting_plan:
        plan = frappe.get_doc("PPC Casting Plan", run.casting_plan)
    
    # Create Mother Coil
    coil = frappe.new_doc("Mother Coil")
    coil.casting_run = run_name
    coil.casting_plan = run.casting_plan
    coil.melting_batch = run.melting_batch
    coil.caster = run.caster
    coil.furnace = run.furnace
    coil.cast_date = getdate()
    coil.cast_start_time = now_datetime()
    
    # Copy from plan
    if plan:
        coil.alloy = plan.alloy
        coil.product_item = plan.product_item
        coil.temper = plan.temper
        coil.planned_width_mm = plan.planned_width_mm
        coil.planned_gauge_mm = plan.planned_gauge_mm
        coil.planned_weight_mt = plan.planned_weight_mt
    
    coil.qc_status = "Pending"
    coil.insert()
    
    # Validate only one active coil per caster (no overlapping without end time)
    active_unfinished = frappe.get_all(
        "Mother Coil",
        filters={
            "caster": coil.caster,
            "casting_run": run_name,
            "cast_end_time": ["is", "not set"],
            "name": ["!=", coil.name],
            "is_scrap": 0
        },
        limit=1
    )
    if active_unfinished:
        frappe.throw(_("Another coil is still in Casting for this caster. Finish it before creating a new one."))
    log_coil_event(
        coil=coil.name,
        casting_run=run_name,
        event_type="COIL_STARTED",
        reference_doctype="Mother Coil",
        reference_name=coil.name,
        details=f"Temp ID {coil.temp_coil_id}"
    )
    
    # Add to run's coil table
    run.append("coils", {
        "sequence": len(run.coils) + 1,
        "mother_coil": coil.name
    })
    run.save()
    
    # Create Coil QC record
    create_coil_qc_record(coil.name, run_name)
    
    frappe.db.commit()
    
    return {
        "name": coil.name,
        "temp_coil_id": coil.temp_coil_id
    }


def create_coil_qc_record(coil_name, run_name=None):
    """
    Create a Coil QC record for a Mother Coil.
    """
    # Check if already exists
    existing = frappe.db.exists("Coil QC", {"mother_coil": coil_name})
    if existing:
        return existing
    
    qc = frappe.new_doc("Coil QC")
    qc.mother_coil = coil_name
    qc.casting_run = run_name
    qc.qc_date = getdate()
    qc.qc_status = "Pending"
    qc.insert()
    
    return qc.name


@frappe.whitelist()
def finish_coil(coil_name, actual_width_mm=None, actual_gauge_mm=None, actual_weight_mt=None):
    """
    Mark a coil as finished (set end time and actual dimensions).
    """
    if not coil_name:
        frappe.throw(_("Coil name is required."))
    
    coil = frappe.get_doc("Mother Coil", coil_name)
    
    coil.cast_end_time = now_datetime()
    
    if actual_width_mm is not None:
        coil.actual_width_mm = flt(actual_width_mm, 2)
    if actual_gauge_mm is not None:
        coil.actual_gauge_mm = flt(actual_gauge_mm, 3)
    if actual_weight_mt is not None:
        coil.actual_weight_mt = flt(actual_weight_mt, 3)
    
    coil.save()
    log_coil_event(
        coil=coil.name,
        casting_run=coil.casting_run,
        event_type="COIL_FINISHED",
        reference_doctype="Mother Coil",
        reference_name=coil.name,
        details="Coil finished with actual dimensions"
    )
    
    # Update Coil QC with measured dimensions
    coil_qc = frappe.db.get_value("Coil QC", {"mother_coil": coil_name}, "name")
    if coil_qc:
        frappe.db.set_value("Coil QC", coil_qc, {
            "width_mm_measured": coil.actual_width_mm,
            "gauge_mm_measured": coil.actual_gauge_mm,
            "coil_weight_mt_measured": coil.actual_weight_mt
        })
    
    # Update run totals
    if coil.casting_run:
        update_run_totals(coil.casting_run)
    
    frappe.db.commit()
    
    return {
        "name": coil.name,
        "cast_end_time": str(coil.cast_end_time)
    }


@frappe.whitelist()
def update_coil_dimensions(coil_name, actual_width_mm=None, actual_gauge_mm=None, actual_weight_mt=None):
    """
    Update actual dimensions of a coil.
    """
    if not coil_name:
        frappe.throw(_("Coil name is required."))
    
    coil = frappe.get_doc("Mother Coil", coil_name)
    
    if actual_width_mm is not None:
        coil.actual_width_mm = flt(actual_width_mm, 2)
    if actual_gauge_mm is not None:
        coil.actual_gauge_mm = flt(actual_gauge_mm, 3)
    if actual_weight_mt is not None:
        coil.actual_weight_mt = flt(actual_weight_mt, 3)
    
    coil.save()
    
    # Update Coil QC
    coil_qc = frappe.db.get_value("Coil QC", {"mother_coil": coil_name}, "name")
    if coil_qc:
        frappe.db.set_value("Coil QC", coil_qc, {
            "width_mm_measured": coil.actual_width_mm,
            "gauge_mm_measured": coil.actual_gauge_mm,
            "coil_weight_mt_measured": coil.actual_weight_mt
        })
    
    # Update run totals
    if coil.casting_run:
        update_run_totals(coil.casting_run)
    
    frappe.db.commit()
    
    return {"updated": True}


@frappe.whitelist()
def mark_coil_scrap(coil_name, scrap_reason=None, scrap_weight_mt=None):
    """
    Mark a coil as scrap.
    """
    if not coil_name:
        frappe.throw(_("Coil name is required."))
    
    coil = frappe.get_doc("Mother Coil", coil_name)
    
    coil.is_scrap = 1
    coil.scrap_reason = scrap_reason or "Marked as scrap from Casting Kiosk"
    coil.scrap_weight_mt = flt(scrap_weight_mt or coil.actual_weight_mt or coil.planned_weight_mt, 3)
    coil.qc_status = "Rejected"
    coil.coil_id = None  # Clear final coil ID
    
    coil.save()
    log_coil_event(
        coil=coil.name,
        casting_run=coil.casting_run,
        event_type="COIL_MARKED_SCRAP",
        reference_doctype="Mother Coil",
        reference_name=coil.name,
        remarks=coil.scrap_reason
    )
    
    # Update Coil QC
    coil_qc = frappe.db.get_value("Coil QC", {"mother_coil": coil_name}, "name")
    if coil_qc:
        frappe.db.set_value("Coil QC", coil_qc, {
            "qc_status": "Scrap",
            "qc_remarks": scrap_reason
        })
    
    # Update run totals
    if coil.casting_run:
        update_run_totals(coil.casting_run)
    
    frappe.db.commit()
    
    return {"marked": True}


def update_run_totals(run_name):
    """
    Update the totals on a Casting Run based on its coils.
    """
    if not run_name:
        return
    
    coils = frappe.get_all(
        "Mother Coil",
        filters={"casting_run": run_name},
        fields=["actual_weight_mt", "is_scrap"]
    )
    
    total_weight = sum(flt(c.actual_weight_mt or 0) for c in coils)
    scrap_weight = sum(flt(c.actual_weight_mt or 0) for c in coils if c.is_scrap)
    
    frappe.db.set_value("Casting Run", run_name, {
        "total_coils": len(coils),
        "total_cast_weight": flt(total_weight, 3),
        "total_scrap_weight": flt(scrap_weight, 3)
    })


# ==================== COIL DETAIL ====================

@frappe.whitelist()
def get_coil_detail(coil_name):
    """
    Get full details of a Mother Coil including chemistry status.
    """
    if not coil_name:
        return None
    
    coil = frappe.db.get_value(
        "Mother Coil",
        coil_name,
        ["*"],
        as_dict=True
    )
    
    if not coil:
        return None
    
    # Get chemistry status from melting batch
    chemistry_status = None
    if coil.melting_batch:
        batch_qc_status = frappe.db.get_value("Melting Batch", coil.melting_batch, "qc_status")
        if batch_qc_status == "OK":
            chemistry_status = "Within Spec"
        elif batch_qc_status == "Correction Required":
            chemistry_status = "Correction Required"
        elif batch_qc_status == "Rejected":
            chemistry_status = "Rejected"
        else:
            chemistry_status = "Pending"
    
    coil["chemistry_status"] = chemistry_status
    
    # Attach QC Sample info (unified QC)
    qc_sample = coil.get("coil_qc_sample") or frappe.db.get_value(
        "QC Sample",
        {"source_type": ["in", ["Coil", "Casting Coil"]], "mother_coil": coil_name, "docstatus": ["<", 2]},
        "name"
    )
    coil["coil_qc_sample"] = qc_sample
    if qc_sample:
        qs = frappe.get_doc("QC Sample", qc_sample)
        coil["qc_status"] = qs.status or qs.overall_result
        coil["qc_comments"] = qs.qc_comment or qs.correction_note or qs.remarks
        coil["qc_deviation_summary"] = qs.deviation_messages
        coil["qc_overall_result"] = qs.overall_result
        coil["qc_sample_time"] = qs.sample_time
    
    # Chemistry status aligns to coil qc_status when present
    coil["chemistry_status"] = coil.get("qc_status") or coil.get("chemistry_status") or "Pending"
    
    return coil


@frappe.whitelist()
def get_coil_process_log(coil):
    """
    Safe fetch of coil process log entries. Returns [] if DocType not present.
    """
    if not frappe.db.exists("DocType", "Coil Process Log"):
        return []
    return frappe.get_all(
        "Coil Process Log",
        filters={"coil": coil},
        fields=["timestamp", "event_type", "user", "details", "remarks", "reference_doctype", "reference_name"],
        order_by="timestamp asc"
    )


@frappe.whitelist()
def get_coil_process_logs(coil_name):
    # Backward-compatible alias
    return get_coil_process_log(coil_name)


@frappe.whitelist()
def get_coil_qc_history(coil_name):
    """
    Fetch QC samples history for a Mother Coil.
    Returns list of QC Sample records linked to this coil.
    """
    if not coil_name:
        return []
    
    samples = frappe.get_all(
        "QC Sample",
        filters={
            "mother_coil": coil_name,
            "source_type": "Casting"
        },
        fields=[
            "name",
            "sample_no",
            "sample_id",
            "sample_time",
            "status",
            "qc_decision",
            "overall_result",
            "deviation_messages",
            "remarks",
            "lab_technician",
            "qc_decision_time"
        ],
        order_by="sample_time desc"
    )
    
    # Build response with normalized fields
    result = []
    for s in samples:
        result.append({
            "name": s.name,
            "sample_no": s.sample_no or s.sample_id or s.name,
            "sample_time": s.sample_time,
            "status": s.status or s.qc_decision or s.overall_result or "Pending",
            "qc_decision": s.qc_decision or "Pending",
            "deviation_summary": s.deviation_messages or "",
            "remarks": s.remarks or "",
            "lab_technician": s.lab_technician or "",
            "qc_decision_time": s.qc_decision_time
        })
    
    return result


# Placeholder for future inventory integration
def create_coil_stock_entry_if_required(coil_doc):
    """
    Placeholder: integrate Stock Entry creation when ready.
    """
    # TODO: implement Stock Entry creation and warehouse movement
    return


@frappe.whitelist()
def get_or_create_coil_qc(coil_name):
    """
    Get or create a Coil QC record for a Mother Coil.
    """
    if not coil_name:
        frappe.throw(_("Coil name is required."))
    
    # Check if exists
    existing = frappe.db.get_value("Coil QC", {"mother_coil": coil_name}, "name")
    if existing:
        return {"name": existing}
    
    # Get coil details
    coil = frappe.get_doc("Mother Coil", coil_name)
    
    # Create new
    qc = frappe.new_doc("Coil QC")
    qc.mother_coil = coil_name
    qc.casting_run = coil.casting_run
    qc.qc_date = getdate()
    qc.qc_status = "Pending"
    qc.width_mm_measured = coil.actual_width_mm
    qc.gauge_mm_measured = coil.actual_gauge_mm
    qc.coil_weight_mt_measured = coil.actual_weight_mt
    qc.insert()
    
    frappe.db.commit()
    
    return {"name": qc.name}


@frappe.whitelist()
def get_or_create_coil_qc_sample(coil_name):
    """
    Get or create QC Sample for a Mother Coil and return its name.
    Uses the unified QC Sample DocType leveraged by QC Kiosk.
    """
    if not coil_name:
        frappe.throw(_("Coil name is required."))
    
    # Check existing QC Sample (include old and new source_type values)
    existing = frappe.db.get_value(
        "QC Sample",
        {"source_type": ["in", ["Casting", "Coil", "Casting Coil"]], "mother_coil": coil_name, "docstatus": ["<", 2]},
        "name"
    )
    if existing:
        return {"qc_sample": existing}
    
    coil = frappe.get_doc("Mother Coil", coil_name)
    
    # Determine next sample number for this coil
    existing_samples = frappe.get_all(
        "QC Sample",
        filters={
            "source_type": ["in", ["Casting", "Coil", "Casting Coil"]],
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
    
    qc_doc = frappe.new_doc("QC Sample")
    # Use standardized source_type value
    qc_doc.source_type = "Casting"
    qc_doc.source_doctype = "Mother Coil"
    qc_doc.source_document = coil.name
    qc_doc.source_name = coil.name
    qc_doc.mother_coil = coil.name
    qc_doc.coil = coil.name
    qc_doc.casting_run = coil.casting_run
    qc_doc.casting_plan = coil.casting_plan
    qc_doc.melting_batch = coil.melting_batch
    qc_doc.caster = coil.caster
    qc_doc.furnace = coil.furnace
    qc_doc.alloy = coil.alloy
    qc_doc.product_item = coil.product_item
    qc_doc.temper = coil.temper
    qc_doc.sample_time = now_datetime()
    qc_doc.sample_id = sample_no
    qc_doc.sample_no = sample_no
    qc_doc.sample_sequence_no = sample_seq
    qc_doc.status = "Pending"
    qc_doc.overall_result = "Pending"
    
    qc_doc.insert(ignore_permissions=True)
    frappe.db.commit()
    
    return {"qc_sample": qc_doc.name}


# ==================== STATUS SYNCHRONIZATION ====================

def sync_plan_status_from_melting(melting_batch_name, new_status):
    """
    Sync PPC Casting Plan status when Melting Batch status changes.
    Called from Melting Batch hooks.
    """
    if not melting_batch_name:
        return
    
    # Find linked plan
    plan_name = frappe.db.get_value(
        "PPC Casting Plan",
        {"melting_batch": melting_batch_name},
        "name"
    )
    
    if not plan_name:
        return
    
    plan = frappe.get_doc("PPC Casting Plan", plan_name)
    
    # Map melting status to plan status
    if new_status == "Charging":
        if plan.status == "Planned":
            plan.status = "Melting"
            plan.melting_start = now_datetime()
    elif new_status == "Ready for Transfer":
        if plan.status in ["Planned", "Melting"]:
            plan.status = "Metal Ready"
            plan.melting_end = now_datetime()
    elif new_status == "Transferred":
        if plan.status == "Metal Ready":
            # Status stays Metal Ready until casting starts
            pass
    
    plan.save()
    frappe.db.commit()


def sync_plan_status_from_casting(run_name, new_status):
    """
    Sync PPC Casting Plan status when Casting Run status changes.
    """
    if not run_name:
        return
    
    run = frappe.get_doc("Casting Run", run_name)
    
    if not run.casting_plan:
        return
    
    plan = frappe.get_doc("PPC Casting Plan", run.casting_plan)
    
    if new_status == "Casting":
        plan.status = "Casting"
        plan.casting_start = run.run_start_time or now_datetime()
    elif new_status == "Completed":
        plan.status = "Coils Complete"
        plan.casting_end = run.run_end_time or now_datetime()
    
    plan.save()
    frappe.db.commit()



