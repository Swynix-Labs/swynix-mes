// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on("Annealing Log", {
	onload(frm) {
		// Auto-generate annealing_id for new documents
		if (frm.is_new() && !frm.doc.annealing_id) {
			frappe.call({
				method: 'swynix_mes.swynix_mes.doctype.annealing_log.annealing_log.generate_annealing_id',
				callback(r) {
					if (r.message) {
						frm.set_value('annealing_id', r.message);
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
	},
});
