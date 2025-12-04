// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on("Alloy Chemical Composition Master", {
	setup(frm) {
		// Set query filter for alloy field - filter by Item Group
		frm.set_query("alloy", function () {
			return {
				filters: {
					item_group: "Alloy"
				}
			};
		});

		// Set query filter for element fields in child table
		frm.set_query("element_1", "composition_rules", function () {
			return {
				filters: {
					item_group: "Chemicals for Composition"
				}
			};
		});

		frm.set_query("element_2", "composition_rules", function () {
			return {
				filters: {
					item_group: "Chemicals for Composition"
				}
			};
		});

		frm.set_query("element_3", "composition_rules", function () {
			return {
				filters: {
					item_group: "Chemicals for Composition"
				}
			};
		});
	},

	refresh(frm) {
		// Apply field visibility for all existing rows on refresh
		apply_all_rows_visibility(frm);

		// Add custom button to copy from existing master
		if (!frm.is_new()) {
			frm.add_custom_button(__("Copy Rules from Another Alloy"), function () {
				copy_rules_from_another_alloy(frm);
			});
		}
	},

	onload(frm) {
		// Apply visibility on load
		apply_all_rows_visibility(frm);
	}
});

frappe.ui.form.on("Alloy Chemical Rule Detail", {
	form_render(frm, cdt, cdn) {
		// Apply field visibility when form popup opens
		let row = locals[cdt][cdn];
		// Multiple attempts with increasing delays to ensure DOM is ready
		[50, 100, 200].forEach(delay => {
			setTimeout(() => {
				toggle_child_fields(frm, cdn, row);
			}, delay);
		});
	},

	condition_type(frm, cdt, cdn) {
		let row = locals[cdt][cdn];

		// Clear irrelevant fields when condition type changes
		clear_fields_for_condition_type(row);

		// Toggle field visibility with small delay for DOM update
		setTimeout(() => {
			toggle_child_fields(frm, cdn, row);
		}, 50);
		
		frm.refresh_field("composition_rules");
	},

	limit_type(frm, cdt, cdn) {
		let row = locals[cdt][cdn];

		// Clear min/max based on new limit type
		if (row.limit_type === "Minimum" || row.limit_type === "Equal To") {
			frappe.model.set_value(cdt, cdn, "max_percentage", null);
		} else if (row.limit_type === "Maximum") {
			frappe.model.set_value(cdt, cdn, "min_percentage", null);
		}

		// Toggle field visibility
		setTimeout(() => {
			toggle_child_fields(frm, cdn, row);
		}, 50);
	},

	sum_limit_type(frm, cdt, cdn) {
		let row = locals[cdt][cdn];

		// Clear sum min/max based on new sum limit type
		if (row.sum_limit_type === "Minimum" || row.sum_limit_type === "Equal To") {
			frappe.model.set_value(cdt, cdn, "sum_max_percentage", null);
		} else if (row.sum_limit_type === "Maximum") {
			frappe.model.set_value(cdt, cdn, "sum_min_percentage", null);
		}

		// Toggle field visibility
		setTimeout(() => {
			toggle_child_fields(frm, cdn, row);
		}, 50);
	},

	element_2(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		setTimeout(() => {
			toggle_child_fields(frm, cdn, row);
		}, 50);
	},

	element_3(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		setTimeout(() => {
			toggle_child_fields(frm, cdn, row);
		}, 50);
	},

	composition_rules_add(frm, cdt, cdn) {
		// Set default values for new row
		frappe.model.set_value(cdt, cdn, "condition_type", "Normal Limit");
		frappe.model.set_value(cdt, cdn, "is_mandatory", 1);

		// Apply grid column visibility
		setTimeout(() => {
			apply_grid_column_visibility(frm);
		}, 100);
	}
});

function apply_all_rows_visibility(frm) {
	// Apply grid column visibility based on what data exists
	apply_grid_column_visibility(frm);
}

function apply_grid_column_visibility(frm) {
	let grid = frm.fields_dict.composition_rules.grid;

	// Determine which columns to show based on existing data
	let has_sum_limit = false;
	let has_ratio = false;
	let has_multi_element = false;

	if (frm.doc.composition_rules) {
		frm.doc.composition_rules.forEach(function (row) {
			if (row.condition_type === "Sum Limit") has_sum_limit = true;
			if (row.condition_type === "Ratio") has_ratio = true;
			if (row.element_2 || row.element_3) has_multi_element = true;
		});
	}

	// Toggle grid columns - show element_2 if any multi-element rules exist
	grid.toggle_display("element_2", has_multi_element || has_sum_limit || has_ratio);
	grid.toggle_display("element_3", false); // Usually hidden in grid, visible in form

	// Toggle limit type - always visible as it's commonly used
	grid.toggle_display("limit_type", true);
	grid.toggle_display("min_percentage", true);
	grid.toggle_display("max_percentage", true);

	grid.refresh();
}

