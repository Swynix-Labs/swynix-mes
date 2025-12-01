// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on('Casting Operation', {
    onload(frm) {
        // Auto-generate casting_id for new documents
        if (frm.is_new() && !frm.doc.casting_id) {
            frappe.call({
                method: 'swynix_mes.swynix_mes.doctype.casting_operation.casting_operation.generate_casting_id',
                callback(r) {
                    if (r.message) {
                        frm.set_value('casting_id', r.message);
                    }
                }
            });
        }
        // Auto-fill operator with logged-in user for new documents
        if (frm.is_new() && !frm.doc.operator) {
            frm.set_value('operator', frappe.session.user);
        }
        // Set operator field as readonly
        frm.set_df_property('operator', 'read_only', 1);
        
        // Fetch total_cast_weight from melting batch on load
        if (frm.doc.melting_batch) {
            frappe.call({
                method: 'frappe.client.get',
                args: {
                    doctype: 'Melting Batch',
                    name: frm.doc.melting_batch
                },
                callback: function(r) {
                    if (r.message) {
                        // Set value even if it's 0
                        let metal_to_casting = parseFloat(r.message.metal_to_casting) || 0;
                        frm.set_value('total_cast_weight', metal_to_casting);
                    }
                }
            });
        } else if (!frm.doc.total_cast_weight) {
            // Set default to 0 if no melting batch selected
            frm.set_value('total_cast_weight', 0);
        }
    },
    operator(frm) {
        // Prevent operator from being changed - always reset to logged-in user
        if (frm.doc.operator !== frappe.session.user) {
            frm.set_value('operator', frappe.session.user);
        }
    },
    melting_batch(frm) {
        // Fetch metal_to_casting from melting batch and set as total_cast_weight
        if (frm.doc.melting_batch) {
            frappe.call({
                method: 'frappe.client.get',
                args: {
                    doctype: 'Melting Batch',
                    name: frm.doc.melting_batch
                },
                callback: function(r) {
                    if (r.message) {
                        // Set value even if it's 0
                        let metal_to_casting = parseFloat(r.message.metal_to_casting) || 0;
                        frm.set_value('total_cast_weight', metal_to_casting);
                    }
                }
            });
        } else {
            frm.set_value('total_cast_weight', 0);
        }
    },
    refresh(frm) {
        // Hide Update button if document is submitted
        if (frm.doc.docstatus === 1) {
            frm.page.clear_primary_action();
        }
        
        // Ensure operator is always set to logged-in user and readonly
        if (frm.is_new() && !frm.doc.operator) {
            frm.set_value('operator', frappe.session.user);
        }
        frm.set_df_property('operator', 'read_only', 1);
        
        // Fetch total_cast_weight from melting batch (always sync since it's readonly)
        if (frm.doc.melting_batch) {
            frappe.call({
                method: 'frappe.client.get',
                args: {
                    doctype: 'Melting Batch',
                    name: frm.doc.melting_batch
                },
                callback: function(r) {
                    if (r.message) {
                        // Set value even if it's 0
                        let metal_to_casting = parseFloat(r.message.metal_to_casting) || 0;
                        frm.set_value('total_cast_weight', metal_to_casting);
                    }
                }
            });
        } else if (!frm.doc.total_cast_weight) {
            // Set default to 0 if no melting batch selected
            frm.set_value('total_cast_weight', 0);
        }
        
        // Ensure total_cast_weight field is visible
        frm.set_df_property('total_cast_weight', 'hidden', 0);
        
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
        
        // Load connections (only if document is saved)
        if (!frm.is_new()) {
            load_connections(frm);
        }
    },

    // Whenever these fields change, recompute yield
    planned_melt_weight(frm) {
        calculate_yield(frm);
    },

    total_cast_weight(frm) {
        calculate_yield(frm);
    },

    start_time(frm) {
        calculate_duration(frm);
    },

    end_time(frm) {
        calculate_duration(frm);
    },

    // Also on validate – last safety net
    validate(frm) {
        calculate_duration(frm);
        calculate_yield(frm);
    },
    
    // Reload connections after save
    after_save(frm) {
        if (!frm.is_new()) {
            load_connections(frm);
        }
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

    // Check if current time falls within any active shift
    let current_datetime = frappe.datetime.now_datetime();
    let current_time_str = moment(current_datetime).format('HH:mm:ss');
    
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Shift Master',
            filters: {
                is_active: 1
            },
            fields: ['name', 'shift_name', 'start_time', 'end_time']
        },
        callback: function(r) {
            if (!r.message || r.message.length === 0) {
                frappe.msgprint({
                    title: __('No Active Shift Found'),
                    indicator: 'red',
                    message: __('No active shift found in Shift Master. Please create an active shift before starting casting.')
                });
                return;
            }

            let timeInShift = false;
            let matchedShift = null;

            r.message.forEach(shift => {
                if (shift.start_time && shift.end_time) {
                    // Parse time strings (format: HH:mm:ss or HH:mm)
                    let shiftStartStr = shift.start_time;
                    let shiftEndStr = shift.end_time;
                    
                    // Ensure time format is HH:mm:ss
                    if (shiftStartStr.length === 5) shiftStartStr += ':00';
                    if (shiftEndStr.length === 5) shiftEndStr += ':00';
                    
                    let shiftStart = moment(shiftStartStr, 'HH:mm:ss');
                    let shiftEnd = moment(shiftEndStr, 'HH:mm:ss');
                    let current = moment(current_time_str, 'HH:mm:ss');

                    // Handle shifts that span midnight (e.g., 22:00 to 06:00)
                    if (shiftEnd.isBefore(shiftStart) || shiftEnd.isSame(shiftStart)) {
                        // Shift spans midnight - add 1 day to end time for comparison
                        shiftEnd.add(1, 'day');
                        if (current.isBefore(shiftStart)) {
                            current.add(1, 'day');
                        }
                    }

                    if (current.isSameOrAfter(shiftStart) && current.isBefore(shiftEnd)) {
                        timeInShift = true;
                        matchedShift = shift;
                    }
                }
            });

            if (!timeInShift) {
                frappe.msgprint({
                    title: __('Shift Validation Failed'),
                    indicator: 'red',
                    message: __('Current time does not fall within any active shift. Please start casting during an active shift period.')
                });
                return;
            }

            // All validations passed, start casting
            frm.set_value('start_time', current_datetime);
            frm.set_value('status', 'In Progress');

            frm.save().then(() => {
                frappe.msgprint(__('Casting started.'));
            });
        }
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

