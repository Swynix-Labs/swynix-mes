// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on("PPC Casting Plan", {
	setup(frm) {
		// Filter caster: only Workstations with workstation_type = 'Casting'
		frm.set_query("casting_workstation", function() {
			return {
				filters: {
					workstation_type: "Casting"
				}
			};
		});

		// Filter furnace: only Workstations with workstation_type = 'Foundry'
		frm.set_query("furnace", function() {
			return {
				filters: {
					workstation_type: "Foundry"
				}
			};
		});

		// Filter alloy to show only items in Alloy item group
		frm.set_query("alloy", function() {
			return {
				filters: {
					item_group: "Alloy"
				}
			};
		});

		// Filter product_item to show only items in Product item group
		frm.set_query("product_item", function() {
			return {
				filters: {
					item_group: "Product"
				}
			};
		});

			let filters = {
				is_active: 1,
				docstatus: 1
			};
			if (frm.doc.alloy) {
				filters.alloy = frm.doc.alloy;
			}
			return { filters: filters };
		});

		// Filter so_item in child table by selected sales_order
		frm.set_query("so_item", "sales_orders", function(doc, cdt, cdn) {
			let row = locals[cdt][cdn];
			if (row.sales_order) {
				return {
					query: "swynix_mes.swynix_mes.doctype.ppc_casting_plan.ppc_casting_plan.get_so_items_for_order",
					filters: {
						sales_order: row.sales_order
					}
				};
			}
			return {};
		});
	},

	refresh(frm) {
		// Show/hide sections based on plan_type
		toggle_sections(frm);

		// Calculate and display duration
		calculate_duration(frm);

		// Show status indicator
		if (frm.doc.status) {
			let indicator = get_status_indicator(frm.doc.status);
			frm.page.set_indicator(frm.doc.status, indicator);
		}

		// Add custom buttons
		if (!frm.is_new() && frm.doc.docstatus === 0) {
			if (frm.doc.status === "Draft") {
				frm.add_custom_button(__("Mark as Planned"), function() {
					frm.set_value("status", "Planned");
					frm.save();
				}, __("Status"));
			}
			if (frm.doc.status === "Planned") {
				frm.add_custom_button(__("Release to Melting"), function() {
					frm.set_value("status", "Released to Melting");
					frm.save();
				}, __("Status"));
			}
		}

		// Show linked documents
		if (frm.doc.melting_batch) {
			frm.add_custom_button(__("View Melting Batch"), function() {
				frappe.set_route("Form", "Melting Batch", frm.doc.melting_batch);
			}, __("Links"));
		}
	},

	plan_type(frm) {
		toggle_sections(frm);

		// Clear casting-specific fields when switching to Downtime
		if (frm.doc.plan_type === "Downtime") {
			frm.set_value("product_item", null);
			frm.set_value("width_mm", null);
			frm.set_value("alloy", null);
			frm.set_value("temper", null);
			frm.set_value("final_gauge_mm", null);
			frm.set_value("planned_weight_mt", null);
			frm.set_value("customer", null);
			frm.clear_table("sales_orders");
			frm.refresh_field("sales_orders");
		}
		// Clear downtime-specific fields when switching to Casting
		else if (frm.doc.plan_type === "Casting") {
			frm.set_value("downtime_type", null);
			frm.set_value("downtime_reason", null);
		}
	},

	start_datetime(frm) {
		calculate_duration(frm);
		// Auto-set plan_date
		if (frm.doc.start_datetime && !frm.doc.plan_date) {
			frm.set_value("plan_date", frappe.datetime.get_datetime_as_string(frm.doc.start_datetime).split(" ")[0]);
		}
	},

	end_datetime(frm) {
		calculate_duration(frm);
	},

	product_item(frm) {
		// Auto-fetch product details (if custom fields exist on Item)
		if (frm.doc.product_item) {
			frappe.db.get_value("Item", frm.doc.product_item, 
				["custom_width_mm", "custom_gauge_mm", "custom_temper", "custom_alloy"], 
				function(r) {
					if (r) {
						if (r.custom_width_mm && !frm.doc.width_mm) {
							frm.set_value("width_mm", r.custom_width_mm);
						}
						if (r.custom_gauge_mm && !frm.doc.final_gauge_mm) {
							frm.set_value("final_gauge_mm", r.custom_gauge_mm);
						}
						if (r.custom_temper && !frm.doc.temper) {
							frm.set_value("temper", r.custom_temper);
						}
						if (r.custom_alloy && !frm.doc.alloy) {
							frm.set_value("alloy", r.custom_alloy);
						}
					}
				}
			);
		}
	},

	alloy(frm) {
		if (!frm.doc.alloy) {
		}
			let filters = {
				is_active: 1,
				docstatus: 1
			};
			if (frm.doc.alloy) {
				filters.alloy = frm.doc.alloy;
			}
			return { filters: filters };
		});
	}
});

