// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

var mk_current_furnace = null;
var mk_current_date = null;
var mk_current_batch = null;

frappe.pages["melting-kiosk"].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Melting Kiosk",
		single_column: true
	});

	$(frappe.render_template("melting_kiosk", {})).appendTo(page.body);

	mk_current_date = frappe.datetime.get_today();
	$("#mk_plan_date").val(mk_current_date);

	init_mk_events();
	load_furnaces();
};

frappe.pages["melting-kiosk"].on_page_show = function() {
	if (mk_current_furnace) {
		refresh_all();
	}
};

function init_mk_events() {
	$(document).on("change", "#mk_furnace_select", function() {
		mk_current_furnace = $(this).val();
		refresh_all();
	});

	$(document).on("change", "#mk_plan_date", function() {
		mk_current_date = $(this).val();
		refresh_all();
	});

	$(document).on("click", "#mk_btn_refresh", function() {
		refresh_all();
	});

	$(document).on("click", "#mk_btn_new_batch", function() {
		open_new_batch_dialog();
	});

	$(document).on("click", ".mk-batch-item", function() {
		var name = $(this).data("name");
		$(".mk-batch-item").removeClass("active");
		$(this).addClass("active");
		mk_current_batch = name;
		load_batch_detail(name);
	});

	// Casting Plan - Start Melting button
	$(document).on("click", ".mk-btn-start-from-plan", function(e) {
		e.stopPropagation();
		var planName = $(this).data("plan");
		confirm_and_start_from_plan(planName);
	});

	$(document).on("click", "#mk_btn_add_rm", function() {
		open_add_rm_dialog(false);
	});

	$(document).on("click", "#mk_btn_correction", function() {
		open_add_rm_dialog(true);
	});

	$(document).on("click", "#mk_btn_charging_complete", function() {
		mark_charging_complete();
	});

	$(document).on("click", "#mk_btn_burner_on", function() {
		log_process_event("Burner On");
	});

	$(document).on("click", "#mk_btn_fluxing", function() {
		open_flux_dialog();
	});

	$(document).on("click", "#mk_btn_sample", function() {
		create_sample();
	});

	$(document).on("click", "#mk_btn_ready_transfer", function() {
		mark_ready_for_transfer();
	});

	// Tab switching (Raw / Process / Spectro / Transfer) - custom JS, no route change
	$(document).on("click", "#mk_batch_tabs .mk-tab", function(e) {
		e.preventDefault();
		var tab = $(this).data("tab");

		// Set active tab header
		$("#mk_batch_tabs .mk-tab").removeClass("active");
		$(this).addClass("active");

		// Hide all tab panes
		$(".mk-tab-pane").removeClass("active");

		// Show selected pane
		$("#mk_tab_" + tab).addClass("active");
	});
}

function load_furnaces() {
	frappe.call({
		method: "swynix_mes.swynix_mes.api.melting_kiosk.get_furnaces",
		callback: function(r) {
			var furnaces = r.message || [];
			var $select = $("#mk_furnace_select");
			$select.empty();
			$select.append('<option value="">-- Select Furnace --</option>');
			furnaces.forEach(function(f) {
				$select.append('<option value="' + f.name + '">' + (f.workstation_name || f.name) + '</option>');
			});
		}
	});
}

// ==================== REFRESH ALL ====================

function refresh_all() {
	refresh_cast_plans();
	refresh_batches();
}

// ==================== CASTING PLANS ====================

function refresh_cast_plans() {
	var $container = $("#mk_cast_plan_container");
	
	if (!mk_current_furnace) {
		$container.html(
			'<div class="mk-empty">' +
				'<div class="empty-icon"><i class="fa fa-calendar-o"></i></div>' +
				'<div class="empty-text">Select a furnace to see casting plans</div>' +
			'</div>'
		);
		return;
	}

	frappe.call({
		method: "swynix_mes.swynix_mes.api.melting_kiosk.get_cast_plans_for_furnace",
		args: {
			furnace: mk_current_furnace,
			for_date: mk_current_date
		},
		callback: function(r) {
			var plans = r.message || [];
			render_cast_plans(plans);
		}
	});
}

