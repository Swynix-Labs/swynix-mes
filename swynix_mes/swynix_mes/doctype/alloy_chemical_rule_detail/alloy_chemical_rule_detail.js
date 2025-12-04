// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

// This script handles the form dialog when editing a child table row
frappe.ui.form.on("Alloy Chemical Rule Detail", {
	refresh(frm) {
		// Set filters for element fields
		frm.set_query("element_1", function() {
			return {
				filters: {
					item_group: "Chemicals for Composition"
				}
			};
		});
		
		frm.set_query("element_2", function() {
			return {
				filters: {
					item_group: "Chemicals for Composition"
				}
			};
		});
		
		frm.set_query("element_3", function() {
			return {
				filters: {
					item_group: "Chemicals for Composition"
				}
			};
		});
		
		// Initialize field visibility
		toggle_fields_for_dialog(frm);
	},
	
	condition_type(frm) {
		clear_fields_for_condition_type_dialog(frm);
		toggle_fields_for_dialog(frm);
	},
	
	limit_type(frm) {
		if (frm.doc.limit_type === "Minimum") {
			frm.set_value("max_percentage", "");
		} else if (frm.doc.limit_type === "Maximum") {
			frm.set_value("min_percentage", "");
		}
		toggle_fields_for_dialog(frm);
	},
	
	sum_limit_type(frm) {
		if (frm.doc.sum_limit_type === "Minimum") {
			frm.set_value("sum_max_percentage", "");
		} else if (frm.doc.sum_limit_type === "Maximum") {
			frm.set_value("sum_min_percentage", "");
		}
		toggle_fields_for_dialog(frm);
	},
	
	element_2(frm) {
		toggle_fields_for_dialog(frm);
	},
	
	element_3(frm) {
		toggle_fields_for_dialog(frm);
	}
});

function clear_fields_for_condition_type_dialog(frm) {
	if (frm.doc.condition_type !== "Normal Limit") {
		frm.set_value("limit_type", "");
		frm.set_value("min_percentage", "");
		frm.set_value("max_percentage", "");
	}
	
	if (frm.doc.condition_type !== "Sum Limit") {
		frm.set_value("sum_limit_type", "");
		frm.set_value("sum_min_percentage", "");
		frm.set_value("sum_max_percentage", "");
	}
	
	if (frm.doc.condition_type !== "Ratio") {
		frm.set_value("ratio_value_1", "");
		frm.set_value("ratio_value_2", "");
		frm.set_value("ratio_value_3", "");
	}
	
	if (frm.doc.condition_type === "Normal Limit" || frm.doc.condition_type === "Remainder" || frm.doc.condition_type === "Free Text") {
		frm.set_value("element_2", "");
		frm.set_value("element_3", "");
	}
}

function toggle_fields_for_dialog(frm) {
	if (!frm.doc.condition_type) return;
	
	// Hide everything first
	const fields_to_hide = [
		"limit_type", "min_percentage", "max_percentage",
		"sum_limit_type", "sum_min_percentage", "sum_max_percentage",
		"ratio_section", "ratio_value_1", "ratio_value_2", "ratio_value_3",
		"element_2", "element_3", "notes"
	];
	
	fields_to_hide.forEach(fieldname => {
		if (frm.fields_dict[fieldname]) {
			frm.toggle_display(fieldname, false);
		}
	});
	
	// Always show element_1 and is_mandatory
	frm.toggle_display("element_1", true);
	frm.toggle_display("is_mandatory", true);
	
	if (frm.doc.condition_type === "Normal Limit") {
		frm.toggle_display("limit_type", true);
		
		if (frm.doc.limit_type === "Minimum") {
			frm.toggle_display("min_percentage", true);
		} else if (frm.doc.limit_type === "Maximum") {
			frm.toggle_display("max_percentage", true);
		} else if (frm.doc.limit_type === "Range") {
			frm.toggle_display("min_percentage", true);
			frm.toggle_display("max_percentage", true);
		}
		
		frm.set_df_property("element_2", "read_only", 1);
		frm.set_df_property("element_3", "read_only", 1);
		
	} else if (frm.doc.condition_type === "Sum Limit") {
		frm.toggle_display("element_2", true);
		frm.toggle_display("element_3", true);
		frm.toggle_display("sum_limit_type", true); // Always show sum_limit_type
		
		if (frm.doc.sum_limit_type === "Minimum") {
			frm.toggle_display("sum_min_percentage", true);
			frm.toggle_display("sum_max_percentage", false);
		} else if (frm.doc.sum_limit_type === "Maximum") {
			frm.toggle_display("sum_min_percentage", false);
			frm.toggle_display("sum_max_percentage", true);
		} else if (frm.doc.sum_limit_type === "Range") {
			frm.toggle_display("sum_min_percentage", true);
			frm.toggle_display("sum_max_percentage", true);
		}
		
		frm.set_df_property("sum_limit_type", "reqd", true);
		if (frm.doc.sum_limit_type === "Minimum") {
			frm.set_df_property("sum_min_percentage", "reqd", true);
			frm.set_df_property("sum_max_percentage", "reqd", false);
		} else if (frm.doc.sum_limit_type === "Maximum") {
			frm.set_df_property("sum_min_percentage", "reqd", false);
			frm.set_df_property("sum_max_percentage", "reqd", true);
		} else if (frm.doc.sum_limit_type === "Range") {
			frm.set_df_property("sum_min_percentage", "reqd", true);
			frm.set_df_property("sum_max_percentage", "reqd", true);
		}
		
		frm.set_df_property("element_2", "read_only", 0);
		frm.set_df_property("element_3", "read_only", 0);
		
	} else if (frm.doc.condition_type === "Ratio") {
		frm.toggle_display("element_2", true);
		frm.toggle_display("element_3", true);
		frm.toggle_display("ratio_section", true);
		frm.toggle_display("ratio_value_1", true);
		frm.toggle_display("ratio_value_2", !!frm.doc.element_2);
		frm.toggle_display("ratio_value_3", !!frm.doc.element_3);
		
		frm.set_df_property("ratio_value_1", "reqd", true);
		frm.set_df_property("ratio_value_2", "reqd", !!frm.doc.element_2);
		frm.set_df_property("ratio_value_3", "reqd", !!frm.doc.element_3);
		
		frm.set_df_property("element_2", "read_only", 0);
		frm.set_df_property("element_3", "read_only", 0);
		
	} else if (frm.doc.condition_type === "Remainder") {
		frm.toggle_display("min_percentage", true);
		frm.set_df_property("element_2", "read_only", 1);
		frm.set_df_property("element_3", "read_only", 1);
		
	} else if (frm.doc.condition_type === "Free Text") {
		frm.toggle_display("notes", true);
		frm.set_df_property("element_2", "read_only", 1);
		frm.set_df_property("element_3", "read_only", 1);
	}
}
