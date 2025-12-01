// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on("Reel", {
	onload(frm) {
		// Auto-generate reel_id for new documents
		if (frm.is_new() && !frm.doc.reel_id) {
			frappe.call({
				method: 'swynix_mes.swynix_mes.doctype.reel.reel.generate_reel_id',
				callback(r) {
					if (r.message) {
						frm.set_value('reel_id', r.message);
					}
				}
			});
		}
	},
	refresh(frm) {
		// Hide Update button if document is submitted
		if (frm.doc.docstatus === 1) {
			frm.page.clear_primary_action();
		}
	},
});