function render_cast_plans(plans) {
	var $container = $("#mk_cast_plan_container");
	
	if (!plans.length) {
		$container.html(
			'<div class="mk-empty">' +
				'<div class="empty-icon"><i class="fa fa-calendar-o"></i></div>' +
				'<div class="empty-text">No casting plans for this date</div>' +
			'</div>'
		);
		return;
	}

	var html = "";
	plans.forEach(function(p) {
		var hasBatch = p.melting_batch ? true : false;
		var itemClass = hasBatch ? "mk-plan-item has-batch" : "mk-plan-item";
		
		// Format time range
		var startTime = p.start_datetime ? frappe.datetime.str_to_user(p.start_datetime).split(' ')[1] || "" : "";
		var endTime = p.end_datetime ? frappe.datetime.str_to_user(p.end_datetime).split(' ')[1] || "" : "";
		var timeRange = startTime && endTime ? (startTime + " → " + endTime) : (startTime || "");
		
		// Badge class
		var badgeClass = hasBatch ? "badge badge-started" : "badge badge-planned";
		var badgeText = hasBatch ? "Started" : (p.status || "Planned");
		
		// Button
		var btnDisabled = hasBatch ? "disabled" : "";
		var btnClass = hasBatch ? "btn btn-success btn-start" : "btn btn-primary btn-start";
		var btnLabel = hasBatch ? '<i class="fa fa-check"></i> Started' : '<i class="fa fa-play"></i> Start';
		
		// Product and alloy display
		var productName = p.product_item || "No Product";
		var alloyName = p.alloy || "-";
		
		html += '<div class="' + itemClass + '">' +
			'<div class="plan-title">' + frappe.utils.escape_html(productName) + ' <span style="font-weight:normal;color:#6c757d;">(' + frappe.utils.escape_html(alloyName) + ')</span></div>' +
			'<div class="plan-meta"><i class="fa fa-clock-o"></i> ' + timeRange + (p.duration_minutes ? ' (' + p.duration_minutes + ' min)' : '') + '</div>' +
			'<div class="plan-specs">' +
				'Width: ' + (p.planned_width_mm || "-") + ' mm | ' +
				'Gauge: ' + (p.planned_gauge_mm || "-") + ' mm | ' +
				'Weight: ' + (p.planned_weight_mt || "-") + ' MT' +
			'</div>' +
			'<div class="plan-footer">' +
				'<span class="' + badgeClass + '">' + frappe.utils.escape_html(badgeText) + '</span>' +
				'<button type="button" class="' + btnClass + ' mk-btn-start-from-plan" data-plan="' + p.name + '" ' + btnDisabled + '>' + btnLabel + '</button>' +
			'</div>' +
		'</div>';
	});
	
	$container.html(html);
}

function confirm_and_start_from_plan(planName) {
	if (!planName) return;

	frappe.confirm(
		__("Start melting for this casting plan?<br><br>This will create a new Melting Batch and link it to this plan."),
		function() {
			frappe.call({
				method: "swynix_mes.swynix_mes.api.melting_kiosk.start_batch_from_cast_plan",
				args: { plan_name: planName },
				freeze: true,
				freeze_message: __("Creating Melting Batch..."),
				callback: function(r) {
					if (r.message) {
						var batchName = r.message.melting_batch;
						var batchId = r.message.melting_batch_id || batchName;
						
						frappe.show_alert({
							message: __("Melting Batch {0} created from casting plan!", [batchId]),
							indicator: "green"
						});
						
						// Set the new batch as current and refresh
						mk_current_batch = batchName;
						refresh_all();
					}
				}
			});
		}
	);
}

// ==================== BATCH LIST ====================

function refresh_batches() {
	if (!mk_current_furnace) {
		$("#mk_batch_list_container").html(
			'<div class="mk-empty">' +
				'<div class="empty-icon"><i class="fa fa-inbox"></i></div>' +
				'<div class="empty-text">Select a furnace to see batches</div>' +
			'</div>'
		);
		clear_batch_detail();
		return;
	}

	frappe.call({
		method: "swynix_mes.swynix_mes.api.melting_kiosk.get_batches_for_furnace",
		args: {
			furnace: mk_current_furnace,
			for_date: mk_current_date
		},
		callback: function(r) {
			var batches = r.message || [];
			render_batch_list(batches);
		}
	});
}

function render_batch_list(batches) {
	var $container = $("#mk_batch_list_container");
	
	if (!batches.length) {
		$container.html(
			'<div class="mk-empty">' +
				'<div class="empty-icon"><i class="fa fa-inbox"></i></div>' +
				'<div class="empty-text">No batches for this date</div>' +
				'<button type="button" class="btn btn-primary btn-sm" id="mk_btn_new_batch_empty" style="margin-top: 12px;">' +
					'<i class="fa fa-plus"></i> Create First Batch' +
				'</button>' +
			'</div>'
		);
		clear_batch_detail();
		$("#mk_btn_new_batch_empty").on("click", function() {
			open_new_batch_dialog();
		});
		return;
	}

	var html = '';
	batches.forEach(function(b) {
		var label = b.melting_batch_id || b.name;
		var statusClass = get_batch_status_class(b.status);
		var subtitle = (b.alloy || "-") + " | " + (b.product_item || "-");
		var weight_info = b.charged_weight_mt ? flt(b.charged_weight_mt, 3) + " MT" : "";
		var active_class = mk_current_batch === b.name ? " active" : "";
		
		html += '<div class="mk-batch-item' + active_class + '" data-name="' + b.name + '">' +
			'<div class="batch-info">' +
				'<div class="batch-name">' + label + '</div>' +
				'<div class="batch-meta">' + subtitle + (weight_info ? ' | ' + weight_info : '') + '</div>' +
			'</div>' +
			'<span class="batch-status ' + statusClass + '">' + b.status + '</span>' +
		'</div>';
	});
	$container.html(html);

	// Auto-select first batch or reload current batch
	if (!mk_current_batch && batches[0]) {
		mk_current_batch = batches[0].name;
		$(".mk-batch-item").first().addClass("active");
		load_batch_detail(mk_current_batch);
	} else if (mk_current_batch) {
		// Check if current batch still exists in list
		var exists = false;
		for (var i = 0; i < batches.length; i++) {
			if (batches[i].name === mk_current_batch) {
				exists = true;
				break;
			}
		}
		if (exists) {
			load_batch_detail(mk_current_batch);
		} else if (batches[0]) {
			mk_current_batch = batches[0].name;
			$(".mk-batch-item").first().addClass("active");
			load_batch_detail(mk_current_batch);
		}
	}
}

