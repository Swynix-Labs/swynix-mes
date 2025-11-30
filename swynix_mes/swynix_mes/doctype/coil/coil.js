// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on('Coil', {
    refresh(frm) {

        // Start QC Button
        if (!frm.is_new() && frm.doc.qc_status === "Pending") {
            frm.add_custom_button(__('Start QC'), () => {
                frappe.route_options = {
                    reference_type: 'Coil',
                    reference_name: frm.doc.name,
                    inspection_type: 'Final',
                    quality_inspection_template: 'Coil - Final QC'
                };
                frappe.new_doc('Quality Inspection');
            }, __('Quality'));
        }

        // Open QC
        if (frm.doc.quality_inspection) {
            frm.add_custom_button(__('Open Inspection'), () => {
                frappe.set_route('Form', 'Quality Inspection', frm.doc.quality_inspection);
            }, __('Quality'));
        }

        // Print Label
        frm.add_custom_button(__('Print Label'), () => {
            frappe.call({
                method: "frappe.client.get",
                args: {
                    doctype: "Print Format",
                    name: "Coil Label"
                },
                callback() {
                    frappe.set_route("print", "Coil", frm.doc.name, "Coil Label");
                }
            })
        }, __('Actions'));

        // Mark Consumed
        if (!frm.doc.is_consumed) {
            frm.add_custom_button(__('Mark Consumed'), () => {
                frm.set_value("is_consumed", 1);
                frm.save();
            }, __('Actions'));
        }

        // Create Slitting Batch
        frm.add_custom_button(__('Create Slitting Batch'), () => {
            frappe.route_options = { coil: frm.doc.name };
            frappe.new_doc('Slitting Batch');
        }, __('Next Operations'));
    },

    // Autofill Data from Casting Operation
    casting_operation(frm) {
        if (frm.doc.casting_operation) {
            frappe.call({
                method: "frappe.client.get",
                args: {
                    doctype: "Casting Operation",
                    name: frm.doc.casting_operation
                },
                callback(r) {
                    if (!r.message) return;
                    let op = r.message;

                    frm.set_value("melting_batch", op.melting_batch);
                    frm.set_value("alloy_grade", op.alloy_grade);
                    frm.set_value("shift", op.shift);
                    frm.set_value("furnace", op.furnace);
                    frm.set_value("produced_on", op.end_time);
                }
            });
        }
    }
});
