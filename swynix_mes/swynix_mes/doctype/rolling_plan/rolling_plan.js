// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on("Rolling Plan", {
	refresh(frm) {
		// Hide Update button if document is submitted
		if (frm.doc.docstatus === 1) {
			frm.page.clear_primary_action();
		}
		
		set_coil_query(frm);
		update_pass_count(frm);

		if (!frm.doc.rolling_plan_id) {
			frm.add_custom_button(__("Generate Plan ID"), () => {
				generate_rolling_plan_id(frm);
			});
		}
	},

	onload(frm) {
		set_coil_query(frm);
	},

	coil(frm) {
		if (!frm.doc.rolling_plan_id && frm.doc.coil) {
			generate_rolling_plan_id(frm);
		}
	},
});

frappe.ui.form.on("Rolling Plan Pass", {
	pass_number(frm) {
		update_pass_count(frm);
	},
	thickness_out(frm) {
		update_pass_count(frm);
	},
	planned_passes_add(frm) {
		update_pass_count(frm);
	},
	planned_passes_remove(frm) {
		update_pass_count(frm);
	},
});

function set_coil_query(frm) {
	frm.set_query("coil", () => {
		return {
			filters: {
				// docstatus: 1,
			},
		};
	});
}

function update_pass_count(frm) {
	const rows = frm.doc.planned_passes || [];
	frm.set_value("pass_count", rows.length || 0);
}

function generate_rolling_plan_id(frm) {
	if (!frm.doc.coil) {
		frappe.msgprint(__("Please select a Coil before generating Rolling Plan ID."));
		return;
	}

	frappe.call({
		method:
			"swynix_mes.swynix_mes.doctype.rolling_plan.rolling_plan.generate_rolling_plan_id",
		args: {
			coil: frm.doc.coil,
		},
		callback(r) {
			if (r.message) {
				frm.set_value("rolling_plan_id", r.message);
			}
		},
	});
}



