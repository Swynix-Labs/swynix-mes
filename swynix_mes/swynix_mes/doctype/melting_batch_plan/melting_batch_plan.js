// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.ui.form.on('Melting Batch Plan', {
    refresh: function(frm) {
        set_recipe_filter(frm);
        // Add "Fetch Materials" button
        if (frm.doc.recipe) {
            frm.add_custom_button(__('Fetch Materials'), function() {
                fetch_recipe_materials(frm);
            });
        }
    },

    onload(frm) {
        set_recipe_filter(frm);
        set_recipe_query(frm);
    },

    // When Alloy Grade changes, re-apply filter for recipes
    alloy_grade(frm) {
        set_recipe_query(frm);
        set_recipe_filter(frm);
        // Clear recipe & table if alloy is changed
        frm.set_value('recipe', null);
        frm.clear_table('planned_materials');
        frm.refresh_field('planned_materials');
        // Also show button when recipe is selected
        if (frm.doc.recipe) {
            frm.add_custom_button(__('Fetch Materials'), function() {
                fetch_recipe_materials(frm);
            });
        }
    },

    // When Recipe is selected, pull raw materials from Recipe Master
    recipe: function(frm) {
        set_recipe_filter(frm);
        // Also show button when recipe is selected
        if (frm.doc.recipe) {
            frm.add_custom_button(__('Fetch Materials'), function() {
                fetch_recipe_materials(frm);
            });
        }

        if (!frm.doc.recipe) return;

        frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "Recipe Master",
                name: frm.doc.recipe
            },
            callback: function(r) {
                if (!r.message) return;

                // Clear existing planned materials
                frm.clear_table("planned_materials");

                // r.message.compositions is the child table in Recipe Master
                (r.message.compositions || []).forEach(row => {
                    let child = frm.add_child("planned_materials");
                    child.item        = row.item;
                    child.source_type = row.source_type;
                    child.ratio       = row.ratio;      // % ratio
                    // planned_qty will be calculated once melt weight is entered
                });

                frm.refresh_field("planned_materials");

                // If melt weight is already filled, recalc quantities
                if (frm.doc.planned_melt_weight_kg) {
                    frm.trigger('planned_melt_weight_kg');
                }
            }
        });
    },

    planned_melt_weight_kg: function(frm) {
        // Recalculate planned quantities when planned melt weight changes
        calculate_planned_quantities(frm);
    },

    plan_date(frm) {
        if (!frm.doc.plan_date) return;

        let selected = frappe.datetime.str_to_obj(frm.doc.plan_date);
        let today = frappe.datetime.str_to_obj(frappe.datetime.get_today());

        // If selected date is before today
        if (selected < today) {
            frappe.msgprint({
                title: __("Invalid Date"),
                message: __("Plan Date cannot be earlier than today."),
                indicator: "red"
            });

            // Reset the field
            frm.set_value("plan_date", "");
        }
    },

    validate(frm) {
        if (frm.doc.plan_date) {
            let selected = frappe.datetime.str_to_obj(frm.doc.plan_date);
            let today = frappe.datetime.str_to_obj(frappe.datetime.get_today());

            if (selected < today) {
                frappe.throw("Plan Date cannot be earlier than today.");
            }
        }
    }
});

// Handle child table changes
frappe.ui.form.on('Recipe Detail', {
    ratio: function(frm, cdt, cdn) {
        // Recalculate when ratio changes
        calculate_planned_quantities(frm);
    }
});

function fetch_recipe_materials(frm) {
    if (!frm.doc.recipe) {
        frappe.msgprint(__('Please select a Recipe first'));
        return;
    }
    
    // Show loading indicator
    frappe.show_alert({
        message: __('Fetching materials...'),
        indicator: 'blue'
    }, 3);
    
    // Call server-side method
    frappe.call({
        method: 'swynix_mes.api.fetch_recipe_materials',
        args: {
            recipe_name: frm.doc.recipe
        },
        callback: function(r) {
            if (r.message && r.message.success) {
                // Clear existing planned_materials
                frm.clear_table('planned_materials');
                
                // Add each material to planned_materials
                r.message.materials.forEach(function(material) {
                    let row = frm.add_child('planned_materials');
                    row.item = material.item;
                    row.source_type = material.source_type;
                    row.ratio = material.ratio;
                    row.planned_qty = material.planned_qty;
                });
                
                // Refresh and calculate
                frm.refresh_field('planned_materials');
                calculate_planned_quantities(frm);
                
                frappe.show_alert({
                    message: r.message.message,
                    indicator: 'green'
                }, 5);
            } else {
                frappe.msgprint({
                    title: __('Error'),
                    message: r.message ? r.message.message : __('Failed to fetch materials'),
                    indicator: 'red'
                });
            }
        },
        error: function(err) {
            frappe.msgprint({
                title: __('Error'),
                message: __('Failed to fetch recipe materials. Check console for details.'),
                indicator: 'red'
            });
            console.error('Error:', err);
        }
    });
}

function calculate_planned_quantities(frm) {
    if (!frm.doc.planned_melt_weight_kg || frm.doc.planned_melt_weight_kg <= 0) {
        return;
    }
    
    let total_ratio = 0;
    
    // Calculate total ratio/percentage
    (frm.doc.planned_materials || []).forEach(function(row) {
        if (row.ratio) {
            total_ratio += flt(row.ratio);
        }
    });
    
    if (total_ratio === 0) {
        return;
    }
    
    // Calculate planned quantity for each row
    (frm.doc.planned_materials || []).forEach(function(row) {
        if (row.ratio) {
            // Formula: (Ratio / Total Ratio) * Planned Melt Weight
            let ratio_fraction = flt(row.ratio) / total_ratio;
            row.planned_qty = flt(ratio_fraction * flt(frm.doc.planned_melt_weight_kg), 3);
        }
    });
    
    frm.refresh_field('planned_materials');
    
    frappe.show_alert({
        message: __('Planned quantities calculated'),
        indicator: 'blue'
    }, 3);
}

// Helper: filter Recipe based on selected Alloy Grade
function set_recipe_query(frm) {
    frm.set_query("recipe", function() {
        let filters = {};
        if (frm.doc.alloy_grade) {
            filters.alloy_grade = frm.doc.alloy_grade;
        }
        return { filters: filters };
    });
}

function set_recipe_filter(frm) {
    frm.set_query('recipe', () => {
        let filters = {
            docstatus: 1    // only submitted recipes
        };

        if (frm.doc.alloy_grade) {
            filters["alloy_grade"] = frm.doc.alloy_grade;
        }

        return { filters: filters };
    });
}
