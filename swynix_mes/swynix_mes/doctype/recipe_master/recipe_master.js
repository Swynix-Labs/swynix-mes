// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on('Recipe Master', {
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