function toggle_child_fields(frm, cdn, row) {
	// Get the grid
	let grid = frm.fields_dict.composition_rules.grid;
	let grid_row = grid.get_row(cdn);
	if (!grid_row) return;

	let condition_type = row.condition_type || "Normal Limit";
	let limit_type = row.limit_type || "";
	let sum_limit_type = row.sum_limit_type || "";

	// Check if multi-element rule
	let is_multi_element = (condition_type === "Sum Limit" || condition_type === "Ratio");

	// Helper to toggle field visibility
	function toggle_field(fieldname, visible) {
		// Update the docfield property to control visibility
		grid.update_docfield_property(fieldname, 'hidden', visible ? 0 : 1);
		
		// If grid_form is open, also directly toggle the DOM element
		if (grid_row.grid_form && grid_row.grid_form.fields_dict) {
			let field = grid_row.grid_form.fields_dict[fieldname];
			if (field) {
				if (field.$wrapper) {
					field.$wrapper.toggle(visible);
				}
				if (field.df) {
					field.df.hidden = visible ? 0 : 1;
				}
			}
		}
	}

	// Element fields - show element_2 and element_3 for Sum Limit or Ratio
	toggle_field("element_2", is_multi_element);
	toggle_field("element_3", is_multi_element);
	
	// Force refresh element fields visibility in DOM
	if (grid_row.grid_form) {
		let $form = $(grid_row.grid_form.wrapper);
		$form.find('[data-fieldname="element_2"]').closest('.frappe-control').toggle(is_multi_element);
		$form.find('[data-fieldname="element_3"]').closest('.frappe-control').toggle(is_multi_element);
	}

	// Normal Limit section and fields
	toggle_field("normal_limit_section", condition_type === "Normal Limit");
	toggle_field("limit_type", condition_type === "Normal Limit");
	toggle_field("min_percentage", condition_type === "Normal Limit" && (limit_type === "Minimum" || limit_type === "Equal To" || limit_type === "Range"));
	toggle_field("max_percentage", condition_type === "Normal Limit" && (limit_type === "Maximum" || limit_type === "Range"));

	// Sum Limit section and fields
	toggle_field("sum_limit_section", condition_type === "Sum Limit");
	toggle_field("sum_limit_type", condition_type === "Sum Limit");
	toggle_field("sum_min_percentage", condition_type === "Sum Limit" && (sum_limit_type === "Minimum" || sum_limit_type === "Equal To" || sum_limit_type === "Range"));
	toggle_field("sum_max_percentage", condition_type === "Sum Limit" && (sum_limit_type === "Maximum" || sum_limit_type === "Range"));

	// Ratio section and fields
	toggle_field("ratio_section", condition_type === "Ratio");
	toggle_field("ratio_value_1", condition_type === "Ratio");
	toggle_field("ratio_value_2", condition_type === "Ratio" && row.element_2);
	toggle_field("ratio_value_3", condition_type === "Ratio" && row.element_3);

	// Remainder section and fields
	toggle_field("remainder_section", condition_type === "Remainder");
	toggle_field("remainder_min_percentage", condition_type === "Remainder");

	// Notes section and field
	toggle_field("notes_section", condition_type === "Free Text" || condition_type === "Remainder");
	toggle_field("notes", condition_type === "Free Text" || condition_type === "Remainder");
}