function get_status_class(status) {
	var map = {
		"Draft": "mk-status-draft",
		"Charging": "mk-status-charging",
		"Melting": "mk-status-melting",
		"Ready for Transfer": "mk-status-ready",
		"Transferred": "mk-status-transferred",
		"Cancelled": "mk-status-cancelled"
	};
	return map[status] || "mk-status-draft";
}

function get_batch_status_class(status) {
	var map = {
		"Draft": "batch-status-charging",
		"Charging": "batch-status-charging",
		"Melting": "batch-status-melting",
		"Ready for Transfer": "batch-status-ready",
		"Transferred": "batch-status-transferred",
		"Cancelled": "batch-status-charging"
	};
	return map[status] || "batch-status-charging";
}

function clear_batch_detail() {
	mk_current_batch = null;
	mk_current_batch_detail = null;
	mk_current_recipe_items = [];
	
	$("#mk_batch_title").html(
		'<i class="fa fa-fire" style="color: #ef4444;"></i> ' +
		'<span>No batch selected</span>'
	);
	$("#mk_batch_summary").html(
		'<div class="mk-empty" style="padding: 30px;">' +
			'<div class="empty-icon"><i class="fa fa-hand-pointer-o"></i></div>' +
			'<div class="empty-text">Select a batch from the list to view details</div>' +
		'</div>'
	);
	$("#mk_raw_table").empty();
	$("#mk_raw_charged_container").empty();
	$("#mk_process_table").empty();
	$("#mk_spectro_table").empty();
	$("#mk_transfer_form").empty();
	$("#mk_action_buttons").hide();
}

function load_batch_detail(name) {
	if (!name) return;

	frappe.call({
		method: "swynix_mes.swynix_mes.api.melting_kiosk.get_batch_detail",
		args: {
			batch_name: name
		},
		callback: function(r) {
			var data = r.message || {};
			var doc = data;  // backward compatibility - doc contains all batch fields
			var batch = data.batch || doc;
			var plan = data.plan || {};
			var recipe = data.recipe || {};
			var recipe_items = data.recipe_items || [];
			
			// Store for later use
			mk_current_batch_detail = data;
			mk_current_recipe_items = recipe_items;
			
			render_batch_header(doc, batch, plan, recipe);
			render_recipe_targets(recipe, recipe_items, batch, plan);
			render_raw_table(doc);
			render_process_table(doc);
			render_spectro_table(doc);
			render_transfer_form(doc);
			update_action_buttons(doc);
		}
	});
}

// Global variables for batch detail
var mk_current_batch_detail = null;
var mk_current_recipe_items = [];

function render_batch_header(doc, batch, plan, recipe) {
	batch = batch || doc;
	plan = plan || {};
	recipe = recipe || {};
	
	var title = batch.melting_batch_id || batch.name || doc.melting_batch_id || doc.name;
	var statusClass = get_batch_status_class(doc.status);
	
	// Show linked casting plan if any
	var planLink = "";
	if (doc.ppc_casting_plan) {
		planLink = '<a href="/app/ppc-casting-plan/' + doc.ppc_casting_plan + '" target="_blank" style="font-size: 12px; color: #6c757d; margin-left: 10px;">' +
			'<i class="fa fa-link"></i> ' + frappe.utils.escape_html(doc.ppc_casting_plan) +
			'</a>';
	}
	
	$("#mk_batch_title").html(
		'<i class="fa fa-fire" style="color: #ef4444;"></i> ' +
		'<span>' + title + '</span> ' +
		'<span class="batch-status ' + statusClass + '">' + doc.status + '</span> ' +
		planLink
	);

	// Get values from batch first, then fall back to plan
	var planned_weight = doc.planned_weight_mt || (plan && plan.planned_weight_mt);
	var width_mm = doc.planned_width_mm || (plan && plan.planned_width_mm) || "-";
	var gauge_mm = doc.planned_gauge_mm || (plan && plan.planned_gauge_mm) || "-";
	var temper = doc.temper || (plan && plan.temper) || "-";
	var recipe_name = doc.charge_mix_recipe || (plan && plan.charge_mix_recipe) || "-";
	
	var planned = planned_weight ? flt(planned_weight, 3) + " MT" : "-";
	var charged = doc.charged_weight_mt ? flt(doc.charged_weight_mt, 3) + " MT" : "-";
	var tapped = doc.tapped_weight_mt ? flt(doc.tapped_weight_mt, 3) + " MT" : "-";
	var yield_pct = doc.yield_percent ? flt(doc.yield_percent, 2) + "%" : "-";
	var yield_style = "";
	if (doc.yield_percent >= 95) {
		yield_style = "color: #059669;";
	} else if (doc.yield_percent < 90 && doc.yield_percent > 0) {
		yield_style = "color: #d97706;";
	}

	// First row: Alloy, Product, Temper
	var html = '<div class="mk-summary-grid">';
	html += '<div class="summary-item"><div class="summary-label">Alloy</div><div class="summary-value">' + frappe.utils.escape_html(doc.alloy || "-") + '</div></div>';
	html += '<div class="summary-item"><div class="summary-label">Product</div><div class="summary-value">' + frappe.utils.escape_html(doc.product_item || "-") + '</div></div>';
	html += '<div class="summary-item"><div class="summary-label">Temper</div><div class="summary-value">' + frappe.utils.escape_html(temper) + '</div></div>';
	html += '</div>';
	
	// Second row: Width, Gauge, Planned Weight
	html += '<div class="mk-summary-grid" style="margin-top: 1px;">';
	html += '<div class="summary-item"><div class="summary-label">Width (mm)</div><div class="summary-value">' + (width_mm !== "-" ? width_mm : "-") + '</div></div>';
	html += '<div class="summary-item"><div class="summary-label">Gauge (mm)</div><div class="summary-value">' + (gauge_mm !== "-" ? gauge_mm : "-") + '</div></div>';
	html += '<div class="summary-item"><div class="summary-label">Planned Weight</div><div class="summary-value">' + planned + '</div></div>';
	html += '</div>';
	
	// Third row: Charged, Tapped, Yield
	html += '<div class="mk-summary-grid" style="margin-top: 1px;">';
	html += '<div class="summary-item"><div class="summary-label">Charged</div><div class="summary-value">' + charged + '</div></div>';
	html += '<div class="summary-item"><div class="summary-label">Tapped</div><div class="summary-value">' + tapped + '</div></div>';
	html += '<div class="summary-item"><div class="summary-label">Yield</div><div class="summary-value" style="' + yield_style + '">' + yield_pct + '</div></div>';
	html += '</div>';
	
	// Third row: Recipe link
	if (recipe_name && recipe_name !== "-") {
		html += '<div style="padding: 8px 15px; background: #f9fafb; border-bottom: 1px solid #e5e7eb; font-size: 12px;">';
		html += '<span style="color: #6c757d;"><i class="fa fa-clipboard"></i> Recipe: </span>';
		html += '<a href="/app/charge-mix-ratio/' + recipe_name + '" target="_blank" style="color: #2490ef;">' + frappe.utils.escape_html(recipe_name) + '</a>';
		html += '</div>';
	}
	
	$("#mk_batch_summary").html(html);
	$("#mk_action_buttons").show();
}