frappe.ui.form.on("PPC Casting Plan SO", {
	sales_order(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		// Clear so_item when sales_order changes
		frappe.model.set_value(cdt, cdn, "so_item", null);
		frappe.model.set_value(cdt, cdn, "item_code", null);

		// Auto-fetch customer
		if (row.sales_order) {
			frappe.db.get_value("Sales Order", row.sales_order, "customer", function(r) {
				if (r && r.customer) {
					frappe.model.set_value(cdt, cdn, "customer", r.customer);
				}
			});
		}
	},

	so_item(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		// Auto-fetch item_code from SO Item
		if (row.so_item) {
			frappe.db.get_value("Sales Order Item", row.so_item, "item_code", function(r) {
				if (r && r.item_code) {
					frappe.model.set_value(cdt, cdn, "item_code", r.item_code);
				}
			});
		}
	}
});

function toggle_sections(frm) {
	// Toggle visibility based on plan_type
	let is_casting = frm.doc.plan_type === "Casting";
	let is_downtime = frm.doc.plan_type === "Downtime";

	// Casting Details section
	frm.toggle_display("casting_details_section", is_casting);
	frm.toggle_display("product_item", is_casting);
	frm.toggle_display("width_mm", is_casting);
	frm.toggle_display("alloy", is_casting);
	frm.toggle_display("temper", is_casting);
	frm.toggle_display("final_gauge_mm", is_casting);
	frm.toggle_display("planned_weight_mt", is_casting);

	// Customer section
	frm.toggle_display("customer_section", is_casting);
	frm.toggle_display("customer", is_casting);
	frm.toggle_display("sales_orders", is_casting);

	// Downtime Details section
	frm.toggle_display("downtime_section", is_downtime);
	frm.toggle_display("downtime_type", is_downtime);
	frm.toggle_display("downtime_reason", is_downtime);
}

function calculate_duration(frm) {
	if (frm.doc.start_datetime && frm.doc.end_datetime) {
		let start = frappe.datetime.str_to_obj(frm.doc.start_datetime);
		let end = frappe.datetime.str_to_obj(frm.doc.end_datetime);
		let diff_ms = end - start;
		let diff_minutes = Math.floor(diff_ms / 60000);

		if (diff_minutes > 0) {
			frm.set_value("duration_minutes", diff_minutes);

			// Display formatted duration
			let hours = Math.floor(diff_minutes / 60);
			let mins = diff_minutes % 60;
			let duration_str = hours > 0 ? `${hours}h ${mins}m` : `${mins}m`;
			frm.dashboard.set_headline(__("Duration: {0}", [duration_str]));
		}
	}
}

function get_status_indicator(status) {
	const indicators = {
		"Draft": "orange",
		"Planned": "blue",
		"Released to Melting": "purple",
		"In Process": "yellow",
		"Completed": "green",
		"Cancelled": "red"
	};
	return indicators[status] || "grey";
}

