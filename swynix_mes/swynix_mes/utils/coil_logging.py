import frappe
from frappe.utils import now_datetime


# Run-level events that don't require a coil
RUN_LEVEL_EVENTS = [
    "CASTING_RUN_STARTED",
    "CASTING_RUN_STOPPED",
    "RUN_STARTED",
    "RUN_STOPPED",
]


def log_coil_event(
    coil=None,
    event_type=None,
    casting_run=None,
    reference_doctype=None,
    reference_name=None,
    details=None,
    remarks=None,
):
    """
    Safe logger for Coil Process Log.
    
    Supports two types of log entries:
    1. Run-level events (coil=None): CASTING_RUN_STARTED, CASTING_RUN_STOPPED, etc.
    2. Coil-level events (coil required): COIL_STARTED, SAMPLE_TAKEN, QC_RESULT_RECEIVED, etc.
    
    Args:
        coil: Link to Mother Coil (optional for run-level events)
        event_type: Type of event being logged
        casting_run: Link to Casting Run (optional)
        reference_doctype: Reference doctype for the event
        reference_name: Reference document name
        details: Event details text
        remarks: Additional remarks
        
    Silently no-ops if DocType not migrated yet.
    """
    if not frappe.db.exists("DocType", "Coil Process Log"):
        return
    
    if not event_type:
        return
    
    # Get actual user from session, not the string "frappe.session.user"
    current_user = frappe.session.user if frappe.session else "Administrator"
    
    # Build the document data
    doc_data = {
        "doctype": "Coil Process Log",
        "casting_run": casting_run,
        "event_type": event_type,
        "reference_doctype": reference_doctype,
        "reference_name": reference_name,
        "details": details,
        "remarks": remarks,
        "user": current_user,
        "timestamp": now_datetime(),
    }
    
    # Only set coil if it's provided (allows NULL for run-level events)
    if coil:
        doc_data["coil"] = coil
    
    doc = frappe.get_doc(doc_data)
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