function update_action_buttons(doc) {
	$("#mk_action_buttons").show();
	
	var status = doc.status;
	var $burner = $("#mk_btn_burner_on");
	var $fluxing = $("#mk_btn_fluxing");
	var $sample = $("#mk_btn_sample");
	var $correction = $("#mk_btn_correction");
	var $ready = $("#mk_btn_ready_transfer");
	var $addRm = $("#mk_btn_add_rm");
	var $chargingComplete = $("#mk_btn_charging_complete");

	$burner.prop("disabled", false).show();
	$fluxing.prop("disabled", false).show();
	$sample.prop("disabled", false).show();
	$correction.prop("disabled", false).show();
	$ready.prop("disabled", false).show();
	$addRm.prop("disabled", false).show();
	$chargingComplete.prop("disabled", false).show();

	if (status === "Transferred" || status === "Cancelled") {
		$burner.prop("disabled", true);
		$fluxing.prop("disabled", true);
		$sample.prop("disabled", true);
		$correction.prop("disabled", true);
		$ready.prop("disabled", true);
		$addRm.prop("disabled", true);
		$chargingComplete.prop("disabled", true);
	} else if (status === "Ready for Transfer") {
		$chargingComplete.prop("disabled", true);
		$addRm.prop("disabled", true);
	} else if (status === "Melting") {
		$chargingComplete.hide();
	} else if (status === "Charging") {
		$ready.prop("disabled", true);
	}
}

function render_recipe_targets(recipe, items, batch, plan) {
	// This renders ABOVE the charged materials in the Raw Material tab
	var $container = $("#mk_raw_table");
	
	// Get planned weight for calculating target kg
	var planned_weight_mt = (batch && batch.planned_weight_mt) || 
		(plan && plan.planned_weight_mt) || 0;
	
	var html = "";
	
	// Recipe Targets Section
	if (items && items.length) {
		html += '<div style="margin-bottom: 15px;">';
		html += '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">';
		html += '<div style="font-weight: 600; font-size: 13px; color: #374151;">';
		html += '<i class="fa fa-clipboard" style="color: #6366f1;"></i> Recipe Targets';
		if (recipe && recipe.name) {
			html += ' <span style="font-weight: normal; color: #6c757d;">- ' + frappe.utils.escape_html(recipe.name) + '</span>';
		}
		html += '</div>';
		if (planned_weight_mt) {
			html += '<div style="font-size: 12px; color: #6c757d;">Planned: ' + flt(planned_weight_mt, 3) + ' MT (' + flt(planned_weight_mt * 1000, 0) + ' kg)</div>';
		}
		html += '</div>';
		
		html += '<table class="mk-table" style="font-size: 12px;">';
		html += '<thead><tr>';
		html += '<th>Ingredient</th>';
		html += '<th>Item Group</th>';
		html += '<th class="text-right">Target %</th>';
		html += '<th class="text-right">Min %</th>';
		html += '<th class="text-right">Max %</th>';
		html += '<th class="text-right">Target Qty (kg)</th>';
		html += '<th style="width: 60px;">Req</th>';
		html += '</tr></thead>';
		html += '<tbody>';
		
		items.forEach(function(row) {
			var ing_name = frappe.utils.escape_html(row.ingredient_name || row.ingredient || "");
			var item_group = frappe.utils.escape_html(row.item_group || "");
			var t_pct = row.target_pct != null ? flt(row.target_pct, 2) : "-";
			var minp = row.min_pct != null ? flt(row.min_pct, 2) : "-";
			var maxp = row.max_pct != null ? flt(row.max_pct, 2) : "-";
			var t_kg = row.target_kg != null ? flt(row.target_kg, 1) : "-";
			var is_mandatory = row.mandatory ? 1 : 0;
			
			// Row highlighting for range type
			var row_style = row.proportion_type === "Range" ? "background: #fefce8;" : "";
			
			html += '<tr style="' + row_style + '">';
			html += '<td class="text-bold">' + ing_name + '</td>';
			html += '<td>' + item_group + '</td>';
			html += '<td class="text-right">' + t_pct + '</td>';
			html += '<td class="text-right" style="color: #6c757d;">' + minp + '</td>';
			html += '<td class="text-right" style="color: #6c757d;">' + maxp + '</td>';
			html += '<td class="text-right text-bold" style="color: #059669;">' + t_kg + '</td>';
			html += '<td>';
			if (is_mandatory) {
				html += '<span style="background: #fee2e2; color: #b91c1c; padding: 2px 6px; border-radius: 4px; font-size: 10px;">Yes</span>';
			}
			html += '</td>';
			html += '</tr>';
		});
		
		html += '</tbody></table>';
		html += '</div>';
	} else {
		html += '<div style="margin-bottom: 15px; padding: 12px; background: #f3f4f6; border-radius: 6px; color: #6c757d; font-size: 12px;">';
		html += '<i class="fa fa-info-circle"></i> No Charge Mix Recipe targets found for this batch.';
		html += '</div>';
	}
	
	// Container for charged materials (will be filled by render_raw_table)
	html += '<div id="mk_raw_charged_container"></div>';
	
	$container.html(html);
}

