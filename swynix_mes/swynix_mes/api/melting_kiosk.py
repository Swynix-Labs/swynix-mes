# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, get_datetime, flt
from datetime import timedelta


@frappe.whitelist()
def get_furnaces():
    """Return list of furnaces (Workstations with workstation_type = 'Foundry')."""
    return frappe.get_all(
        "Workstation",
        filters={"workstation_type": "Foundry"},
        fields=["name", "workstation_name"],
        order_by="workstation_name asc"
    )


@frappe.whitelist()
def get_batches_for_furnace(furnace, for_date=None):
    """
    Return melting batches for a furnace on a given date (default today).
    """
    if not furnace:
        return []

    if not for_date:
        for_date = getdate()

    batches = frappe.get_all(
        "Melting Batch",
        filters={
            "furnace": furnace,
            "plan_date": for_date,
            "docstatus": ["<", 2]  # Exclude cancelled
        },
        fields=[
            "name",
            "melting_batch_id",
            "status",
            "alloy",
            "product_item",
            "planned_weight_mt",
            "charged_weight_mt",
            "tapped_weight_mt",
            "yield_percent",
            "batch_start_datetime",
            "batch_end_datetime"
        ],
        order_by="batch_start_datetime asc, creation asc"
    )

    return batches


@frappe.whitelist()
def create_melting_batch(data):
    """
    Create a new Melting Batch from kiosk dialog.
    
    data:
      - furnace (required)
      - alloy
      - product_item
      - charge_mix_recipe
      - planned_weight_mt
      - ppc_casting_plan
    """
    import json
    if isinstance(data, str):
        data = json.loads(data)
    
    data = frappe._dict(data or {})

    if not data.get("furnace"):
        frappe.throw(_("Furnace is required."))

    doc = frappe.new_doc("Melting Batch")
    doc.furnace = data.furnace
    doc.alloy = data.get("alloy")
    doc.product_item = data.get("product_item")
    doc.charge_mix_recipe = data.get("charge_mix_recipe")
    doc.planned_weight_mt = flt(data.get("planned_weight_mt"))
    doc.plan_date = getdate()
    doc.status = "Charging"
    doc.batch_start_datetime = now_datetime()

    if data.get("ppc_casting_plan"):
        doc.ppc_casting_plan = data.ppc_casting_plan

    doc.insert()
    frappe.db.commit()

    return doc.name


@frappe.whitelist()
def add_raw_material_row(batch_name, item_code, qty_kg, ingredient_type=None,
                         batch_no=None, source_bin=None, bucket_no=None, is_correction=0):
    """
    Append a raw material row (normal or correction) to Melting Batch.
    """
    if not batch_name:
        frappe.throw(_("Melting Batch is required."))

    doc = frappe.get_doc("Melting Batch", batch_name)

    # Auto-assign row_index
    row_index = len(doc.raw_materials) + 1

    row = doc.append("raw_materials", {})
    row.row_index = row_index
    row.item_code = item_code
    row.qty_kg = flt(qty_kg or 0, 3)
    row.ingredient_type = ingredient_type
    row.batch_no = batch_no
    row.source_bin = source_bin
    row.bucket_no = bucket_no
    row.is_correction = int(is_correction or 0)

    # Auto-fetch item_name
    if item_code:
        item = frappe.db.get_value("Item", item_code, ["item_name"], as_dict=True)
        if item:
            row.item_name = item.item_name

    # Recalculate charged_weight_mt and yield%
    total_kg = sum([flt(r.qty_kg) for r in doc.raw_materials])
    doc.charged_weight_mt = flt(total_kg / 1000.0, 3)

    if doc.tapped_weight_mt and doc.charged_weight_mt:
        doc.yield_percent = flt((doc.tapped_weight_mt / doc.charged_weight_mt) * 100, 2)

    doc.save()
    frappe.db.commit()

    return {
        "row_name": row.name,
        "charged_weight_mt": doc.charged_weight_mt,
        "yield_percent": doc.yield_percent
    }


