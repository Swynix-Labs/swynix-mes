// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on("Slitting Operation Log", {
	onload(frm) {
		// Auto-generate operation_id for new documents
		if (frm.is_new() && !frm.doc.operation_id) {
			frappe.call({
				method: 'swynix_mes.swynix_mes.doctype.slitting_operation_log.slitting_operation_log.generate_operation_id',
				callback(r) {
					if (r.message) {
						frm.set_value('operation_id', r.message);
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