function render_raw_table(doc) {
	var $container = $("#mk_raw_charged_container");
	
	// If container doesn't exist (recipe targets not rendered), use main container
	if (!$container.length) {
		$container = $("#mk_raw_table");
	}
	
	// Section header
	var html = '<div style="font-weight: 600; font-size: 13px; color: #374151; margin-bottom: 8px; margin-top: 10px;">';
	html += '<i class="fa fa-cubes" style="color: #f59e0b;"></i> Charged Materials';
	html += '</div>';
	
	if (!doc.raw_materials || !doc.raw_materials.length) {
		html += '<div class="mk-empty" style="padding: 20px;">' +
			'<div class="empty-icon" style="font-size: 24px;"><i class="fa fa-inbox"></i></div>' +
			'<div class="empty-text">No raw materials charged yet</div>' +
		'</div>';
		$container.html(html);
		return;
	}

	var total_kg = 0;
	var correction_kg = 0;

	html += '<table class="mk-table">';
	html += '<thead><tr><th style="width: 40px;">#</th><th>Type</th><th>Item</th><th>Batch / Heat</th><th>Bin</th><th>Bucket</th><th class="text-right">Qty (kg)</th><th style="width: 80px;">Correction</th></tr></thead>';
	html += '<tbody>';

	doc.raw_materials.forEach(function(r, idx) {
		total_kg += flt(r.qty_kg);
		if (r.is_correction) correction_kg += flt(r.qty_kg);
		
		var row_style = r.is_correction ? " style=\"background: #fef3c7;\"" : "";
		html += '<tr' + row_style + '>';
		html += '<td>' + (idx + 1) + '</td>';
		html += '<td>' + frappe.utils.escape_html(r.ingredient_type || "-") + '</td>';
		html += '<td class="text-bold">' + frappe.utils.escape_html(r.item_code || "-") + '<br><small style="font-weight: normal; color: #6c757d;">' + frappe.utils.escape_html(r.item_name || "") + '</small></td>';
		html += '<td>' + frappe.utils.escape_html(r.batch_no || "-") + '</td>';
		html += '<td>' + frappe.utils.escape_html(r.source_bin || "-") + '</td>';
		html += '<td>' + frappe.utils.escape_html(r.bucket_no || "-") + '</td>';
		html += '<td class="text-right text-bold">' + flt(r.qty_kg, 3) + '</td>';
		html += '<td>' + (r.is_correction ? '<span style="background: #fef3c7; color: #b45309; padding: 2px 6px; border-radius: 4px; font-size: 10px;">Yes</span>' : '') + '</td>';
		html += '</tr>';
	});

	html += '</tbody>';
	html += '<tfoot>';
	html += '<tr style="font-weight: 600; background: #f5f7fa;"><td colspan="6" class="text-right">Total:</td><td class="text-right">' + flt(total_kg, 3) + ' kg</td><td></td></tr>';
	if (correction_kg > 0) {
		html += '<tr style="background: #fef3c7;"><td colspan="6" class="text-right">Correction Total:</td><td class="text-right">' + flt(correction_kg, 3) + ' kg</td><td></td></tr>';
	}
	html += '</tfoot></table>';

	$container.html(html);
}