@frappe.whitelist()
def log_process_event(batch_name, event_type, temp_c=None, pressure_bar=None,
                      flux_type=None, flux_qty_kg=None, sample_id=None, note=None):
    """
    Append a process log row for events:
    - Burner On
    - Fluxing
    - Sample Taken
    - Correction
    - Holding
    - Transfer
    - Other
    """
    if not batch_name:
        frappe.throw(_("Melting Batch is required."))

    if not event_type:
        frappe.throw(_("Event Type is required."))

    doc = frappe.get_doc("Melting Batch", batch_name)

    row = doc.append("process_logs", {})
    row.log_time = now_datetime()
    row.event_type = event_type
    row.temp_c = flt(temp_c) if temp_c else None
    row.pressure_bar = flt(pressure_bar) if pressure_bar else None
    row.flux_type = flux_type
    row.flux_qty_kg = flt(flux_qty_kg) if flux_qty_kg else None
    row.sample_id = sample_id
    row.note = note

    # Set batch_start on first Burner On
    if event_type == "Burner On" and not doc.batch_start_datetime:
        doc.batch_start_datetime = row.log_time

    doc.save()
    frappe.db.commit()

    return {
        "name": row.name,
        "log_time": str(row.log_time)
    }


@frappe.whitelist()
def create_sample(batch_name):
    """
    Create next spectro sample (S1, S2,...) and log Sample Taken event.
    """
    if not batch_name:
        frappe.throw(_("Melting Batch is required."))

    doc = frappe.get_doc("Melting Batch", batch_name)

    # Determine next sample ID
    existing_ids = [s.sample_id for s in doc.spectro_samples if s.sample_id]
    idx = len(existing_ids) + 1
    sample_id = f"S{idx}"

    # Add spectro sample row
    srow = doc.append("spectro_samples", {})
    srow.sample_id = sample_id
    srow.sample_time = now_datetime()
    srow.result_status = "Pending"

    # Log process event
    prow = doc.append("process_logs", {})
    prow.log_time = srow.sample_time
    prow.event_type = "Sample Taken"
    prow.sample_id = sample_id

    doc.save()
    frappe.db.commit()

    return {"sample_id": sample_id}


@frappe.whitelist()
def mark_ready_for_transfer(batch_name):
    """
    Lab / Supervisor marks batch Ready for Transfer after chemistry OK.
    """
    if not batch_name:
        frappe.throw(_("Melting Batch is required."))

    doc = frappe.get_doc("Melting Batch", batch_name)

    if doc.status not in ["Melting", "Charging"]:
        frappe.throw(_("Batch must be in Melting or Charging status to mark ready for transfer. Current: {0}").format(doc.status))

    doc.status = "Ready for Transfer"
    doc.save()
    frappe.db.commit()

    return doc.status


@frappe.whitelist()
def start_transfer(batch_name):
    """
    Start the transfer process - records transfer_start_datetime.
    """
    if not batch_name:
        frappe.throw(_("Melting Batch is required."))

    doc = frappe.get_doc("Melting Batch", batch_name)

    if doc.status != "Ready for Transfer":
        frappe.throw(_("Batch must be Ready for Transfer to start transfer. Current: {0}").format(doc.status))

    doc.transfer_start_datetime = now_datetime()
    doc.save()
    frappe.db.commit()

    return {"transfer_start_datetime": str(doc.transfer_start_datetime)}


@frappe.whitelist()
def complete_transfer(batch_name, tapped_weight_mt=None, fo_temp_c=None,
                      fo_pressure_bar=None, dross_weight_kg=None, 
                      energy_fuel_litre=None, note=None):
    """
    Final transfer: record tapped weight, FO readings, dross, fuel, remarks.
    """
    if not batch_name:
        frappe.throw(_("Melting Batch is required."))

    doc = frappe.get_doc("Melting Batch", batch_name)

    if doc.status not in ["Ready for Transfer"]:
        frappe.throw(_("Batch must be Ready for Transfer to complete transfer. Current: {0}").format(doc.status))

    if tapped_weight_mt is not None and tapped_weight_mt != "":
        doc.tapped_weight_mt = flt(tapped_weight_mt, 3)

    if fo_temp_c is not None and fo_temp_c != "":
        doc.fo_temp_c = flt(fo_temp_c, 1)

    if fo_pressure_bar is not None and fo_pressure_bar != "":
        doc.fo_pressure_bar = flt(fo_pressure_bar, 2)

    if dross_weight_kg is not None and dross_weight_kg != "":
        doc.dross_weight_kg = flt(dross_weight_kg, 3)

    if energy_fuel_litre is not None and energy_fuel_litre != "":
        doc.energy_fuel_litre = flt(energy_fuel_litre, 2)

    doc.transfer_end_datetime = now_datetime()
    doc.batch_end_datetime = now_datetime()
    doc.status = "Transferred"

    # Recalculate yield
    if doc.charged_weight_mt and doc.tapped_weight_mt:
        doc.yield_percent = flt((doc.tapped_weight_mt / doc.charged_weight_mt) * 100, 2)

    # Add process log for transfer
    if note:
        prow = doc.append("process_logs", {})
        prow.log_time = doc.transfer_end_datetime
        prow.event_type = "Transfer"
        prow.note = note

    doc.save()
    frappe.db.commit()

    return {
        "status": doc.status,
        "yield_percent": doc.yield_percent
    }


