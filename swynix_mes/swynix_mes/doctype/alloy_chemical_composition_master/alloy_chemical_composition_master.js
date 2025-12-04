// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on("Alloy Chemical Composition Master", {
	refresh(frm) {
		// Set filter for alloy field
		frm.set_query("alloy", function() {
			return {
				filters: {
					item_group: "Alloy"
				}
			};
		});
		
		// Set filters for child table element fields
		frm.set_query("element_1", "composition_details", function() {
			return {
				filters: {
					item_group: "Chemicals for Composition"
				}
			};
		});
		
		frm.set_query("element_2", "composition_details", function() {
			return {
				filters: {
					item_group: "Chemicals for Composition"
				}
			};
		});
		
		frm.set_query("element_3", "composition_details", function() {
			return {
				filters: {
					item_group: "Chemicals for Composition"
				}
			};
		});
		
		// Initialize field visibility for all rows after a short delay to ensure grid is ready
		setTimeout(() => {
			if (frm.doc.composition_details && frm.doc.composition_details.length > 0) {
				frm.doc.composition_details.forEach((row) => {
					if (row.name) {
						toggle_rule_fields(frm, "composition_details", row.name);
					}
				});
			}
		}, 100);
	},
	
	alloy(frm) {
		// Fetch alloy name when alloy is selected
		if (frm.doc.alloy) {
			frappe.db.get_value("Item", frm.doc.alloy, "item_name", (r) => {
				if (r) {
					frm.set_value("alloy_name", r.item_name);
				}
			});
		}
	}
});

// Handle child table events for dynamic field visibility
frappe.ui.form.on("Alloy Chemical Rule Detail", {
	condition_type(frm, cdt, cdn) {
		// Clear dependent fields when condition type changes
		clear_fields_for_condition_type(frm, cdt, cdn);
		toggle_rule_fields(frm, cdt, cdn);
		frm.refresh_field("composition_details");
	},
	
	limit_type(frm, cdt, cdn) {
		toggle_rule_fields(frm, cdt, cdn);
		frm.refresh_field("composition_details");
	},
	
	sum_limit_type(frm, cdt, cdn) {
		// Clear fields based on sum_limit_type
		let row = locals[cdt][cdn];
		if (row.sum_limit_type === "Minimum") {
			frappe.model.set_value(cdt, cdn, "sum_max_percentage", "");
		} else if (row.sum_limit_type === "Maximum") {
			frappe.model.set_value(cdt, cdn, "sum_min_percentage", "");
		}
		toggle_rule_fields(frm, cdt, cdn);
		frm.refresh_field("composition_details");
	},
	
	element_2(frm, cdt, cdn) {
		toggle_rule_fields(frm, cdt, cdn);
		frm.refresh_field("composition_details");
	},
	
	element_3(frm, cdt, cdn) {
		toggle_rule_fields(frm, cdt, cdn);
		frm.refresh_field("composition_details");
	},
	
	alloy_chemical_rule_detail_add(frm, cdt, cdn) {
		// When a new row is added, initialize field visibility
		setTimeout(() => {
			toggle_rule_fields(frm, cdt, cdn);
		}, 50);
	},
	
	form_render(frm, cdt, cdn) {
		toggle_rule_fields(frm, cdt, cdn);
	}
});

function clear_fields_for_condition_type(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	
	if (row.condition_type !== "Normal Limit") {
		frappe.model.set_value(cdt, cdn, "limit_type", "");
		frappe.model.set_value(cdt, cdn, "min_percentage", "");
		frappe.model.set_value(cdt, cdn, "max_percentage", "");
	}
	
	if (row.condition_type !== "Sum Limit") {
		frappe.model.set_value(cdt, cdn, "sum_limit_type", "");
		frappe.model.set_value(cdt, cdn, "sum_min_percentage", "");
		frappe.model.set_value(cdt, cdn, "sum_max_percentage", "");
	}
	
	if (row.condition_type !== "Ratio") {
		frappe.model.set_value(cdt, cdn, "ratio_value_1", "");
		frappe.model.set_value(cdt, cdn, "ratio_value_2", "");
		frappe.model.set_value(cdt, cdn, "ratio_value_3", "");
	}
	
	if (row.condition_type !== "Remainder") {
		// min_percentage is optional for Remainder, so we don't clear it
	}
	
	if (row.condition_type !== "Free Text") {
		// notes can be kept for other types too
	}
	
	// Clear element_2 and element_3 for Normal Limit, Remainder, and Free Text
	if (row.condition_type === "Normal Limit" || row.condition_type === "Remainder" || row.condition_type === "Free Text") {
		frappe.model.set_value(cdt, cdn, "element_2", "");
		frappe.model.set_value(cdt, cdn, "element_3", "");
	}
}