function render_process_table(doc) {
	var $container = $("#mk_process_table");
	
	if (!doc.process_logs || !doc.process_logs.length) {
		$container.html(
			'<div class="mk-empty">' +
				'<div class="empty-icon"><i class="fa fa-list-ol"></i></div>' +
				'<div class="empty-text">No process events logged yet</div>' +
			'</div>'
		);
		return;
	}

	var html = '<table class="mk-table">';
	html += '<thead><tr><th>Time</th><th>Event</th><th class="text-right">Temp</th><th class="text-right">Pressure</th><th>Flux</th><th>Sample</th><th>Note</th></tr></thead>';
	html += '<tbody>';

	doc.process_logs.forEach(function(r) {
		var event_style = get_event_style(r.event_type);
		html += '<tr>';
		html += '<td>' + frappe.datetime.str_to_user(r.log_time) + '</td>';
		html += '<td><span style="' + event_style + ' padding: 2px 8px; border-radius: 4px; font-size: 11px;">' + (r.event_type || "-") + '</span></td>';
		html += '<td class="text-right">' + (r.temp_c || "-") + '</td>';
		html += '<td class="text-right">' + (r.pressure_bar || "-") + '</td>';
		html += '<td>' + (r.flux_type || "-") + (r.flux_qty_kg ? " (" + r.flux_qty_kg + " kg)" : "") + '</td>';
		html += '<td>' + (r.sample_id || "-") + '</td>';
		html += '<td>' + (r.note || "-") + '</td>';
		html += '</tr>';
	});

	html += '</tbody></table>';
	$container.html(html);
}

function get_event_style(event_type) {
	var map = {
		"Burner On": "background: #d1fae5; color: #047857;",
		"Fluxing": "background: #dbeafe; color: #1d4ed8;",
		"Sample Taken": "background: #fef3c7; color: #b45309;",
		"Correction": "background: #fee2e2; color: #b91c1c;",
		"Holding": "background: #f3f4f6; color: #4b5563;",
		"Transfer": "background: #e0e7ff; color: #4338ca;"
	};
	return map[event_type] || "background: #f3f4f6; color: #4b5563;";
}

function render_spectro_table(doc) {
	var $container = $("#mk_spectro_table");
	
	if (!doc.spectro_samples || !doc.spectro_samples.length) {
		$container.html(
			'<div class="mk-empty">' +
				'<div class="empty-icon"><i class="fa fa-flask"></i></div>' +
				'<div class="empty-text">No spectro samples taken yet</div>' +
			'</div>'
		);
		return;
	}

	var html = '<table class="mk-table">';
	html += '<thead><tr><th>Sample ID</th><th>Time</th><th>Si %</th><th>Fe %</th><th>Cu %</th><th>Mn %</th><th>Mg %</th><th>Zn %</th><th>Ti %</th><th>Al %</th><th>Status</th><th>Correction</th></tr></thead>';
	html += '<tbody>';

	doc.spectro_samples.forEach(function(s) {
		var status_style = "background: #f3f4f6; color: #4b5563;";
		if (s.result_status === "Within Limit") {
			status_style = "background: #d1fae5; color: #047857;";
		} else if (s.result_status === "Out of Limit") {
			status_style = "background: #fee2e2; color: #b91c1c;";
		}
		
		html += '<tr>';
		html += '<td class="text-bold">' + (s.sample_id || "-") + '</td>';
		html += '<td>' + frappe.datetime.str_to_user(s.sample_time) + '</td>';
		html += '<td>' + (s.si_percent || "-") + '</td>';
		html += '<td>' + (s.fe_percent || "-") + '</td>';
		html += '<td>' + (s.cu_percent || "-") + '</td>';
		html += '<td>' + (s.mn_percent || "-") + '</td>';
		html += '<td>' + (s.mg_percent || "-") + '</td>';
		html += '<td>' + (s.zn_percent || "-") + '</td>';
		html += '<td>' + (s.ti_percent || "-") + '</td>';
		html += '<td>' + (s.al_percent || "-") + '</td>';
		html += '<td><span style="' + status_style + ' padding: 2px 8px; border-radius: 4px; font-size: 11px;">' + (s.result_status || "Pending") + '</span></td>';
		html += '<td>' + (s.correction_required ? '<span style="background: #fef3c7; color: #b45309; padding: 2px 6px; border-radius: 4px; font-size: 10px;">Yes</span>' : '') + '</td>';
		html += '</tr>';
	});

	html += '</tbody></table>';
	$container.html(html);
}

