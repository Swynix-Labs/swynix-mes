// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on("Packing Batch", {
	onload(frm) {
		set_reference_filters(frm);
		// Auto-generate packing_batch_id for new documents
		if (frm.is_new() && !frm.doc.packing_batch_id) {
			frappe.call({
				method: 'swynix_mes.swynix_mes.doctype.packing_batch.packing_batch.generate_packing_batch_id',
				callback(r) {
					if (r.message) {
						frm.set_value('packing_batch_id', r.message);
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
		
		set_reference_filters(frm);

		if (!frm.is_new()) {
			frm.add_custom_button(__("Load Items from WIP"), () => {
				load_items_from_wip(frm);
			});
		}
	},
});

function set_reference_filters(frm) {
	// Example hook: restrict source_doctype/source_name later if needed
}

function load_items_from_wip(frm) {
	if (!frm.doc.source_doctype || !frm.doc.source_name) {
		frappe.msgprint(
			__("Please select Source Doctype and Source Document to load items from.")
		);
		return;
	}

	frappe.call({
		method:
			"swynix_mes.swynix_mes.doctype.packing_batch.packing_batch.load_items_from_source",
		args: {
			source_doctype: frm.doc.source_doctype,
			source_name: frm.doc.source_name,
		},
		callback(r) {
			if (!r.message || !r.message.items) return;

			frm.clear_table("items");
			(r.message.items || []).forEach((row) => {
				const child = frm.add_child("items");
				child.item = row.item;
				child.source_reference = row.source_reference;
				child.qty = row.qty;
				child.uom = row.uom;
			});

			frm.refresh_field("items");
		},
	});
}



