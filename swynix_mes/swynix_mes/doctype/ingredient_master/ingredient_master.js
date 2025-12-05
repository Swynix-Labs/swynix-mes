// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on("Ingredient Master", {
	refresh(frm) {
		// Show usage info
		if (!frm.is_new()) {
			frm.add_custom_button(__("View Usage"), function() {
				frappe.set_route("List", "Ingredient Master", {
					"name": frm.doc.name
				});
			});
		}
	},

	ingredient_name(frm) {
		// Auto-generate code from ingredient_name if code is empty
		if (frm.doc.ingredient_name && !frm.doc.code) {
			frm.set_value("code", frm.doc.ingredient_name.toUpperCase().replace(/ /g, "-"));
		}
	}
});

frappe.ui.form.on("Ingredient Item Group", {
	item_group(frm, cdt, cdn) {
		// Check for duplicate item groups
		let row = locals[cdt][cdn];
		if (row.item_group) {
			let duplicates = frm.doc.allowed_item_groups.filter(
				r => r.item_group === row.item_group && r.name !== row.name
			);
			if (duplicates.length > 0) {
				frappe.msgprint(__("Item Group '{0}' is already added.", [row.item_group]));
				frappe.model.set_value(cdt, cdn, "item_group", null);
			}
		}
	}
});