@frappe.whitelist()
def update_batch_status(batch_name, new_status):
    """
    Update the status of a melting batch.
    Valid statuses: Draft, Charging, Melting, Ready for Transfer, Transferred, Cancelled
    """
    if not batch_name:
        frappe.throw(_("Melting Batch is required."))

    if not new_status:
        frappe.throw(_("New status is required."))

    valid_statuses = ["Draft", "Charging", "Melting", "Ready for Transfer", "Transferred", "Cancelled"]
    if new_status not in valid_statuses:
        frappe.throw(_("Invalid status: {0}. Valid statuses: {1}").format(new_status, ", ".join(valid_statuses)))

    doc = frappe.get_doc("Melting Batch", batch_name)
    doc.status = new_status
    doc.save()
    frappe.db.commit()

    return doc.status


@frappe.whitelist()
def get_batch_detail(batch_name):
    """
    Get full details of a melting batch including child tables.
    """
    if not batch_name:
        frappe.throw(_("Melting Batch is required."))

    doc = frappe.get_doc("Melting Batch", batch_name)

    return {
        "name": doc.name,
        "melting_batch_id": doc.melting_batch_id,
        "status": doc.status,
        "furnace": doc.furnace,
        "alloy": doc.alloy,
        "product_item": doc.product_item,
        "charge_mix_recipe": doc.charge_mix_recipe,
        "plan_date": str(doc.plan_date) if doc.plan_date else None,
        "planned_weight_mt": doc.planned_weight_mt,
        "charged_weight_mt": doc.charged_weight_mt,
        "tapped_weight_mt": doc.tapped_weight_mt,
        "yield_percent": doc.yield_percent,
        "batch_start_datetime": str(doc.batch_start_datetime) if doc.batch_start_datetime else None,
        "batch_end_datetime": str(doc.batch_end_datetime) if doc.batch_end_datetime else None,
        "transfer_start_datetime": str(doc.transfer_start_datetime) if doc.transfer_start_datetime else None,
        "transfer_end_datetime": str(doc.transfer_end_datetime) if doc.transfer_end_datetime else None,
        "fo_temp_c": doc.fo_temp_c,
        "fo_pressure_bar": doc.fo_pressure_bar,
        "dross_weight_kg": doc.dross_weight_kg,
        "energy_fuel_litre": doc.energy_fuel_litre,
        "remarks": doc.remarks,
        "raw_materials": [
            {
                "name": r.name,
                "row_index": r.row_index,
                "ingredient_type": r.ingredient_type,
                "item_code": r.item_code,
                "item_name": r.item_name,
                "batch_no": r.batch_no,
                "source_bin": r.source_bin,
                "bucket_no": r.bucket_no,
                "qty_kg": r.qty_kg,
                "is_correction": r.is_correction
            }
            for r in doc.raw_materials
        ],
        "process_logs": [
            {
                "name": p.name,
                "log_time": str(p.log_time) if p.log_time else None,
                "event_type": p.event_type,
                "temp_c": p.temp_c,
                "pressure_bar": p.pressure_bar,
                "flux_type": p.flux_type,
                "flux_qty_kg": p.flux_qty_kg,
                "sample_id": p.sample_id,
                "note": p.note
            }
            for p in doc.process_logs
        ],
        "spectro_samples": [
            {
                "name": s.name,
                "sample_id": s.sample_id,
                "sample_time": str(s.sample_time) if s.sample_time else None,
                "si_percent": s.si_percent,
                "fe_percent": s.fe_percent,
                "cu_percent": s.cu_percent,
                "mn_percent": s.mn_percent,
                "mg_percent": s.mg_percent,
                "zn_percent": s.zn_percent,
                "ti_percent": s.ti_percent,
                "al_percent": s.al_percent,
                "result_status": s.result_status,
                "correction_required": s.correction_required,
                "remarks": s.remarks
            }
            for s in doc.spectro_samples
        ]
    }

