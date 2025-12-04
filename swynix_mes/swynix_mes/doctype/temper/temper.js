// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on("Temper", {
	setup(frm) {
		// Filter alloy to show only items in Alloy item group
		frm.set_query("alloy", "alloy_mappings", function() {
			return {
				filters: {
					item_group: "Alloy"
				}
			};
		});
	},

	refresh(frm) {
		// Show active/inactive indicator
		if (!frm.is_new()) {
			if (frm.doc.is_active) {
				frm.page.set_indicator(__("Active"), "green");
			} else {
				frm.page.set_indicator(__("Inactive"), "red");
			}
		}
	},

	temper_code(frm) {
		// Auto-uppercase temper code
		if (frm.doc.temper_code) {
			frm.set_value("temper_code", frm.doc.temper_code.toUpperCase().trim());
		}
	},

	series(frm) {
		// Auto-suggest hardness level based on series
		if (frm.doc.series === "O") {
			frm.set_value("hardness_level", "Fully Soft");
		} else if (frm.doc.series === "F") {
			frm.set_value("hardness_level", "");
		}
	}
});

frappe.ui.form.on("Temper Alloy Mapping", {
	alloy(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		// Check for duplicates
		if (row.alloy) {
			let duplicates = frm.doc.alloy_mappings.filter(
				r => r.alloy === row.alloy && r.name !== row.name
			);
			if (duplicates.length > 0) {
				frappe.msgprint(__("Alloy '{0}' is already mapped to this temper.", [row.alloy]));
				frappe.model.set_value(cdt, cdn, "alloy", null);
			}
		}
	},

	min_gauge_mm(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		// Validate min < max
		if (row.min_gauge_mm && row.max_gauge_mm && row.min_gauge_mm >= row.max_gauge_mm) {
			frappe.msgprint(__("Min Gauge must be less than Max Gauge"));
		}
	},

	max_gauge_mm(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		// Validate min < max
		if (row.min_gauge_mm && row.max_gauge_mm && row.min_gauge_mm >= row.max_gauge_mm) {
			frappe.msgprint(__("Min Gauge must be less than Max Gauge"));
		}
	}
});


