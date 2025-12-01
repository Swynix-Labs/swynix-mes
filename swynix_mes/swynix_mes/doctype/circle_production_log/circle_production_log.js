// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on("Circle Production Log", {
	onload(frm) {
		// Auto-generate log_id for new documents
		if (frm.is_new() && !frm.doc.log_id) {
			frappe.call({
				method: 'swynix_mes.swynix_mes.doctype.circle_production_log.circle_production_log.generate_log_id',
				callback(r) {
					if (r.message) {
						frm.set_value('log_id', r.message);
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
		// Ensure operator is always set to logged-in user and readonly
		if (frm.is_new() && !frm.doc.operator) {
			frm.set_value('operator', frappe.session.user);
		}
		frm.set_df_property('operator', 'read_only', 1);
	},
});
