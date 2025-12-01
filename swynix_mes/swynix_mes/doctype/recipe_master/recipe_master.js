// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on('Recipe Master', {
    refresh(frm) {
        // Hide Update button if document is submitted
        if (frm.doc.docstatus === 1) {
            frm.page.clear_primary_action();
        }
    },
    onload(frm) {
        // Auto-generate recipe_id for new documents
        if (frm.is_new() && !frm.doc.recipe_id) {
            frappe.call({
                method: 'swynix_mes.swynix_mes.doctype.recipe_master.recipe_master.generate_recipe_id',
                callback(r) {
                    if (r.message) {
                        frm.set_value('recipe_id', r.message);
                    }
                }
            });
        }
    },

    validate(frm) {
        let total_ratio = 0;

        // Replace 'compositions' with your table fieldname if different
        (frm.doc.compositions || []).forEach(row => {
            // Replace 'ratio' with your fieldname if different
            total_ratio += flt(row.ratio || 0);
        });

        if (total_ratio !== 100) {
            frappe.throw(
                __("Total of all Planned % or Ratio must be exactly 100%. Current total: {0}%", [total_ratio])
            );
        }
    }
});
