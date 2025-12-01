// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on('Melting Batch', {
    onload(frm) {
        // Auto-fill operator with logged-in user for new documents
        if (frm.is_new() && !frm.doc.operator) {
            frm.set_value('operator', frappe.session.user);
        }

        // Set operator field as readonly
        frm.set_df_property('operator', 'read_only', 1);
    },
    operator(frm) {
        // Prevent operator from being changed - always reset to logged-in user
        if (frm.doc.operator !== frappe.session.user) {
            frm.set_value('operator', frappe.session.user);
        }
    },
    metal_to_casting(frm) {
        calculate_metal_recovery(frm);
    },
    melting_batch_plan(frm) {
        if (frm.doc.melting_batch_plan) {
            load_planned_materials_from_plan(frm);
        } else {
            frm.clear_table('charged_materials');
            frm.refresh_field('charged_materials');
        }
        // Recalculate total_charged after materials are loaded
        calculate_total_charged(frm);
    },
    refresh(frm) {
        // Hide Update button if document is submitted
        if (frm.doc.docstatus === 1) {
            frm.page.clear_primary_action();
            frm.remove_custom_button('Update')
        }
        
        // Ensure operator is always set to logged-in user and readonly
        if (frm.is_new() && !frm.doc.operator) {
            frm.set_value('operator', frappe.session.user);
        }
        frm.set_df_property('operator', 'read_only', 1);
        
        // Calculate duration
        calculate_duration(frm);
        
        // Calculate total charged and metal recovery
        calculate_total_charged(frm);
        calculate_metal_recovery(frm);
        
        // Set up periodic update for duration if end_time is not set
        if (frm.doc.start_time && !frm.doc.end_time) {
            if (frm.duration_interval) {
                clearInterval(frm.duration_interval);
            }
            frm.duration_interval = setInterval(() => {
                if (frm.doc.start_time && !frm.doc.end_time) {
                    calculate_duration(frm);
                } else {
                    clearInterval(frm.duration_interval);
                }
            }, 60000); // Update every minute
        } else {
            if (frm.duration_interval) {
                clearInterval(frm.duration_interval);
                frm.duration_interval = null;
            }
        }
        
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
                calculate_duration(frm);
                frm.save();
            }, __('Operations')).addClass('btn-danger');

            // Allow loading raw materials even while in progress
            frm.add_custom_button(__('Load Raw Materials'), () => {
                load_raw_materials_from_plan(frm);
            }, __('Operations'));
        }

        // 3) Post-melting actions - when Completed
        if (frm.doc.status === 'Completed') {
            // Get PLC - show before submit (when status is Completed but docstatus is 0)
            if (!frm.is_new() && frm.doc.docstatus === 0) {
                frm.add_custom_button(__('Get PLC'), () => {
                    // Placeholder - no action for now
                }, __('Operations'));
            }

            // Start Casting (create Casting Operation) - only show after document is submitted
            // docstatus === 1 means document is submitted (not just saved)
            if (!frm.is_new() && frm.doc.docstatus === 1) {
                frm.add_custom_button(__('Start Casting'), () => {
                    create_casting_operation(frm);
                }, __('Next Step')).addClass('btn-primary');
            }

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

        // Print Heat Slip
        frm.add_custom_button(__('Print Heat Slip'), () => {
            frm.print_doc();
        }, __('Print'));
    }
});

// Helper: Load Raw Materials from Melting Batch Plan into Charged Materials (auto-fetch)
function load_planned_materials_from_plan(frm) {
    if (!frm.doc.melting_batch_plan) {
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
                return;
            }

            const plan = r.message;
            const planned_rows = plan.planned_materials || [];

            if (!planned_rows.length) {
                return;
            }

            frm.clear_table('charged_materials');

            planned_rows.forEach(row => {
                let child = frm.add_child('charged_materials');
                child.item = row.item;
                child.source_type = row.source_type;
                // Map planned_qty from Recipe Detail to planned_qty_kg in Planned Raw Material
                child.planned_qty_kg = row.planned_qty || 0;
                // actual_qty and warehouse remain to be filled by operator
            });

            frm.refresh_field('charged_materials');
        }
    });
}

