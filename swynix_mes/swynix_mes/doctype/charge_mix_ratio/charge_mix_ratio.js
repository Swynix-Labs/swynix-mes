// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on("Charge Mix Ratio", {
	setup(frm) {
		// Filter alloy field to only show items from Alloy item group
		frm.set_query("alloy", function() {
			return {
				filters: {
					item_group: "Alloy"
				}
			};
		});

		// Filter item_group in ingredients based on selected ingredient
		frm.set_query("item_group", "ingredients", function(doc, cdt, cdn) {
			let row = locals[cdt][cdn];
			if (row.ingredient) {
				return {
					query: "swynix_mes.swynix_mes.doctype.charge_mix_ratio.charge_mix_ratio.get_allowed_item_groups_for_ingredient",
					filters: {
						ingredient: row.ingredient
					}
				};
			}
			return {};
		});
	},

	refresh(frm) {
		// Show total percentage summary
		if (frm.doc.ingredients && frm.doc.ingredients.length > 0) {
			calculate_total_percentage(frm);
		}

		// Add button to validate mix
		if (!frm.is_new() && frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Test Validation"), function() {
				test_cmr_validation(frm);
			});
		}
	},

	alloy(frm) {
		// Auto-generate recipe code when alloy changes
		if (frm.doc.alloy && !frm.doc.recipe_code) {
			let revision = frm.doc.revision_no || "01";
			frm.set_value("recipe_code", `CMR-${frm.doc.alloy}-${revision}`);
		}
	}
});

frappe.ui.form.on("Charge Mix Ratio Ingredient", {
	ingredient(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		// Clear item_group when ingredient changes
		frappe.model.set_value(cdt, cdn, "item_group", null);
	},

	exact_pct(frm, cdt, cdn) {
		calculate_total_percentage(frm);
	},

	min_pct(frm, cdt, cdn) {
		calculate_total_percentage(frm);
	},

	max_pct(frm, cdt, cdn) {
		calculate_total_percentage(frm);
	},

	proportion_type(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		// Clear percentage fields when type changes
		if (row.proportion_type === "Exact") {
			frappe.model.set_value(cdt, cdn, "min_pct", null);
			frappe.model.set_value(cdt, cdn, "max_pct", null);
		} else if (row.proportion_type === "Range") {
			frappe.model.set_value(cdt, cdn, "exact_pct", null);
		}
		calculate_total_percentage(frm);
	},

	ingredients_remove(frm) {
		calculate_total_percentage(frm);
	}
});

function calculate_total_percentage(frm) {
	let total_min = 0;
	let total_max = 0;

	(frm.doc.ingredients || []).forEach(row => {
		if (row.proportion_type === "Exact") {
			total_min += row.exact_pct || 0;
			total_max += row.exact_pct || 0;
		} else if (row.proportion_type === "Range") {
			total_min += row.min_pct || 0;
			total_max += row.max_pct || 0;
		}
	});

	// Display summary in dashboard
	let html = `
		<div class="row">
			<div class="col-sm-6">
				<strong>Total Min %:</strong> ${total_min.toFixed(2)}%
			</div>
			<div class="col-sm-6">
				<strong>Total Max %:</strong> ${total_max.toFixed(2)}%
				${total_max > 100 ? '<span class="text-danger"> (Exceeds 100%!)</span>' : ''}
			</div>
		</div>
	`;

	if (!frm.dashboard.data.percentage_summary) {
		frm.dashboard.add_section(html, __("Percentage Summary"));
		frm.dashboard.data.percentage_summary = true;
	} else {
		frm.dashboard.set_headline(html);
	}
}

function test_cmr_validation(frm) {
	// Dialog to test validation
	let d = new frappe.ui.Dialog({
		title: __("Test Charge Mix Validation"),
		fields: [
			{
				label: __("Test Ingredients JSON"),
				fieldname: "ingredients_json",
				fieldtype: "Code",
				options: "JSON",
				reqd: 1,
				default: JSON.stringify([
					{"ingredient": "", "item_group": "", "pct": 0}
				], null, 2)
			}
		],
		primary_action_label: __("Validate"),
		primary_action(values) {
			frappe.call({
				method: "swynix_mes.swynix_mes.doctype.charge_mix_ratio.charge_mix_ratio.validate_charge_mix",
				args: {
					alloy: frm.doc.alloy,
					ingredients_json: values.ingredients_json
				},
				callback(r) {
					if (r.message) {
						let result = r.message;
						let msg = `<strong>Valid:</strong> ${result.valid ? 'Yes' : 'No'}<br><br>`;

						if (result.errors.length > 0) {
							msg += `<strong>Errors:</strong><ul>${result.errors.map(e => `<li>${e}</li>`).join('')}</ul>`;
						}

						if (result.warnings.length > 0) {
							msg += `<strong>Warnings:</strong><ul>${result.warnings.map(w => `<li>${w}</li>`).join('')}</ul>`;
						}

						frappe.msgprint({
							title: __("Validation Result"),
							indicator: result.valid ? "green" : "red",
							message: msg
						});
					}
				}
			});
			d.hide();
		}
	});
	d.show();
}








