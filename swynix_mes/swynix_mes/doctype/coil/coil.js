// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on('Coil', {
    onload(frm) {
        // Auto-generate coil_id for new documents if empty
        if (frm.is_new() && !frm.doc.coil_id) {
            generate_coil_id(frm);
        }
        
        // Add generate button next to coil_id field
        setup_coil_id_generate_button(frm);
    },
    
    refresh(frm) {
        // Hide Update button if document is submitted
        if (frm.doc.docstatus === 1) {
            frm.page.clear_primary_action();
        }
        
        // Setup generate button for coil_id field
        setup_coil_id_generate_button(frm);

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
    
    coil_id(frm) {
        // Remove generate button if coil_id is filled
        if (frm.doc.coil_id) {
            remove_coil_id_generate_button(frm);
        } else {
            setup_coil_id_generate_button(frm);
        }
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

// Function to generate coil_id
function generate_coil_id(frm) {
    frappe.call({
        method: 'swynix_mes.swynix_mes.doctype.coil.coil.generate_coil_id',
        callback(r) {
            if (r.message) {
                frm.set_value('coil_id', r.message);
            }
        }
    });
}

// Setup generate button next to coil_id field
function setup_coil_id_generate_button(frm) {
    // Remove existing button if any
    remove_coil_id_generate_button(frm);
    
    // Only show button if coil_id is empty
    if (!frm.doc.coil_id && frm.is_new()) {
        let field = frm.get_field('coil_id');
        if (field && field.$input) {
            let $wrapper = field.$input.parent();
            if (!$wrapper.find('.generate-coil-id-btn').length) {
                let $btn = $('<button>')
                    .addClass('btn btn-sm btn-secondary generate-coil-id-btn')
                    .html('<i class="fa fa-refresh"></i>')
                    .attr('title', __('Generate Coil ID'))
                    .css({
                        'margin-left': '5px',
                        'padding': '4px 8px'
                    })
                    .on('click', function(e) {
                        e.preventDefault();
                        e.stopPropagation();
                        generate_coil_id(frm);
                    });
                $wrapper.append($btn);
            }
        }
    }
}

// Remove generate button
function remove_coil_id_generate_button(frm) {
    let field = frm.get_field('coil_id');
    if (field && field.$input) {
        field.$input.parent().find('.generate-coil-id-btn').remove();
    }
}