// Helper: Load Raw Materials from Melting Batch Plan into Charged Materials (manual button)
function load_raw_materials_from_plan(frm) {
    if (!frm.doc.melting_batch_plan) {
        frappe.msgprint(__('Please select a Melting Batch Plan first.'));
        return;
    }

    load_planned_materials_from_plan(frm);
    frappe.msgprint(__('Planned materials loaded into Charged Materials. Please fill Actual Qty (kg) and Warehouse.'));
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

// Handle Planned Raw Material child table
frappe.ui.form.on('Planned Raw Material', {
    item(frm, cdt, cdn) {
        // Prevent manual editing of item if it was auto-filled from plan
        let row = locals[cdt][cdn];
        if (frm.doc.melting_batch_plan && row.item) {
            // Item should remain readonly - this is just a safeguard
        }
    },
    source_type(frm, cdt, cdn) {
        // Prevent manual editing of source_type if it was auto-filled from plan
        let row = locals[cdt][cdn];
        if (frm.doc.melting_batch_plan && row.source_type) {
            // Source type should remain readonly - this is just a safeguard
        }
    },
    actual_qty(frm, cdt, cdn) {
        // Recalculate total_charged when actual_qty changes
        calculate_total_charged(frm);
        calculate_metal_recovery(frm);
    },
    form_render(frm, cdt, cdn) {
        // Ensure readonly fields remain readonly when form is rendered
        let row = locals[cdt][cdn];
        if (frm.doc.melting_batch_plan) {
            // Fields are already readonly from JSON, but ensure they stay that way
            if (row.item) {
                frm.set_df_property('item', 'read_only', 1, cdn, 'charged_materials');
            }
            if (row.source_type) {
                frm.set_df_property('source_type', 'read_only', 1, cdn, 'charged_materials');
            }
        }
    },
    charged_materials_remove(frm) {
        // Recalculate when row is removed
        calculate_total_charged(frm);
        calculate_metal_recovery(frm);
    }
});

/**
 * Calculate Duration in minutes from start_time & end_time
 * If end_time is not set, use current time
 */
function calculate_duration(frm) {
    if (frm.doc.start_time) {
        // moment.js is available in Frappe
        let start = moment(frm.doc.start_time);
        let end = frm.doc.end_time ? moment(frm.doc.end_time) : moment();

        if (end.isBefore(start)) {
            frappe.msgprint(__('End Time is before Start Time. Please correct the timings.'));
            return;
        }

        let diff_mins = moment.duration(end.diff(start)).asMinutes();
        diff_mins = Math.round(diff_mins * 10) / 10; // 1 decimal place

        frm.set_value('duration_mins', diff_mins);
    } else {
        // Clear duration if start_time is missing
        frm.set_value('duration_mins', null);
    }
}

/**
 * Calculate Total Charged from sum of actual_qty in charged_materials table
 */
function calculate_total_charged(frm) {
    let total = 0;
    if (frm.doc.charged_materials && frm.doc.charged_materials.length > 0) {
        frm.doc.charged_materials.forEach(row => {
            if (row.actual_qty) {
                total += parseFloat(row.actual_qty) || 0;
            }
        });
    }
    frm.set_value('total_charged', total);
}

/**
 * Calculate Metal Recovery % = (Metal to Casting / Total Charged) * 100
 */
function calculate_metal_recovery(frm) {
    let metal_to_casting = parseFloat(frm.doc.metal_to_casting) || 0;
    let total_charged = parseFloat(frm.doc.total_charged) || 0;

    if (total_charged > 0 && metal_to_casting >= 0) {
        let recovery = (metal_to_casting / total_charged) * 100;
        recovery = Math.round(recovery * 100) / 100; // 2 decimal places
        frm.set_value('metal_recovery_pct', recovery);
    } else {
        frm.set_value('metal_recovery_pct', null);
    }
}