/**
 * Load all connections (Coils, Dross Logs, Energy Logs) for this Casting Operation
 */
function load_connections(frm) {
    if (!frm.doc.name) return;
    
    load_coils(frm);
    load_dross_logs(frm);
    load_energy_logs(frm);
}

/**
 * Load and display Coils linked to this Casting Operation (only submitted)
 */
function load_coils(frm) {
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Coil',
            filters: {
                casting_operation: frm.doc.name,
                docstatus: 1  // Only submitted coils
            },
            fields: ['name', 'coil_id'],
            order_by: 'creation desc'
        },
        callback: function(r) {
            let html = '';
            if (r.message && r.message.length > 0) {
                html = '<table class="table table-bordered" style="width: 100%;">';
                html += '<thead><tr><th>ID</th><th>Name</th></tr></thead>';
                html += '<tbody>';
                r.message.forEach(coil => {
                    html += `<tr>
                        <td>${coil.coil_id || ''}</td>
                        <td><a href="#Form/Coil/${coil.name}" onclick="frappe.set_route('Form', 'Coil', '${coil.name}'); return false;">${coil.name}</a></td>
                    </tr>`;
                });
                html += '</tbody></table>';
            } else {
                html = '<p class="text-muted">No submitted coils found for this casting operation.</p>';
            }
            frm.set_df_property('coils_html', 'options', html);
        }
    });
}

/**
 * Load and display Dross Logs linked to this Casting Operation (only submitted)
 */
function load_dross_logs(frm) {
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Dross Log',
            filters: {
                casting_operation: frm.doc.name,
                docstatus: 1  // Only submitted logs
            },
            fields: ['name', 'dross_id', 'dross_qty', 'dross_quality'],
            order_by: 'creation desc'
        },
        callback: function(r) {
            let html = '';
            if (r.message && r.message.length > 0) {
                html = '<table class="table table-bordered" style="width: 100%;">';
                html += '<thead><tr><th>ID</th><th>Name</th><th>Quantity</th><th>Quality</th></tr></thead>';
                html += '<tbody>';
                r.message.forEach(log => {
                    html += `<tr>
                        <td>${log.dross_id || ''}</td>
                        <td><a href="#Form/Dross Log/${log.name}" onclick="frappe.set_route('Form', 'Dross Log', '${log.name}'); return false;">${log.name}</a></td>
                        <td>${log.dross_qty || 0}</td>
                        <td>${log.dross_quality || ''}</td>
                    </tr>`;
                });
                html += '</tbody></table>';
            } else {
                html = '<p class="text-muted">No submitted dross logs found for this casting operation.</p>';
            }
            frm.set_df_property('dross_logs_html', 'options', html);
        }
    });
}

/**
 * Load and display Energy Logs linked to this Casting Operation (only submitted)
 */
function load_energy_logs(frm) {
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Energy Log',
            filters: {
                casting_operation: frm.doc.name,
                docstatus: 1  // Only submitted logs
            },
            fields: ['name', 'utility_type', 'consumption', 'unit', 'from_time', 'to_time'],
            order_by: 'creation desc'
        },
        callback: function(r) {
            let html = '';
            if (r.message && r.message.length > 0) {
                html = '<table class="table table-bordered" style="width: 100%;">';
                html += '<thead><tr><th>Name</th><th>Utility Type</th><th>Consumption</th><th>Unit</th><th>From Time</th><th>To Time</th></tr></thead>';
                html += '<tbody>';
                r.message.forEach(log => {
                    html += `<tr>
                        <td><a href="#Form/Energy Log/${log.name}" onclick="frappe.set_route('Form', 'Energy Log', '${log.name}'); return false;">${log.name}</a></td>
                        <td>${log.utility_type || ''}</td>
                        <td>${log.consumption || 0}</td>
                        <td>${log.unit || ''}</td>
                        <td>${log.from_time ? frappe.datetime.str_to_user(log.from_time) : ''}</td>
                        <td>${log.to_time ? frappe.datetime.str_to_user(log.to_time) : ''}</td>
                    </tr>`;
                });
                html += '</tbody></table>';
            } else {
                html = '<p class="text-muted">No submitted energy logs found for this casting operation.</p>';
            }
            frm.set_df_property('energy_logs_html', 'options', html);
        }
    });
}