function render_transfer_form(doc) {
	var $container = $("#mk_transfer_form");
	var editable = (doc.status === "Ready for Transfer");
	var is_transferred = (doc.status === "Transferred");
	var disabled = editable ? "" : " disabled";

	var html = '<div style="max-width: 500px;">';
	
	html += '<div class="mk-form-group">';
	html += '<label>Tapped Metal (MT)</label>';
	html += '<input type="number" step="0.001" class="form-control" id="mk_tapped_weight" value="' + (doc.tapped_weight_mt || "") + '"' + disabled + '>';
	html += '</div>';
	
	html += '<div class="mk-form-group">';
	html += '<label>FO Temp (°C)</label>';
	html += '<input type="number" class="form-control" id="mk_fo_temp" value="' + (doc.fo_temp_c || "") + '"' + disabled + '>';
	html += '</div>';
	
	html += '<div class="mk-form-group">';
	html += '<label>FO Pressure (bar)</label>';
	html += '<input type="number" step="0.01" class="form-control" id="mk_fo_press" value="' + (doc.fo_pressure_bar || "") + '"' + disabled + '>';
	html += '</div>';
	
	html += '<div class="mk-form-group">';
	html += '<label>Dross (kg)</label>';
	html += '<input type="number" step="0.1" class="form-control" id="mk_dross" value="' + (doc.dross_weight_kg || "") + '"' + disabled + '>';
	html += '</div>';
	
	html += '<div class="mk-form-group">';
	html += '<label>Fuel (L/SCM)</label>';
	html += '<input type="number" step="0.1" class="form-control" id="mk_fuel" value="' + (doc.energy_fuel_litre || "") + '"' + disabled + '>';
	html += '</div>';
	
	html += '<div class="mk-form-group">';
	html += '<label>Note</label>';
	html += '<textarea class="form-control" id="mk_transfer_note" rows="2"' + disabled + '>' + (doc.remarks || "") + '</textarea>';
	html += '</div>';
	
	html += '<div style="margin-top: 20px;">';
	if (editable) {
		html += '<button type="button" class="btn btn-primary" id="mk_btn_complete_transfer"><i class="fa fa-check"></i> Submit and Complete Transfer</button>';
	} else if (is_transferred) {
		html += '<div style="padding: 12px; background: #d1fae5; color: #047857; border-radius: 4px;"><i class="fa fa-check-circle"></i> Transfer completed at ' + frappe.datetime.str_to_user(doc.transfer_end_datetime) + '</div>';
	} else {
		html += '<div style="padding: 12px; background: #dbeafe; color: #1d4ed8; border-radius: 4px;"><i class="fa fa-info-circle"></i> Batch must be Ready for Transfer to complete transfer</div>';
	}
	html += '</div>';
	html += '</div>';

	$container.html(html);

	if (editable) {
		$("#mk_btn_complete_transfer").on("click", function() {
			complete_transfer();
		});
	}
}

function open_new_batch_dialog() {
	if (!mk_current_furnace) {
		frappe.msgprint(__("Please select a furnace first."));
		return;
	}

	var d = new frappe.ui.Dialog({
		title: __("Start New Melting Batch"),
		fields: [
			{
				fieldname: "furnace",
				label: __("Furnace"),
				fieldtype: "Link",
				options: "Workstation",
				default: mk_current_furnace,
				read_only: 1
			},
			{
				fieldname: "alloy",
				label: __("Alloy"),
				fieldtype: "Link",
				options: "Item"
			},
			{
				fieldname: "product_item",
				label: __("Product Item"),
				fieldtype: "Link",
				options: "Item"
			},
			{
				fieldname: "charge_mix_recipe",
				label: __("Charge Mix Recipe"),
				fieldtype: "Link",
				options: "Charge Mix Ratio"
			},
			{
				fieldname: "planned_weight_mt",
				label: __("Planned Metal (MT)"),
				fieldtype: "Float",
				precision: 3
			}
		],
		primary_action_label: __("Create Batch"),
		primary_action: function(values) {
			frappe.call({
				method: "swynix_mes.swynix_mes.api.melting_kiosk.create_melting_batch",
				args: { data: values },
				callback: function(r) {
					d.hide();
					frappe.show_alert({
						message: __("Melting Batch {0} created", [r.message]),
						indicator: "green"
					});
					mk_current_batch = r.message;
					mk_current_date = frappe.datetime.get_today();
					$("#mk_plan_date").val(mk_current_date);
					refresh_all();
				}
			});
		}
	});

	d.fields_dict.alloy.get_query = function() {
		return { filters: { item_group: "Alloy" } };
	};

	d.fields_dict.product_item.get_query = function() {
		return { filters: { item_group: "Product" } };
	};

	d.fields_dict.charge_mix_recipe.get_query = function() {
		var alloy = d.get_value("alloy");
		var filters = { is_active: 1, docstatus: 1 };
		if (alloy) filters.alloy = alloy;
		return { filters: filters };
	};

	d.show();
}

function open_add_rm_dialog(is_correction) {
	if (!mk_current_batch) {
		frappe.msgprint(__("Select a batch first."));
		return;
	}

	var d = new frappe.ui.Dialog({
		title: is_correction ? __("Add Correction Charge") : __("Add Raw Material"),
		fields: [
			{
				fieldname: "ingredient_type",
				label: __("Ingredient Type"),
				fieldtype: "Select",
				options: "Primary Ingot\nPlant Scrap\nEC Scrap\nSecondary Scrap\nDross Ingot\nFlux\nAdditive\nCorrection Element\nOther",
				reqd: 1,
				default: is_correction ? "Correction Element" : ""
			},
			{
				fieldname: "item_code",
				label: __("Item"),
				fieldtype: "Link",
				options: "Item",
				reqd: 1
			},
			{
				fieldname: "batch_no",
				label: __("Batch / Heat / Lot"),
				fieldtype: "Data"
			},
			{
				fieldname: "source_bin",
				label: __("Source Bin"),
				fieldtype: "Link",
				options: "Warehouse"
			},
			{
				fieldname: "bucket_no",
				label: __("Bucket / Charge No"),
				fieldtype: "Data"
			},
			{
				fieldname: "qty_kg",
				label: __("Qty (kg)"),
				fieldtype: "Float",
				reqd: 1,
				precision: 3
			}
		],
		primary_action_label: __("Add"),
		primary_action: function(values) {
			frappe.call({
				method: "swynix_mes.swynix_mes.api.melting_kiosk.add_raw_material_row",
				args: {
					batch_name: mk_current_batch,
					item_code: values.item_code,
					qty_kg: values.qty_kg,
					ingredient_type: values.ingredient_type,
					batch_no: values.batch_no,
					source_bin: values.source_bin,
					bucket_no: values.bucket_no,
					is_correction: is_correction ? 1 : 0
				},
				callback: function() {
					d.hide();
					frappe.show_alert({
						message: __("Raw material added"),
						indicator: "green"
					});
					load_batch_detail(mk_current_batch);
					refresh_batches();
				}
			});
		}
	});

	d.show();
}

