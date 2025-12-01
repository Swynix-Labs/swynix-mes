// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on("Caster QC Inspection", {
	onload(frm) {
		// Auto-generate qc_id for new documents
		if (frm.is_new() && !frm.doc.qc_id) {
			frappe.call({
				method: 'swynix_mes.swynix_mes.doctype.caster_qc_inspection.caster_qc_inspection.generate_qc_id',
				callback(r) {
					if (r.message) {
						frm.set_value('qc_id', r.message);
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
