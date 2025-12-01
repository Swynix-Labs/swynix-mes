// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on('Coil Operation', {
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
        // Calculate duration
        calculate_duration(frm);
        
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
    },
    start_time(frm) {
        calculate_duration(frm);
    },
    end_time(frm) {
        calculate_duration(frm);
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

