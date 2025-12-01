// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on("Casting Operation 2", {
	onload(frm) {
		// Auto-generate casting_operation_id for new documents
		if (frm.is_new() && !frm.doc.casting_operation_id) {
			frappe.call({
				method: 'swynix_mes.swynix_mes.doctype.casting_operation_2.casting_operation_2.generate_casting_operation_id',
				callback(r) {
					if (r.message) {
						frm.set_value('casting_operation_id', r.message);
					}
				}
			});
		}
	},
});