function open_flux_dialog() {
	if (!mk_current_batch) {
		frappe.msgprint(__("Select a batch first."));
		return;
	}

	var d = new frappe.ui.Dialog({
		title: __("Log Fluxing Event"),
		fields: [
			{
				fieldname: "temp_c",
				label: __("Temp (°C)"),
				fieldtype: "Float",
				precision: 1
			},
			{
				fieldname: "flux_type",
				label: __("Flux Type"),
				fieldtype: "Link",
				options: "Item"
			},
			{
				fieldname: "flux_qty_kg",
				label: __("Flux Qty (kg)"),
				fieldtype: "Float",
				precision: 3
			},
			{
				fieldname: "note",
				label: __("Note"),
				fieldtype: "Small Text"
			}
		],
		primary_action_label: __("Log Event"),
		primary_action: function(values) {
			frappe.call({
				method: "swynix_mes.swynix_mes.api.melting_kiosk.log_process_event",
				args: {
					batch_name: mk_current_batch,
					event_type: "Fluxing",
					temp_c: values.temp_c,
					flux_type: values.flux_type,
					flux_qty_kg: values.flux_qty_kg,
					note: values.note
				},
				callback: function() {
					d.hide();
					frappe.show_alert({
						message: __("Fluxing event logged"),
						indicator: "blue"
					});
					load_batch_detail(mk_current_batch);
				}
			});
		}
	});

	d.show();
}

function log_process_event(event_type) {
	if (!mk_current_batch) {
		frappe.msgprint(__("Select a batch first."));
		return;
	}

	frappe.call({
		method: "swynix_mes.swynix_mes.api.melting_kiosk.log_process_event",
		args: {
			batch_name: mk_current_batch,
			event_type: event_type
		},
		callback: function() {
			frappe.show_alert({
				message: __(event_type + " logged"),
				indicator: "green"
			});
			load_batch_detail(mk_current_batch);
		}
	});
}

function create_sample() {
	if (!mk_current_batch) {
		frappe.msgprint(__("Select a batch first."));
		return;
	}

	frappe.call({
		method: "swynix_mes.swynix_mes.api.melting_kiosk.create_sample",
		args: { batch_name: mk_current_batch },
		callback: function(r) {
			var sample_id = r.message && r.message.sample_id;
			frappe.show_alert({
				message: __("Sample {0} created. Lab can enter chemistry.", [sample_id || "S?"]),
				indicator: "orange"
			});
			load_batch_detail(mk_current_batch);
		}
	});
}

function mark_charging_complete() {
	if (!mk_current_batch) {
		frappe.msgprint(__("Select a batch first."));
		return;
	}

	frappe.confirm(
		__("Mark charging as complete? This will change status to Melting."),
		function() {
			frappe.call({
				method: "swynix_mes.swynix_mes.api.melting_kiosk.update_batch_status",
				args: {
					batch_name: mk_current_batch,
					new_status: "Melting"
				},
				callback: function() {
					frappe.show_alert({
						message: __("Charging complete. Status changed to Melting."),
						indicator: "orange"
					});
					load_batch_detail(mk_current_batch);
					refresh_batches();
				}
			});
		}
	);
}

function mark_ready_for_transfer() {
	if (!mk_current_batch) {
		frappe.msgprint(__("Select a batch first."));
		return;
	}

	frappe.confirm(
		__("Mark batch as Ready for Transfer?"),
		function() {
			frappe.call({
				method: "swynix_mes.swynix_mes.api.melting_kiosk.mark_ready_for_transfer",
				args: { batch_name: mk_current_batch },
				callback: function(r) {
					frappe.show_alert({
						message: __("Batch marked {0}", [r.message]),
						indicator: "yellow"
					});
					load_batch_detail(mk_current_batch);
					refresh_batches();
				}
			});
		}
	);
}

function complete_transfer() {
	if (!mk_current_batch) return;

	var tapped = $("#mk_tapped_weight").val();
	var fo_temp = $("#mk_fo_temp").val();
	var fo_press = $("#mk_fo_press").val();
	var dross = $("#mk_dross").val();
	var fuel = $("#mk_fuel").val();
	var note = $("#mk_transfer_note").val();

	if (!tapped) {
		frappe.msgprint(__("Please enter Tapped Metal weight."));
		return;
	}

	frappe.confirm(
		__("Complete transfer with tapped weight {0} MT?", [tapped]),
		function() {
			frappe.call({
				method: "swynix_mes.swynix_mes.api.melting_kiosk.complete_transfer",
				args: {
					batch_name: mk_current_batch,
					tapped_weight_mt: tapped,
					fo_temp_c: fo_temp,
					fo_pressure_bar: fo_press,
					dross_weight_kg: dross,
					energy_fuel_litre: fuel,
					note: note
				},
				callback: function(r) {
					frappe.show_alert({
						message: __("Batch transferred successfully! Yield: {0}%", [flt(r.message.yield_percent, 2)]),
						indicator: "green"
					});
					load_batch_detail(mk_current_batch);
					refresh_batches();
				}
			});
		}
	);
}
