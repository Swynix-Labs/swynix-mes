// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on('Casting Operation', {
    refresh(frm) {
        // Clean old buttons
        frm.clear_custom_buttons();

        // Only in Draft
        if (frm.doc.docstatus === 0) {
            // Not started yet → show "Start Casting"
            if (!frm.doc.start_time) {
                frm.add_custom_button(__('Start Casting'), () => {
                    start_casting(frm);
                }).addClass('btn-primary');
            }
            // Started but not ended → show "Stop Casting"
            else if (frm.doc.start_time && !frm.doc.end_time) {
                frm.add_custom_button(__('Stop Casting'), () => {
                    stop_casting(frm);
                }).addClass('btn-danger');
            }
        }

        // Only after save + submit we allow further actions
        if (!frm.is_new() && frm.doc.docstatus === 1) {
            // Group name "Further Operations" just for UI grouping
            frm.add_custom_button(__('Create Coils'), () => {
                make_coils_from_cast(frm);
            }, __('Further Operations'));

            frm.add_custom_button(__('Create Dross Log'), () => {
                make_dross_log_from_cast(frm);
            }, __('Further Operations'));

            frm.add_custom_button(__('Create Energy Log'), () => {
                make_energy_log_from_cast(frm);
            }, __('Further Operations'));
        }

        // Recalculate on refresh (in case something changed via server)
        calculate_duration(frm);
        calculate_yield(frm);
    },

    // Whenever these fields change, recompute yield
    planned_melt_weight(frm) {
        calculate_yield(frm);
    },

    total_cast_weight(frm) {
        calculate_yield(frm);
    },

    // Also on validate – last safety net
    validate(frm) {
        calculate_duration(frm);
        calculate_yield(frm);
    }
});

/**
 * Start Casting:
 * - basic validations
 * - set start_time = now
 * - status = "In Progress"
 * - save doc
 */
function start_casting(frm) {
    // Basic checks
    if (!frm.doc.melting_batch) {
        frappe.msgprint(__('Please select a Melting Batch before starting casting.'));
        return;
    }
    if (!frm.doc.caster_machine) {
        frappe.msgprint(__('Please select a Caster Machine before starting casting.'));
        return;
    }
    if (!frm.doc.operator) {
        frappe.msgprint(__('Please select an Operator before starting casting.'));
        return;
    }

    if (frm.doc.start_time) {
        frappe.msgprint(__('Casting already started.'));
        return;
    }

    frm.set_value('start_time', frappe.datetime.now_datetime());
    frm.set_value('status', 'In Progress');

    frm.save().then(() => {
        frappe.msgprint(__('Casting started.'));
    });
}

/**
 * Stop Casting:
 * - require start_time
 * - set end_time = now
 * - calculate duration + yield
 * - status = "Completed"
 * - save doc
 */
function stop_casting(frm) {
    if (!frm.doc.start_time) {
        frappe.msgprint(__('Cannot stop casting because Start Time is not set.'));
        return;
    }
    if (frm.doc.end_time) {
        frappe.msgprint(__('Casting is already stopped.'));
        return;
    }

    // Optional: ensure total_cast_weight is entered
    if (!frm.doc.total_cast_weight) {
        frappe.confirm(
            __('Total Cast Weight is empty. Do you still want to stop casting?'),
            () => {
                perform_stop(frm);
            }
        );
    } else {
        perform_stop(frm);
    }
}

function perform_stop(frm) {
    frm.set_value('end_time', frappe.datetime.now_datetime());
    frm.set_value('status', 'Completed');

    calculate_duration(frm);
    calculate_yield(frm);

    frm.save().then(() => {
        frappe.msgprint(__('Casting stopped and marked as Completed.'));
    });
}

/**
 * Calculate Duration in minutes from start_time & end_time
 */
function calculate_duration(frm) {
    if (frm.doc.start_time && frm.doc.end_time) {
        // moment.js is available in Frappe
        let start = moment(frm.doc.start_time);
        let end = moment(frm.doc.end_time);

        if (end.isBefore(start)) {
            frappe.msgprint(__('End Time is before Start Time. Please correct the timings.'));
            return;
        }

        let diff_mins = moment.duration(end.diff(start)).asMinutes();
        diff_mins = Math.round(diff_mins * 10) / 10; // 1 decimal place

        frm.set_value('duration_mins', diff_mins);
    }
}

/**
 * Calculate Yield % = (total_cast_weight / planned_melt_weight) * 100
 */
function calculate_yield(frm) {
    let planned = parseFloat(frm.doc.planned_melt_weight) || 0;
    let cast = parseFloat(frm.doc.total_cast_weight) || 0;

    if (planned > 0 && cast >= 0) {
        let y = (cast / planned) * 100;
        y = Math.round(y * 100) / 100; // 2 decimals
        frm.set_value('yield_percent', y);
    } else {
        frm.set_value('yield_percent', null);
    }
}

/**
 * Create Coil doc pre-filled from Casting Operation
 * (user will duplicate / create as many coils as needed)
 */
function make_coils_from_cast(frm) {
    if (!frm.doc.total_cast_weight) {
        frappe.msgprint(__('Please enter Total Cast Weight (kg) before creating coils.'));
        return;
    }

    // Default per-coil weight suggestion (can be edited in the Coil form)
    let no_of_coils = frm.doc.no_of_coils || 1;
    let per_coil_weight = frm.doc.total_cast_weight / no_of_coils;

    frappe.route_options = {
        // adjust fieldnames in Coil as per your doctype
        casting_operation: frm.doc.name,
        melting_batch: frm.doc.melting_batch,
        heat_number: frm.doc.heat_number,
        alloy_grade: frm.doc.alloy_grade,
        planned_weight: per_coil_weight,     // or 'coil_weight' if that's your field
    };

    frappe.new_doc('Coil');
}

/**
 * Create Dross Log linked to this Casting Operation
 */
function make_dross_log_from_cast(frm) {
    frappe.route_options = {
        casting_operation: frm.doc.name,
        melting_batch: frm.doc.melting_batch,
        heat_number: frm.doc.heat_number,
        alloy_grade: frm.doc.alloy_grade,
        // you can also pass default weight = frm.doc.dross_weight if you have it
    };

    frappe.new_doc('Dross Log');
}

/**
 * Create Energy Log linked to this Casting Operation
 */
function make_energy_log_from_cast(frm) {
    frappe.route_options = {
        casting_operation: frm.doc.name,
        melting_batch: frm.doc.melting_batch,
        heat_number: frm.doc.heat_number,
        furnace: frm.doc.furnace,
        shift: frm.doc.shift,
        // e.g. default_start_time: frm.doc.start_time if you want
    };

    frappe.new_doc('Energy Log');
}
