// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on('Coil', {
	refresh(frm) {
		// Show coil_id as read-only badge
		if (frm.doc.coil_id) {
			frm.set_intro(__('Coil ID: <strong>{0}</strong>', [frm.doc.coil_id]));
		}

		// Toggle mother_coil visibility based on coil_role
		frm.toggle_reqd('mother_coil', frm.doc.coil_role === 'Child');
		frm.toggle_display('mother_coil', frm.doc.coil_role === 'Child');

		// Add filters for link fields
		set_field_filters(frm);

		// Add custom buttons for submitted docs
		if (frm.doc.docstatus === 1) {
			add_custom_buttons(frm);
		}
	},

	coil_role(frm) {
		// Clear mother_coil when role changes to Mother
		if (frm.doc.coil_role === 'Mother') {
			frm.set_value('mother_coil', '');
		}

		// Toggle mother_coil field
		frm.toggle_reqd('mother_coil', frm.doc.coil_role === 'Child');
		frm.toggle_display('mother_coil', frm.doc.coil_role === 'Child');
	},

	validate(frm) {
		// Validate mother coil for Child role
		if (frm.doc.coil_role === 'Child' && !frm.doc.mother_coil) {
			frappe.throw(__('Please select Mother Coil for a Child coil.'));
		}

		// Clear mother_coil for Mother role
		if (frm.doc.coil_role === 'Mother' && frm.doc.mother_coil) {
			frm.set_value('mother_coil', '');
		}
	},

	casting_plan(frm) {
		// Auto-fill fields from casting plan if selected
		if (frm.doc.casting_plan) {
			frappe.db.get_doc('PPC Casting Plan', frm.doc.casting_plan).then(plan => {
				if (plan) {
					// Auto-fill only if fields are empty
					if (!frm.doc.alloy && plan.alloy) {
						frm.set_value('alloy', plan.alloy);
					}
					if (!frm.doc.temper && plan.temper) {
						frm.set_value('temper', plan.temper);
					}
					if (!frm.doc.product_item && plan.product_item) {
						frm.set_value('product_item', plan.product_item);
					}
					if (!frm.doc.width_mm && plan.planned_width_mm) {
						frm.set_value('width_mm', plan.planned_width_mm);
					}
					if (!frm.doc.thickness_mm && plan.planned_gauge_mm) {
						frm.set_value('thickness_mm', plan.planned_gauge_mm);
					}
					if (!frm.doc.weight_mt && plan.planned_weight_mt) {
						frm.set_value('weight_mt', plan.planned_weight_mt);
					}
					if (!frm.doc.caster && plan.caster) {
						frm.set_value('caster', plan.caster);
					}
					if (!frm.doc.furnace && plan.furnace) {
						frm.set_value('furnace', plan.furnace);
					}
					if (plan.melting_batch && !frm.doc.melting_batch) {
						frm.set_value('melting_batch', plan.melting_batch);
					}
				}
			});
		}
	},

	melting_batch(frm) {
		// Auto-fill from melting batch if selected
		if (frm.doc.melting_batch) {
			frappe.db.get_doc('Melting Batch', frm.doc.melting_batch).then(batch => {
				if (batch) {
					if (!frm.doc.alloy && batch.alloy) {
						frm.set_value('alloy', batch.alloy);
					}
					if (!frm.doc.furnace && batch.furnace) {
						frm.set_value('furnace', batch.furnace);
					}
					if (!frm.doc.casting_plan && batch.ppc_casting_plan) {
						frm.set_value('casting_plan', batch.ppc_casting_plan);
					}
				}
			});
		}
	}
});

function set_field_filters(frm) {
	// Filter Alloy: Item Group = Alloy
	frm.set_query('alloy', () => {
		return {
			filters: {
				item_group: 'Alloy'
			}
		};
	});

	// Filter Product Item: Item Group = Product
	frm.set_query('product_item', () => {
		return {
			filters: {
				item_group: 'Product'
			}
		};
	});

	// Filter Mother Coil: Only Mother coils
	frm.set_query('mother_coil', () => {
		return {
			filters: {
				coil_role: 'Mother',
				docstatus: 1  // Only submitted mother coils
			}
		};
	});

	// Filter Caster: Workstation Type = Casting
	frm.set_query('caster', () => {
		return {
			filters: {
				workstation_type: 'Casting'
			}
		};
	});

	// Filter Furnace: Workstation Type = Foundry
	frm.set_query('furnace', () => {
		return {
			filters: {
				workstation_type: ['in', ['Foundry', 'Furnace', 'Melting Furnace']]
			}
		};
	});
}

function add_custom_buttons(frm) {
	// Button to create child coil
	if (frm.doc.coil_role === 'Mother') {
		frm.add_custom_button(__('Create Child Coil'), () => {
			frappe.new_doc('Coil', {
				coil_role: 'Child',
				mother_coil: frm.doc.name,
				alloy: frm.doc.alloy,
				temper: frm.doc.temper,
				product_item: frm.doc.product_item,
				casting_plan: frm.doc.casting_plan,
				melting_batch: frm.doc.melting_batch,
				heat_number: frm.doc.heat_number,
				batch_number: frm.doc.batch_number,
				caster: frm.doc.caster,
				furnace: frm.doc.furnace
			});
		}, __('Actions'));
	}

	// Button to view related coils (children of this mother)
	if (frm.doc.coil_role === 'Mother') {
		frm.add_custom_button(__('View Child Coils'), () => {
			frappe.set_route('List', 'Coil', {
				mother_coil: frm.doc.name
			});
		}, __('View'));
	}

	// Button to view mother coil
	if (frm.doc.coil_role === 'Child' && frm.doc.mother_coil) {
		frm.add_custom_button(__('View Mother Coil'), () => {
			frappe.set_route('Form', 'Coil', frm.doc.mother_coil);
		}, __('View'));
	}
}
