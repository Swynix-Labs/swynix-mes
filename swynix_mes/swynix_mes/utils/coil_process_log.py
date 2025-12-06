import frappe
from frappe.utils import now_datetime


def log_coil_event(
    coil=None,
    casting_run=None,
    event_type=None,
    reference_doctype=None,
    reference_name=None,
    details=None,
    remarks=None,
):
    """
    Create Coil Process Log entry (auditable timeline).
    """
    if not event_type:
        return
    doc = frappe.new_doc("Coil Process Log")
    doc.coil = coil
    doc.casting_run = casting_run
    doc.event_type = event_type
    doc.timestamp = now_datetime()
    doc.reference_doctype = reference_doctype
    doc.reference_name = reference_name
    doc.details = details
    doc.remarks = remarks
    doc.user = frappe.session.user if hasattr(frappe, "session") else None
    doc.insert(ignore_permissions=True)
    return doc.name