function toggle_rule_fields(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row) return;
	
	// Check if we're in a form dialog (editing mode) or grid mode
	let is_form_dialog = false;
	let target_frm = frm;
	
	// Try to detect if we're in a dialog (when editing child table row)
	if (cdt === "Alloy Chemical Rule Detail" && cdn) {
		// Check if there's an active dialog
		if (window.cur_dialog && window.cur_dialog.fields_dict) {
			target_frm = window.cur_dialog;
			is_form_dialog = true;
		} else if (frm.dialog && frm.dialog.fields_dict) {
			target_frm = frm.dialog;
			is_form_dialog = true;
		}
	}
	
	const grid = frm.fields_dict.composition_details?.grid;
	const grid_row = grid ? grid.get_row(cdn) : null;
	
	// Helper function to toggle display - works for both grid and form dialog
	const show = (fieldname, visible) => {
		if (is_form_dialog) {
			// Form dialog mode - use the dialog's form
			if (target_frm.fields_dict && target_frm.fields_dict[fieldname]) {
				target_frm.toggle_display(fieldname, visible);
			}
		} else if (grid_row) {
			// Grid mode
			try {
				grid_row.toggle_display(fieldname, visible);
			} catch (e) {
				try {
					grid_row.set_df_property(fieldname, "hidden", !visible);
				} catch (e2) {
					// Field might not exist yet, ignore
				}
			}
		}
	};
	
	// Helper function to set property - works for both grid and form dialog
	const set_prop = (fieldname, prop, value) => {
		if (is_form_dialog) {
			if (target_frm.fields_dict && target_frm.fields_dict[fieldname]) {
				target_frm.set_df_property(fieldname, prop, value);
			}
		} else if (grid_row) {
			try {
				grid_row.set_df_property(fieldname, prop, value);
			} catch (e) {
				// Field might not exist yet, ignore
			}
		}
	};
	
	// Hide everything first
	[
		"limit_type",
		"min_percentage",
		"max_percentage",
		"sum_limit_type",
		"sum_min_percentage",
		"sum_max_percentage",
		"ratio_section",
		"ratio_value_1",
		"ratio_value_2",
		"ratio_value_3",
		"element_2",
		"element_3",
		"notes"
	].forEach(fieldname => show(fieldname, false));
	
	// Always show element_1, is_mandatory
	show("element_1", true);
	show("is_mandatory", true);
	
	if (!row.condition_type) return;
	
	if (row.condition_type === "Normal Limit") {
		show("limit_type", true);
		
		if (row.limit_type === "Minimum") {
			show("min_percentage", true);
		} else if (row.limit_type === "Maximum") {
			show("max_percentage", true);
		} else if (row.limit_type === "Range") {
			show("min_percentage", true);
			show("max_percentage", true);
		}
		
		// Set read-only for element_2 and element_3
		set_prop("element_2", "read_only", 1);
		set_prop("element_3", "read_only", 1);
		
	} else if (row.condition_type === "Sum Limit") {
		// For 2- or 3-element sums - similar to Normal Limit behavior
		show("element_2", true);
		show("element_3", true);
		show("sum_limit_type", true); // Always show sum_limit_type when Sum Limit is selected
		
		// Show min/max fields based on sum_limit_type selection (similar to Normal Limit)
		if (row.sum_limit_type === "Minimum") {
			show("sum_min_percentage", true);
			show("sum_max_percentage", false);
		} else if (row.sum_limit_type === "Maximum") {
			show("sum_min_percentage", false);
			show("sum_max_percentage", true);
		} else if (row.sum_limit_type === "Range") {
			show("sum_min_percentage", true);
			show("sum_max_percentage", true);
		}
		// If sum_limit_type is not set yet, don't show min/max (user needs to select sum_limit_type first)
		
		// Set mandatory flags
		set_prop("sum_limit_type", "reqd", true);
		if (row.sum_limit_type === "Minimum") {
			set_prop("sum_min_percentage", "reqd", true);
			set_prop("sum_max_percentage", "reqd", false);
		} else if (row.sum_limit_type === "Maximum") {
			set_prop("sum_min_percentage", "reqd", false);
			set_prop("sum_max_percentage", "reqd", true);
		} else if (row.sum_limit_type === "Range") {
			set_prop("sum_min_percentage", "reqd", true);
			set_prop("sum_max_percentage", "reqd", true);
		} else {
			// Reset mandatory flags when sum_limit_type is not selected
			set_prop("sum_min_percentage", "reqd", false);
			set_prop("sum_max_percentage", "reqd", false);
		}
		
		// Set read-only off for element_2 and element_3
		set_prop("element_2", "read_only", 0);
		set_prop("element_3", "read_only", 0);
		
	} else if (row.condition_type === "Ratio") {
		// Ratio is only ratio, no min/max
		show("element_2", true);
		show("element_3", true);
		show("ratio_section", true);
		show("ratio_value_1", true);
		show("ratio_value_2", !!row.element_2);
		show("ratio_value_3", !!row.element_3);
		
		// Set mandatory flags for ratio values
		set_prop("ratio_value_1", "reqd", true);
		set_prop("ratio_value_2", "reqd", !!row.element_2);
		set_prop("ratio_value_3", "reqd", !!row.element_3);
		
		// Set read-only off for element_2 and element_3
		set_prop("element_2", "read_only", 0);
		set_prop("element_3", "read_only", 0);
		
	} else if (row.condition_type === "Remainder") {
		show("min_percentage", true);
		
		// Set read-only for element_2 and element_3
		set_prop("element_2", "read_only", 1);
		set_prop("element_3", "read_only", 1);
		
	} else if (row.condition_type === "Free Text") {
		show("notes", true);
		
		// Set read-only for element_2 and element_3
		set_prop("element_2", "read_only", 1);
		set_prop("element_3", "read_only", 1);
	}
}