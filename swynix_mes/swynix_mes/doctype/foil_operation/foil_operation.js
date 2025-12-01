// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on("Foil Operation", {
	refresh(frm) {
		set_reel_query(frm);

		if (!frm.is_new()) {
			frm.add_custom_button(__("Load From Reel"), () => {
				load_from_reel(frm);
			});
		}
	},

	onload(frm) {
		set_reel_query(frm);
		// Auto-generate foil_operation_id for new documents
		if (frm.is_new() && !frm.doc.foil_operation_id) {
			frappe.call({
				method: 'swynix_mes.swynix_mes.doctype.foil_operation.foil_operation.generate_foil_operation_id',
				callback(r) {
					if (r.message) {
						frm.set_value('foil_operation_id', r.message);
					}
				}
			});
		}
	},

	reel(frm) {
		// Auto-load basic data when reel selected
		if (frm.doc.reel) {
			load_from_reel(frm);
		}
	},
});

function set_reel_query(frm) {
	frm.set_query("reel", () => {
		return {
			filters: {
				// Example: status: "Available",
			},
		};
	});
}

function load_from_reel(frm) {
	if (!frm.doc.reel) {
		frappe.msgprint(__("Please select a Reel first."));
		return;
	}

	frappe.call({
		method:
			"swynix_mes.swynix_mes.doctype.foil_operation.foil_operation.load_from_reel",
		args: {
			reel: frm.doc.reel,
		},
		callback(r) {
			if (!r.message) return;

			// Map a few standard fields if present in response
			if (r.message.width) {
				frm.set_value("width", r.message.width);
			}
			if (r.message.thickness) {
				frm.set_value("thickness", r.message.thickness);
			}
			if (r.message.coil) {
				frm.set_value("coil", r.message.coil);
			}
		},
	});
}



