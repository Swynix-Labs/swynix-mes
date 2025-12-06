// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on("Melting Batch", {
	setup(frm) {
		// Filter furnace to only show Foundry workstations
		frm.set_query("furnace", function() {
			return {
				query: "swynix_mes.swynix_mes.doctype.melting_batch.melting_batch.get_foundry_workstations"
			};
		});

		// Filter alloy to only show items from Alloy item group
		frm.set_query("alloy", function() {
			return {
				query: "swynix_mes.swynix_mes.doctype.melting_batch.melting_batch.get_alloy_items"
			};
		});

		// Filter product_item to only show items from Product item group
		frm.set_query("product_item", function() {
			return {
				query: "swynix_mes.swynix_mes.doctype.melting_batch.melting_batch.get_product_items"
			};
		});

		// Filter charge_mix_ratio based on selected alloy
		frm.set_query("charge_mix_ratio", function() {
			return {
				query: "swynix_mes.swynix_mes.doctype.melting_batch.melting_batch.get_charge_mix_for_alloy",
				filters: {
					alloy: frm.doc.alloy
				}
			};
		});
	},

	refresh(frm) {
		// Set melting_batch_id from name if empty
		if (frm.doc.name && !frm.doc.melting_batch_id) {
			frm.set_value("melting_batch_id", frm.doc.name);
		}

		// Add status action buttons based on current status
		if (!frm.is_new() && frm.doc.docstatus === 0) {
			add_status_buttons(frm);
		}

		// Show weight summary
		if (frm.doc.raw_materials && frm.doc.raw_materials.length > 0) {
			show_weight_summary(frm);
		}

		// Show status indicator
		show_status_indicator(frm);
	},

	alloy(frm) {
		// Clear charge_mix_ratio when alloy changes
		if (frm.doc.charge_mix_ratio) {
			// Verify the recipe is for the selected alloy
			frappe.db.get_value("Charge Mix Ratio", frm.doc.charge_mix_ratio, "alloy", (r) => {
				if (r && r.alloy !== frm.doc.alloy) {
					frm.set_value("charge_mix_ratio", null);
					frappe.show_alert({
						message: __("Charge Mix Ratio cleared as it doesn't match the selected Alloy"),
						indicator: "orange"
					});
				}
			});
		}
	},

	tapped_weight_mt(frm) {
		calculate_yield(frm);
	}
});

frappe.ui.form.on("Melting Batch Raw Material", {
	qty_kg(frm, cdt, cdn) {
		calculate_charged_weight(frm);
	},

	raw_materials_add(frm, cdt, cdn) {
		// Auto-set row_index
		let row = locals[cdt][cdn];
		row.row_index = frm.doc.raw_materials.length;
		frm.refresh_field("raw_materials");
	},

	raw_materials_remove(frm) {
		calculate_charged_weight(frm);
		// Re-sequence row_index
		(frm.doc.raw_materials || []).forEach((row, idx) => {
			row.row_index = idx + 1;
		});
		frm.refresh_field("raw_materials");
	},

	item_code(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.item_code) {
			frappe.db.get_value("Item", row.item_code, "item_name", (r) => {
				if (r) {
					frappe.model.set_value(cdt, cdn, "item_name", r.item_name);
				}
			});
		}
	}
});

function calculate_charged_weight(frm) {
	let total_kg = 0;
	(frm.doc.raw_materials || []).forEach(row => {
		total_kg += flt(row.qty_kg);
	});
	
	frm.set_value("charged_weight_mt", flt(total_kg / 1000, 3));
	calculate_yield(frm);
}

function calculate_yield(frm) {
	if (flt(frm.doc.tapped_weight_mt) > 0 && flt(frm.doc.charged_weight_mt) > 0) {
		let yield_pct = (flt(frm.doc.tapped_weight_mt) / flt(frm.doc.charged_weight_mt)) * 100;
		frm.set_value("yield_percent", flt(yield_pct, 2));
	} else {
		frm.set_value("yield_percent", 0);
	}
}

