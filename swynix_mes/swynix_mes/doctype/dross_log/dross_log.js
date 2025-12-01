// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on("Dross Log", {
	onload(frm) {
		// Auto-generate dross_id for new documents
		if (frm.is_new() && !frm.doc.dross_id) {
			frappe.call({
				method: 'swynix_mes.swynix_mes.doctype.dross_log.dross_log.generate_dross_id',
				callback(r) {
					if (r.message) {
						frm.set_value('dross_id', r.message);
					}
				}
			});
		}
	},
});