function clear_fields_for_condition_type(row) {
	let condition_type = row.condition_type;
	let cdt = row.doctype;
	let cdn = row.name;

	// Clear fields based on condition type
	if (condition_type === "Normal Limit") {
		// Clear sum limit, ratio, remainder, and extra elements
		frappe.model.set_value(cdt, cdn, "element_2", null);
		frappe.model.set_value(cdt, cdn, "element_3", null);
		frappe.model.set_value(cdt, cdn, "sum_limit_type", null);
		frappe.model.set_value(cdt, cdn, "sum_min_percentage", null);
		frappe.model.set_value(cdt, cdn, "sum_max_percentage", null);
		frappe.model.set_value(cdt, cdn, "ratio_value_1", null);
		frappe.model.set_value(cdt, cdn, "ratio_value_2", null);
		frappe.model.set_value(cdt, cdn, "ratio_value_3", null);
		frappe.model.set_value(cdt, cdn, "remainder_min_percentage", null);
		frappe.model.set_value(cdt, cdn, "notes", null);
	} else if (condition_type === "Sum Limit") {
		// Clear normal limit, ratio, remainder
		frappe.model.set_value(cdt, cdn, "limit_type", null);
		frappe.model.set_value(cdt, cdn, "min_percentage", null);
		frappe.model.set_value(cdt, cdn, "max_percentage", null);
		frappe.model.set_value(cdt, cdn, "ratio_value_1", null);
		frappe.model.set_value(cdt, cdn, "ratio_value_2", null);
		frappe.model.set_value(cdt, cdn, "ratio_value_3", null);
		frappe.model.set_value(cdt, cdn, "remainder_min_percentage", null);
		frappe.model.set_value(cdt, cdn, "notes", null);
	} else if (condition_type === "Ratio") {
		// Clear normal limit, sum limit, remainder
		frappe.model.set_value(cdt, cdn, "limit_type", null);
		frappe.model.set_value(cdt, cdn, "min_percentage", null);
		frappe.model.set_value(cdt, cdn, "max_percentage", null);
		frappe.model.set_value(cdt, cdn, "sum_limit_type", null);
		frappe.model.set_value(cdt, cdn, "sum_min_percentage", null);
		frappe.model.set_value(cdt, cdn, "sum_max_percentage", null);
		frappe.model.set_value(cdt, cdn, "remainder_min_percentage", null);
		frappe.model.set_value(cdt, cdn, "notes", null);
	} else if (condition_type === "Remainder") {
		// Clear all except element_1, remainder_min_percentage, and notes
		frappe.model.set_value(cdt, cdn, "element_2", null);
		frappe.model.set_value(cdt, cdn, "element_3", null);
		frappe.model.set_value(cdt, cdn, "limit_type", null);
		frappe.model.set_value(cdt, cdn, "min_percentage", null);
		frappe.model.set_value(cdt, cdn, "max_percentage", null);
		frappe.model.set_value(cdt, cdn, "sum_limit_type", null);
		frappe.model.set_value(cdt, cdn, "sum_min_percentage", null);
		frappe.model.set_value(cdt, cdn, "sum_max_percentage", null);
		frappe.model.set_value(cdt, cdn, "ratio_value_1", null);
		frappe.model.set_value(cdt, cdn, "ratio_value_2", null);
		frappe.model.set_value(cdt, cdn, "ratio_value_3", null);
	} else if (condition_type === "Free Text") {
		// Clear all numeric fields and extra elements
		frappe.model.set_value(cdt, cdn, "element_2", null);
		frappe.model.set_value(cdt, cdn, "element_3", null);
		frappe.model.set_value(cdt, cdn, "limit_type", null);
		frappe.model.set_value(cdt, cdn, "min_percentage", null);
		frappe.model.set_value(cdt, cdn, "max_percentage", null);
		frappe.model.set_value(cdt, cdn, "sum_limit_type", null);
		frappe.model.set_value(cdt, cdn, "sum_min_percentage", null);
		frappe.model.set_value(cdt, cdn, "sum_max_percentage", null);
		frappe.model.set_value(cdt, cdn, "ratio_value_1", null);
		frappe.model.set_value(cdt, cdn, "ratio_value_2", null);
		frappe.model.set_value(cdt, cdn, "ratio_value_3", null);
		frappe.model.set_value(cdt, cdn, "remainder_min_percentage", null);
	}
}

function copy_rules_from_another_alloy(frm) {
	// Dialog to select source alloy master
	let d = new frappe.ui.Dialog({
		title: __("Copy Rules from Another Alloy"),
		fields: [
			{
				label: __("Source Master"),
				fieldname: "source_master",
				fieldtype: "Link",
				options: "Alloy Chemical Composition Master",
				reqd: 1,
				get_query: function () {
					return {
						filters: {
							name: ["!=", frm.doc.name],
							is_active: 1
						}
					};
				}
			}
		],
		primary_action_label: __("Copy"),
		primary_action: function (values) {
			frappe.call({
				method: "frappe.client.get",
				args: {
					doctype: "Alloy Chemical Composition Master",
					name: values.source_master
				},
				callback: function (r) {
					if (r.message) {
						let source = r.message;

						// Clear existing rules
						frm.clear_table("composition_rules");

						// Copy rules from source
						source.composition_rules.forEach(function (rule) {
							let new_row = frm.add_child("composition_rules");
							new_row.element_1 = rule.element_1;
							new_row.element_2 = rule.element_2;
							new_row.element_3 = rule.element_3;
							new_row.condition_type = rule.condition_type;
							new_row.is_mandatory = rule.is_mandatory;
							new_row.limit_type = rule.limit_type;
							new_row.min_percentage = rule.min_percentage;
							new_row.max_percentage = rule.max_percentage;
							new_row.sum_limit_type = rule.sum_limit_type;
							new_row.sum_min_percentage = rule.sum_min_percentage;
							new_row.sum_max_percentage = rule.sum_max_percentage;
							new_row.ratio_value_1 = rule.ratio_value_1;
							new_row.ratio_value_2 = rule.ratio_value_2;
							new_row.ratio_value_3 = rule.ratio_value_3;
							new_row.remainder_min_percentage = rule.remainder_min_percentage;
							new_row.notes = rule.notes;
						});

						frm.refresh_field("composition_rules");
						apply_all_rows_visibility(frm);

						frappe.show_alert({
							message: __("Copied {0} rules from {1}", [source.composition_rules.length, values.source_master]),
							indicator: "green"
						});
					}
				}
			});

			d.hide();
		}
	});

	d.show();
}
