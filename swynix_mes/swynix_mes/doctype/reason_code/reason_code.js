// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on("Reason Code", {
	refresh(frm) {
		// Hide Update button if document is submitted
		if (frm.doc.docstatus === 1) {
			frm.page.clear_primary_action();
		}
	},
});
