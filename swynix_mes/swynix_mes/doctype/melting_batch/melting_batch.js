// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on('Melting Batch', {
    refresh(frm) {
        // No buttons on brand-new unsaved document
        if (frm.is_new()) return;

        // Avoid duplicates if refresh is called multiple times
        if (frm.clear_custom_buttons) {
            frm.clear_custom_buttons();
        }

        // --- Status-based main buttons ---

        // 1) Start Melting - only when still in Draft state (not started)
        if (!frm.doc.status || frm.doc.status === 'Draft') {
            frm.add_custom_button(__('Start Melting'), () => {
                if (frm.doc.start_time) {
                    frappe.msgprint(__('Start Time is already set.'));
                    return;
                }

                frm.set_value('start_time', frappe.datetime.now_datetime());
                frm.set_value('status', 'In Progress');
                frm.save();
            }, __('Operations')).addClass('btn-primary');

            // Load Raw Materials button also useful in Draft
            frm.add_custom_button(__('Load Raw Materials'), () => {
                load_raw_materials_from_plan(frm);
            }, __('Operations'));
        }

        // 2) End Melting - when In Progress and no end_time yet
        if (frm.doc.status === 'In Progress') {
            frm.add_custom_button(__('End Melting'), () => {
                if (frm.doc.end_time) {
                    frappe.msgprint(__('End Time is already set.'));
                    return;
                }

                frm.set_value('end_time', frappe.datetime.now_datetime());
                frm.set_value('status', 'Completed');
                frm.save();
            }, __('Operations')).addClass('btn-danger');

            // Allow loading raw materials even while in progress
            frm.add_custom_button(__('Load Raw Materials'), () => {
                load_raw_materials_from_plan(frm);
            }, __('Operations'));
        }

        // 3) Post-melting actions - when Completed
        if (frm.doc.status === 'Completed') {
            // Start Casting (create Casting Operation)
            frm.add_custom_button(__('Start Casting'), () => {
                create_casting_operation(frm);
            }, __('Next Step')).addClass('btn-primary');

            // Dross Log
            frm.add_custom_button(__('Add Dross Log'), () => {
                create_dross_log(frm);
            }, __('Logs'));

            // Energy Log
            frm.add_custom_button(__('Add Energy Log'), () => {
                create_energy_log(frm);
            }, __('Logs'));
        }

        // 4) Available in any non-new doc

        // Record parameters - scroll to parameters table and add a row
        frm.add_custom_button(__('Record Parameters'), () => {
            record_parameters_row(frm);
        }, __('Logs'));

        // Report Breakdown - open Breakdown Log with this batch prefilled
        frm.add_custom_button(__('Report Breakdown'), () => {
            create_breakdown_log(frm);
        }, __('Logs'));

        // Approve Deviation - if header has is_deviation checked
        if (frm.doc.is_deviation && !frm.doc.deviation_approved) {
            frm.add_custom_button(__('Approve Deviation'), () => {
                approve_deviation(frm);
            }, __('Supervisor')).addClass('btn-success');
        }

        // Print Heat Slip
        frm.add_custom_button(__('Print Heat Slip'), () => {
            frm.print_doc();
        }, __('Print'));
    }
});

// Helper: Load Raw Materials from Melting Batch Plan into Charged Materials
function load_raw_materials_from_plan(frm) {
    if (!frm.doc.melting_batch_plan) {
        frappe.msgprint(__('Please select a Melting Batch Plan first.'));
        return;
    }

    frappe.call({
        method: 'frappe.client.get',
        args: {
            doctype: 'Melting Batch Plan',
            name: frm.doc.melting_batch_plan
        },
        callback: function(r) {
            if (!r.message) {
                frappe.msgprint(__('Unable to load Melting Batch Plan.'));
                return;
            }

            const plan = r.message;
            const planned_rows = plan.planned_materials || [];

            if (!planned_rows.length) {
                frappe.msgprint(__('No Planned Materials found in the selected Melting Batch Plan.'));
                return;
            }

            frm.clear_table('charged_materials');

            planned_rows.forEach(row => {
                let child = frm.add_child('charged_materials');
                child.item = row.item;
                child.source_type = row.source_type;
                // If your fieldnames differ, adjust here:
                child.planned_qty_kg = row.planned_qty_kg || 0;
                // actual_qty_kg remains to be filled by operator
            });

            frm.refresh_field('charged_materials');
            frappe.msgprint(__('Planned materials loaded into Charged Materials. Please fill Actual Qty (kg).'));
        }
    });
}

// Helper: Record Parameters (focus + add a row)
function record_parameters_row(frm) {
    // Scroll to parameters table if present
    if (frm.fields_dict.parameters) {
        frm.scroll_to_field('parameters');
    }

    let child = frm.add_child('parameters');
    frm.refresh_field('parameters');

    frappe.msgprint(__('New parameter row added. Please select parameter and enter actual value.'));
}

// Helper: Create Casting Operation from Melting Batch
function create_casting_operation(frm) {
    frappe.model.with_doctype('Casting Operation', () => {
        let doc = frappe.model.get_new_doc('Casting Operation');
        // Prefill some key fields
        doc.melting_batch = frm.doc.name;
        doc.alloy_grade = frm.doc.alloy_grade;
        doc.recipe = frm.doc.recipe;
        doc.furnace = frm.doc.furnace;
        doc.heat_number = frm.doc.heat_number;

        frappe.set_route('Form', 'Casting Operation', doc.name);
    });
}

// Helper: Create Dross Log from Melting Batch
function create_dross_log(frm) {
    frappe.model.with_doctype('Dross Log', () => {
        let doc = frappe.model.get_new_doc('Dross Log');
        doc.melting_batch = frm.doc.name;
        doc.alloy_grade = frm.doc.alloy_grade;
        doc.furnace = frm.doc.furnace;
        doc.heat_number = frm.doc.heat_number;

        frappe.set_route('Form', 'Dross Log', doc.name);
    });
}

// Helper: Create Energy Log from Melting Batch
function create_energy_log(frm) {
    frappe.model.with_doctype('Energy Log', () => {
        let doc = frappe.model.get_new_doc('Energy Log');
        doc.melting_batch = frm.doc.name;
        doc.furnace = frm.doc.furnace;
        doc.shift = frm.doc.shift;
        doc.batch_id = frm.doc.name;

        frappe.set_route('Form', 'Energy Log', doc.name);
    });
}

// Helper: Create Breakdown Log from Melting Batch
function create_breakdown_log(frm) {
    frappe.model.with_doctype('Breakdown Log', () => {
        let doc = frappe.model.get_new_doc('Breakdown Log');
        doc.reference_doctype = 'Melting Batch';
        doc.reference_name = frm.doc.name;
        doc.machine = frm.doc.furnace;
        doc.shift = frm.doc.shift;

        frappe.set_route('Form', 'Breakdown Log', doc.name);
    });
}

// Helper: Approve Deviation (Supervisor action)
function approve_deviation(frm) {
    frappe.confirm(
        __('Are you sure you want to approve this deviation?'),
        () => {
            frm.set_value('deviation_approved', 1);
            frm.set_value('deviation_approved_by', frappe.session.user);
            frm.save().then(() => {
                frappe.msgprint(__('Deviation approved.'));
                frm.reload_doc();
            });
        }
    );
}