function show_weight_summary(frm) {
	let total_kg = 0;
	let correction_kg = 0;
	
	(frm.doc.raw_materials || []).forEach(row => {
		total_kg += flt(row.qty_kg);
		if (row.is_correction) {
			correction_kg += flt(row.qty_kg);
		}
	});

	let html = `
		<div class="row">
			<div class="col-sm-4">
				<strong>${__("Total Charged")}:</strong> ${flt(total_kg, 3)} kg (${flt(total_kg/1000, 3)} MT)
			</div>
			<div class="col-sm-4">
				<strong>${__("Correction Charges")}:</strong> ${flt(correction_kg, 3)} kg
			</div>
			<div class="col-sm-4">
				<strong>${__("Yield")}:</strong> ${flt(frm.doc.yield_percent, 2)}%
				${frm.doc.yield_percent > 0 && frm.doc.yield_percent < 90 ? '<span class="text-warning"> (Low)</span>' : ''}
				${frm.doc.yield_percent >= 98 ? '<span class="text-success"> (Excellent)</span>' : ''}
			</div>
		</div>
	`;

	frm.dashboard.add_section(html, __("Weight Summary"));
}

function show_status_indicator(frm) {
	const status_colors = {
		"Draft": "grey",
		"Charging": "blue",
		"Melting": "orange",
		"Ready for Transfer": "yellow",
		"Transferred": "green",
		"Cancelled": "red"
	};

	let color = status_colors[frm.doc.status] || "grey";
	frm.page.set_indicator(frm.doc.status, color);
}

function add_status_buttons(frm) {
	const status = frm.doc.status;

	if (status === "Draft") {
		frm.add_custom_button(__("Start Charging"), function() {
			frm.call("start_charging").then(r => {
				if (r.message) {
					frm.reload_doc();
					frappe.show_alert({message: __("Charging started"), indicator: "blue"});
				}
			});
		}, __("Actions"));
	}

	if (status === "Charging") {
		frm.add_custom_button(__("Start Melting"), function() {
			frm.call("start_melting").then(r => {
				if (r.message) {
					frm.reload_doc();
					frappe.show_alert({message: __("Melting started"), indicator: "orange"});
				}
			});
		}, __("Actions"));
	}

	if (status === "Melting") {
		frm.add_custom_button(__("Ready for Transfer"), function() {
			frm.call("mark_ready_for_transfer").then(r => {
				if (r.message) {
					frm.reload_doc();
					frappe.show_alert({message: __("Marked ready for transfer"), indicator: "yellow"});
				}
			});
		}, __("Actions"));
	}

	if (status === "Ready for Transfer") {
		frm.add_custom_button(__("Start Transfer"), function() {
			frm.call("start_transfer").then(r => {
				if (r.message) {
					frm.reload_doc();
					frappe.show_alert({message: __("Transfer started"), indicator: "blue"});
				}
			});
		}, __("Actions"));

		frm.add_custom_button(__("Complete Transfer"), function() {
			frm.call("complete_transfer").then(r => {
				if (r.message) {
					frm.reload_doc();
					frappe.show_alert({message: __("Transfer completed"), indicator: "green"});
				}
			});
		}, __("Actions"));
	}

	// Cancel button for non-terminal states
	if (!["Transferred", "Cancelled"].includes(status)) {
		frm.add_custom_button(__("Cancel Batch"), function() {
			frappe.confirm(
				__("Are you sure you want to cancel this Melting Batch?"),
				function() {
					frm.set_value("status", "Cancelled");
					frm.save();
				}
			);
		}, __("Actions"));
	}

	// Reopen from Cancelled
	if (status === "Cancelled") {
		frm.add_custom_button(__("Reopen as Draft"), function() {
			frm.set_value("status", "Draft");
			frm.save();
		}, __("Actions"));
	}
}
