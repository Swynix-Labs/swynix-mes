// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

var mk_current_furnace = null;
var mk_current_date = null;
var mk_current_batch = null;

// Active statuses that indicate a batch is occupying the furnace
const MK_ACTIVE_BATCH_STATUSES = [
	"Charging", "Melting", "Fluxing", "Sampling", "Correction", "Ready for Transfer"
];

/**
 * Show confirmation dialog for irreversible actions.
 * @param {string} title - The action title
 * @param {string} message - Description of what will happen
 * @param {function} yes_callback - Function to call if user confirms
 */
function confirm_irreversible_action(title, message, yes_callback) {
	frappe.confirm(
		`<b>${title}</b><br><br>${message}<br><br>` +
		`<div style="background: #fef3c7; padding: 10px; border-radius: 6px; margin-top: 8px;">` +
		`<i class="fa fa-exclamation-triangle" style="color: #b45309;"></i> ` +
		__("This action <b>cannot be undone</b>. Do you want to continue?") +
		`</div>`,
		function () {
			yes_callback();
		},
		function () {
			// User cancelled - do nothing
		}
	);
}

frappe.pages["melting-kiosk"].on_page_load = function (wrapper) {
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

frappe.pages["melting-kiosk"].on_page_show = function () {
	if (mk_current_furnace) {
		refresh_all();
	}
};

function init_mk_events() {
	$(document).on("change", "#mk_furnace_select", function () {
		mk_current_furnace = $(this).val();
		refresh_all();
	});

	$(document).on("change", "#mk_plan_date", function () {
		mk_current_date = $(this).val();
		refresh_all();
	});

	$(document).on("click", "#mk_btn_refresh", function () {
		refresh_all();
	});

	$(document).on("click", ".mk-batch-item", function () {
		var name = $(this).data("name");
		$(".mk-batch-item").removeClass("active");
		$(this).addClass("active");
		mk_current_batch = name;
		load_batch_detail(name);
	});

	// Casting Plan - Start Melting button
	$(document).on("click", ".mk-btn-start-from-plan", async function (e) {
		e.stopPropagation();
		var planName = $(this).data("plan");
		await confirm_and_start_from_plan(planName);
	});

	$(document).on("click", "#mk_btn_add_rm", function () {
		open_add_rm_dialog(false);
	});

	$(document).on("click", "#mk_btn_correction", function () {
		open_add_rm_dialog(true);
	});

	$(document).on("click", "#mk_btn_charging_complete", function () {
		mark_charging_complete();
	});

	$(document).on("click", "#mk_btn_burner_on", function () {
		log_process_event("Burner On");
	});

	$(document).on("click", "#mk_btn_fluxing", function () {
		open_flux_dialog();
	});

	$(document).on("click", "#mk_btn_sample", function () {
		create_sample();
	});

	$(document).on("click", "#mk_btn_ready_transfer", function () {
		mark_ready_for_transfer();
	});

	// QC Detail Panel - Close button
	$(document).on("click", "#mk-qc-detail-close", function () {
		$("#mk-qc-detail-panel").addClass("hide");
	});

	// Tab switching (Raw / Process / Spectro / Transfer) - custom JS, no route change
	$(document).on("click", "#mk_batch_tabs .mk-tab", function (e) {
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
		callback: function (r) {
			var furnaces = r.message || [];
			var $select = $("#mk_furnace_select");
			$select.empty();
			$select.append('<option value="">-- Select Furnace --</option>');
			furnaces.forEach(function (f) {
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
		callback: function (r) {
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
	plans.forEach(function (p) {
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

async function confirm_and_start_from_plan(planName) {
	if (!planName) return;

	// Check if furnace is free before starting
	if (mk_current_furnace) {
		try {
			await check_furnace_free(mk_current_furnace);
		} catch (e) {
			// Error already shown by check_furnace_free
			return;
		}
	}

	frappe.confirm(
		__("<b>Start Melting for this Casting Plan?</b><br><br>" +
			"<div style='background: #fef3c7; padding: 12px; border-radius: 6px; margin-bottom: 12px;'>" +
			"<i class='fa fa-exclamation-triangle' style='color: #b45309;'></i> " +
			"<b>Important:</b> Once you start melting:" +
			"<ul style='margin: 8px 0 0 20px; padding: 0;'>" +
			"<li>A Melting Batch will be created for this plan.</li>" +
			"<li>This action <b>cannot be undone</b>.</li>" +
			"<li>This Casting Plan <b>cannot be cancelled</b> after batch creation.</li>" +
			"</ul></div>" +
			"Do you want to continue?"),
		function () {
			frappe.call({
				method: "swynix_mes.swynix_mes.api.melting_kiosk.start_batch_from_cast_plan",
				args: { plan_name: planName },
				freeze: true,
				freeze_message: __("Creating Melting Batch..."),
				callback: function (r) {
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
		callback: function (r) {
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
			'<div style="font-size: 11px; color: #6c757d; margin-top: 8px;">Start a batch from the Casting Plan above</div>' +
			'</div>'
		);
		clear_batch_detail();
		return;
	}

	var html = '';
	batches.forEach(function (b) {
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
		callback: function (r) {
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

	// Furnace busy/free indicator
	var furnaceIndicator = "";
	if (is_batch_status_active(doc.status)) {
		furnaceIndicator = '<span class="mk-furnace-indicator mk-furnace-busy">' +
			'<i class="fa fa-fire"></i> Furnace Busy – Active Batch Running' +
			'</span>';
	} else {
		furnaceIndicator = '<span class="mk-furnace-indicator mk-furnace-free">' +
			'<i class="fa fa-check-circle"></i> Furnace Free' +
			'</span>';
	}

	$("#mk_batch_title").html(
		'<i class="fa fa-fire" style="color: #ef4444;"></i> ' +
		'<span>' + title + '</span> ' +
		'<span class="batch-status ' + statusClass + '">' + doc.status + '</span> ' +
		furnaceIndicator +
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
		// Check QC status to enable/disable transfer button
		check_qc_status_for_transfer(doc.name || mk_current_batch, $ready);
	} else if (status === "Charging") {
		$ready.prop("disabled", true);
	}
}

/**
 * Check QC status and update transfer button state.
 * Transfer is only allowed if QC is Approved/Within Spec.
 */
function check_qc_status_for_transfer(batch_name, $btn) {
	if (!batch_name) {
		$btn.prop("disabled", true);
		return;
	}
	
	frappe.call({
		method: "swynix_mes.swynix_mes.api.qc_kiosk.check_qc_for_transfer",
		args: { batch_name: batch_name },
		async: true,
		callback: function(r) {
			if (!r.message) {
				$btn.prop("disabled", true);
				return;
			}
			
			var qc_status = r.message.qc_status;
			var can_transfer = r.message.can_transfer;
			
			// Disable button if QC is not OK
			if (qc_status === "OK" && can_transfer) {
				$btn.prop("disabled", false);
				$btn.attr("title", "QC approved - Ready to transfer");
			} else if (qc_status === "Correction Required") {
				$btn.prop("disabled", true);
				$btn.attr("title", "QC Correction Required - Cannot transfer");
			} else if (qc_status === "Pending") {
				$btn.prop("disabled", true);
				$btn.attr("title", "QC Pending - Complete QC approval before transfer");
			} else {
				$btn.prop("disabled", true);
				$btn.attr("title", "QC status: " + qc_status);
			}
		}
	});
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

		items.forEach(function (row) {
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

	doc.raw_materials.forEach(function (r, idx) {
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

	doc.process_logs.forEach(function (r) {
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

// Global variable for spectro context
var mk_spectro_context = null;

function render_spectro_table(doc) {
	var $container = $("#mk_spectro_table");

	// Load spectro context with composition spec from backend
	load_spectro_context(doc.name || mk_current_batch);
}

async function load_spectro_context(batch_name) {
	/**
	 * Load spectro context (elements with specs + samples) from backend.
	 * Then render the spectro table.
	 */
	var $container = $("#mk_spectro_table");

	if (!batch_name) {
		$container.html(
			'<div class="mk-empty">' +
			'<div class="empty-icon"><i class="fa fa-flask"></i></div>' +
			'<div class="empty-text">No batch selected</div>' +
			'</div>'
		);
		return;
	}

	try {
		const r = await frappe.call({
			method: "swynix_mes.swynix_mes.api.melting_kiosk.get_spectro_context",
			args: { melting_batch: batch_name }
		});

		mk_spectro_context = r.message || { elements: [], samples: [], sum_rules: [] };
		render_spectro_table_from_context(mk_spectro_context);
	} catch (e) {
		console.error("Error loading spectro context:", e);
		$container.html(
			'<div class="mk-empty">' +
			'<div class="empty-icon"><i class="fa fa-exclamation-triangle"></i></div>' +
			'<div class="empty-text">Error loading spectro data</div>' +
			'</div>'
		);
	}
}

function check_value_within_spec(val, element) {
	/**
	 * Check if a value is within the element's specification.
	 * Returns: true = in spec, false = out of spec, null = unknown/no spec
	 */
	if (val == null || val === "" || val === "-") return null;

	var x = parseFloat(val);
	if (isNaN(x)) return null;

	var min_pct = element.min_pct;
	var max_pct = element.max_pct;

	// If no limits defined, can't check
	if (min_pct == null && max_pct == null) return null;

	// Check against limits
	if (min_pct != null && x < min_pct) return false;
	if (max_pct != null && x > max_pct) return false;

	return true;
}

function render_spectro_table_from_context(ctx) {
	/**
	 * Render spectro table from context data.
	 * Shows element headers with spec text and sample values with pass/fail coloring.
	 */
	var $container = $("#mk_spectro_table");
	var elements = ctx.elements || [];
	var samples = ctx.samples || [];
	var sum_rules = ctx.sum_rules || [];

	if (!samples.length) {
		// Show alloy info even with no samples
		var alloy_info = ctx.alloy ?
			'<div style="margin-bottom: 15px; padding: 10px; background: #f0f9ff; border-radius: 6px; font-size: 12px;">' +
			'<i class="fa fa-info-circle" style="color: #0284c7;"></i> ' +
			'Alloy: <b>' + frappe.utils.escape_html(ctx.alloy) + '</b>' +
			(ctx.composition_master ? ' | Composition: <b>' + frappe.utils.escape_html(ctx.composition_master) + '</b>' : '') +
			'</div>' : '';

		$container.html(
			alloy_info +
			'<div class="mk-empty">' +
			'<div class="empty-icon"><i class="fa fa-flask"></i></div>' +
			'<div class="empty-text">No spectro samples taken yet</div>' +
			'</div>'
		);
		return;
	}

	// Build header
	var html = '';

	// Alloy and composition master info
	if (ctx.alloy) {
		html += '<div style="margin-bottom: 12px; padding: 10px 15px; background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%); border-radius: 6px; display: flex; justify-content: space-between; align-items: center;">';
		html += '<div style="font-size: 13px;">';
		html += '<i class="fa fa-flask" style="color: #0284c7;"></i> ';
		html += 'Alloy: <b>' + frappe.utils.escape_html(ctx.alloy) + '</b>';
		if (ctx.composition_master) {
			html += ' <span style="color: #64748b;">|</span> Spec: <b>' + frappe.utils.escape_html(ctx.composition_master) + '</b>';
		}
		html += '</div>';

		// Show sum rules if any
		if (sum_rules.length) {
			html += '<div style="font-size: 11px; color: #475569;">';
			sum_rules.forEach(function (sr, idx) {
				if (idx > 0) html += ' | ';
				html += '<span title="Sum rule">' + frappe.utils.escape_html(sr.label || '') + '</span>';
			});
			html += '</div>';
		}
		html += '</div>';
	}

	// Table
	html += '<table class="mk-table mk-spectro-table">';

	// Header row with element names and specs
	html += '<thead><tr>';
	html += '<th style="min-width: 70px;">Sample</th>';
	html += '<th style="min-width: 100px;">Time</th>';

	elements.forEach(function (el) {
		var tooltip = '';
		if (el.condition_text) {
			tooltip = ' title="' + frappe.utils.escape_html(el.condition_text) + '"';
		}

		html += '<th class="mk-element-header"' + tooltip + '>';
		html += '<div class="mk-element-label">' + frappe.utils.escape_html(el.label || el.code) + ' %</div>';
		html += '<div class="mk-element-spec">Std: ' + frappe.utils.escape_html(el.spec_text || '-') + '</div>';
		html += '</th>';
	});

	html += '<th style="min-width: 80px;">Status</th>';
	html += '<th style="min-width: 100px;">QC Status</th>';
	html += '<th style="min-width: 120px;">QC Summary</th>';
	html += '<th style="min-width: 60px;">Corr?</th>';
	html += '</tr></thead>';

	// Body rows
	html += '<tbody>';
	samples.forEach(function (s) {
		// Count elements out of spec for this sample
		var out_of_spec_count = 0;
		var checked_count = 0;

		elements.forEach(function (el) {
			var val = (s.values && s.values[el.code] != null) ? s.values[el.code] : null;
			var result = check_value_within_spec(val, el);
			if (result === false) out_of_spec_count++;
			if (result !== null) checked_count++;
		});

		// Determine row status
		var row_class = '';
		if (out_of_spec_count > 0) {
			row_class = 'mk-row-has-issues';
		}

		html += '<tr class="' + row_class + '" data-sample-name="' + frappe.utils.escape_html(s.name || '') + '" style="cursor: pointer;">';

		// Sample ID with link to QC Kiosk (includes batch and sample params)
		var qc_kiosk_url = '/app/qc-kiosk?batch=' + encodeURIComponent(mk_current_batch || '') +
			'&sample=' + encodeURIComponent(s.sample_id || '');
		html += '<td class="text-bold">';
		html += '<a href="' + qc_kiosk_url + '" target="_blank" style="color: #0ea5e9;" title="Open in QC Kiosk" onclick="event.stopPropagation();">';
		html += frappe.utils.escape_html(s.sample_id || "-");
		html += '</a></td>';

		html += '<td style="font-size: 11px;">' + (s.sample_time ? frappe.datetime.str_to_user(s.sample_time) : "-") + '</td>';

		// Element values with pass/fail coloring
		elements.forEach(function (el) {
			var val = (s.values && s.values[el.code] != null) ? s.values[el.code] : null;
			var display_val = (val != null && val !== "") ? flt(val, 4) : "-";
			var result = check_value_within_spec(val, el);

			var cell_class = 'mk-sample-val';
			if (result === true) {
				cell_class += ' mk-in-spec';
			} else if (result === false) {
				cell_class += ' mk-out-of-spec';
			}

			html += '<td class="' + cell_class + '" data-element="' + el.code + '">' + display_val + '</td>';
		});

		// Status - use QC status if available, otherwise use overall_result
		var qc_status = s.qc_status || s.overall_result || s.result_status || "Pending";
		var status_style = "background: #f3f4f6; color: #4b5563;";
		var status_display = "Pending";

		if (qc_status === "Within Spec" || qc_status === "In Spec" || qc_status === "Within Limit") {
			status_style = "background: #d1fae5; color: #047857;";
			status_display = "OK";
		} else if (qc_status === "Out of Spec" || qc_status === "Out of Limit") {
			status_style = "background: #fee2e2; color: #b91c1c;";
			status_display = "Out of Spec";
		} else if (qc_status === "Correction Required") {
			status_style = "background: #fef3c7; color: #b45309;";
			status_display = "Correction";
		}

		// Also show sample status (Accepted, In Lab, etc.)
		var sample_status = s.status || "Pending";
		var sample_badge = "";
		if (sample_status === "Accepted") {
			sample_badge = '<span style="background: #d1fae5; color: #047857; padding: 2px 6px; border-radius: 4px; font-size: 9px; margin-left: 4px;">✓</span>';
		} else if (sample_status === "In Lab") {
			sample_badge = '<span style="background: #dbeafe; color: #1d4ed8; padding: 2px 6px; border-radius: 4px; font-size: 9px; margin-left: 4px;">Lab</span>';
		}

		// Show deviation summary as tooltip/chip if available
		var deviation_chip = "";
		if (s.qc_deviation_summary && s.qc_deviation_summary !== "No deviations") {
			var deviation_count = (s.qc_deviation_summary.match(/,/g) || []).length + 1;
			deviation_chip = '<span style="background: #fee2e2; color: #b91c1c; padding: 2px 6px; border-radius: 4px; font-size: 9px; margin-left: 4px;" title="' +
				frappe.utils.escape_html(s.qc_deviation_summary) + '">' + deviation_count + ' dev</span>';
		}

		html += '<td><span style="' + status_style + ' padding: 2px 8px; border-radius: 4px; font-size: 10px; white-space: nowrap;">' +
			frappe.utils.escape_html(status_display) + '</span>' + sample_badge + deviation_chip + '</td>';

		// QC Status column
		var qc_status = s.qc_status || "Pending";
		var qc_status_class = "badge-secondary";
		var qc_status_text = qc_status;
		if (qc_status === "Within Spec") {
			qc_status_class = "badge-success";
			qc_status_text = "Within Spec";
		} else if (qc_status === "Out of Spec") {
			qc_status_class = "badge-danger";
			qc_status_text = "Out of Spec";
		} else if (qc_status === "Correction Required") {
			qc_status_class = "badge-warning";
			qc_status_text = "Correction";
		} else if (qc_status === "Rejected") {
			qc_status_class = "badge-danger";
			qc_status_text = "Rejected";
		}
		html += '<td><span class="badge ' + qc_status_class + '" style="font-size: 10px;">' +
			frappe.utils.escape_html(qc_status_text) + '</span></td>';

		// QC Summary column
		var qc_deviation_count = s.qc_deviation_count || 0;
		var qc_summary_html = '';
		if (qc_deviation_count > 0) {
			qc_summary_html = '<span class="text-danger mk-qc-summary-link" style="cursor: pointer; font-size: 11px;" ' +
				'data-sample-name="' + frappe.utils.escape_html(s.name) + '">' +
				'<i class="fa fa-exclamation-triangle"></i> ' + qc_deviation_count + ' deviation' +
				(qc_deviation_count > 1 ? 's' : '') + ' – view</span>';
		} else if (qc_status === "Within Spec") {
			qc_summary_html = '<span class="text-success" style="font-size: 11px;">' +
				'<i class="fa fa-check-circle"></i> Within Spec</span>';
		} else {
			qc_summary_html = '<span class="text-muted" style="font-size: 11px;">Pending</span>';
		}
		html += '<td>' + qc_summary_html + '</td>';

		// Correction required
		html += '<td>';
		if (s.correction_required || s.status === "Correction Required" || qc_status === "Correction Required") {
			html += '<span style="background: #fef3c7; color: #b45309; padding: 2px 6px; border-radius: 4px; font-size: 10px;">Yes</span>';
		}
		html += '</td>';

		html += '</tr>';

		// Show deviation details row if QC has processed this sample
		var has_qc_deviations = false;
		var deviation_details = [];

		if (s.qc_deviation_detail) {
			try {
				var deviations = JSON.parse(s.qc_deviation_detail);
				if (deviations && deviations.length > 0) {
					has_qc_deviations = true;
					deviation_details = deviations;
				}
			} catch (e) {
				// Invalid JSON, ignore
			}
		}

		// Show summary row with deviation specs
		if (has_qc_deviations || out_of_spec_count > 0) {
			html += '<tr class="mk-spec-summary-row">';
			html += '<td colspan="' + (elements.length + 6) + '">';  // Updated colspan for new columns

			if (has_qc_deviations) {
				// Show exact QC deviation specs
				html += '<div style="padding: 10px 12px; background: #fef2f2; border-left: 3px solid #ef4444; border-radius: 4px;">';
				html += '<div style="color: #dc2626; font-size: 12px; font-weight: 600; margin-bottom: 8px;">';
				html += '<i class="fa fa-exclamation-triangle"></i> QC Deviation Specs:';
				html += '</div>';
				html += '<div style="display: flex; flex-wrap: wrap; gap: 8px;">';

				deviation_details.forEach(function (dev) {
					var severity_class = dev.severity === "high" ? "bad" : (dev.severity === "medium" ? "warn" : "good");
					var border_color = severity_class === "bad" ? "#ef4444" : (severity_class === "warn" ? "#f59e0b" : "#10b981");
					var text_color = severity_class === "bad" ? "#b91c1c" : (severity_class === "warn" ? "#b45309" : "#047857");

					html += '<div class="deviation-card ' + severity_class + '" style="border-left-color: ' + border_color + ';">';
					html += '<strong style="color: ' + text_color + '; display: block; margin-bottom: 2px;">' +
						frappe.utils.escape_html(dev.label || dev.code || "") + '</strong>';
					html += '<small style="color: #64748b; display: block;">Expected: <strong>' + frappe.utils.escape_html(dev.expected || "") +
						'</strong>, Actual: <strong style="color: ' + text_color + ';">' + frappe.utils.escape_html(dev.actual || "") + '</strong></small>';
					html += '</div>';
				});

				html += '</div>';
				html += '</div>';
			} else if (out_of_spec_count > 0) {
				// Fallback: show element count if no QC deviations available
				html += '<span style="color: #dc2626; font-size: 11px;"><i class="fa fa-exclamation-triangle"></i> ';
				html += out_of_spec_count + ' element(s) out of spec</span>';
			}

			html += '</td></tr>';
		}
	});

	html += '</tbody></table>';

	// Add QC Kiosk link with batch parameter
	var batch_for_qc = mk_current_batch || '';
	html += '<div style="margin-top: 12px; text-align: right;">';
	html += '<a href="/app/qc-kiosk?batch=' + encodeURIComponent(batch_for_qc) + '" target="_blank" class="btn btn-xs btn-default">';
	html += '<i class="fa fa-external-link"></i> Open QC Kiosk';
	html += '</a></div>';

	$container.html(html);

	// Bind row click handlers for QC feedback
	bind_spectro_row_clicks();
	bind_qc_summary_links();
}

function bind_qc_summary_links() {
	$(".mk-qc-summary-link").off("click").on("click", function (e) {
		e.stopPropagation();
		var sample_name = $(this).data("sample-name");
		if (sample_name) {
			// Find sample in context
			var sample_data = null;
			if (mk_spectro_context && mk_spectro_context.samples) {
				sample_data = mk_spectro_context.samples.find(function (s) {
					return s.name === sample_name;
				});
			}

			if (sample_data) {
				show_qc_detail_popup(sample_data);
			} else {
				// Load from API if not in context
				load_qc_feedback(sample_name);
			}

			// Highlight the row
			$("#mk_spectro_table tbody tr").removeClass("table-active");
			$(this).closest("tr").addClass("table-active");
		}
	});
}

function show_qc_detail_popup(sample_data) {
	if (!sample_data) return;

	// Parse deviation messages
	var messages = [];
	if (sample_data.qc_deviation_summary && sample_data.qc_deviation_summary.trim()) {
		// Split by newline
		sample_data.qc_deviation_summary.split(/\r?\n/).forEach(function (line) {
			if (line && line.trim()) {
				messages.push(line.trim());
			}
		});
	}

	// Build status HTML
	var qc_status = sample_data.qc_status || "Pending";
	var status_class = "status-pending";
	if (qc_status === "Within Spec") {
		status_class = "status-approved";
	} else if (qc_status === "Correction Required") {
		status_class = "status-correction";
	} else if (qc_status === "Rejected" || qc_status === "Out of Spec") {
		status_class = "status-rejected";
	}

	var status_html = '<span class="status-pill ' + status_class + '">' +
		frappe.utils.escape_html(qc_status) + '</span>';

	// Build deviations HTML
	var dev_html = '';
	if (messages.length === 0) {
		dev_html = '<div class="text-success" style="padding: 10px; background: #f0fdf4; border-radius: 6px;">' +
			'<i class="fa fa-check-circle"></i> All elements within specification.</div>';
	} else {
		dev_html = '<div style="max-height: 300px; overflow-y: auto;">';
		messages.forEach(function (msg) {
			dev_html += '<div class="qc-dev-line" style="margin-bottom: 6px; padding: 8px 10px; background: #fef2f2; border-left: 3px solid #ef4444; border-radius: 4px; font-size: 12px;">' +
				'<i class="fa fa-exclamation-triangle text-danger"></i> ' +
				frappe.utils.escape_html(msg) + '</div>';
		});
		dev_html += '</div>';
	}

	// Build updated by info
	var updated_info = '';
	if (sample_data.qc_last_updated_by) {
		updated_info = '<div class="text-muted" style="font-size: 11px; margin-top: 10px;">' +
			'Last updated by <strong>' + frappe.utils.escape_html(sample_data.qc_last_updated_by) + '</strong>';
		if (sample_data.qc_last_updated_on) {
			updated_info += ' on ' + frappe.datetime.str_to_user(sample_data.qc_last_updated_on);
		}
		updated_info += '</div>';
	}

	// Create dialog
	var d = new frappe.ui.Dialog({
		title: 'QC Details – ' + frappe.utils.escape_html(sample_data.sample_id || ''),
		size: 'large',
		fields: [
			{
				fieldtype: 'HTML',
				fieldname: 'qc_content'
			}
		],
		primary_action_label: 'Open in QC Kiosk',
		primary_action: function () {
			var url = '/app/qc-kiosk?batch=' + encodeURIComponent(mk_current_batch || '') +
				'&sample=' + encodeURIComponent(sample_data.sample_id || '');
			window.open(url, '_blank');
		}
	});

	// Set HTML content
	var html = '<div style="padding: 10px;">';

	// Status row
	html += '<div style="margin-bottom: 16px;">';
	html += '<label class="text-muted" style="font-size: 11px; display: block; margin-bottom: 4px;">QC Status</label>';
	html += status_html;
	html += '</div>';

	// Deviations section
	html += '<div style="margin-bottom: 16px;">';
	html += '<label class="text-muted" style="font-size: 11px; display: block; margin-bottom: 8px;">Specification Deviations (' + messages.length + ')</label>';
	html += dev_html;
	html += '</div>';

	// QC Comment section
	html += '<div style="margin-bottom: 10px;">';
	html += '<label class="text-muted" style="font-size: 11px; display: block; margin-bottom: 4px;">QC Comment / Instruction to Melting</label>';
	html += '<div style="padding: 10px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; min-height: 60px;">';
	html += sample_data.qc_comment ? frappe.utils.escape_html(sample_data.qc_comment) : '<span class="text-muted">No comment provided.</span>';
	html += '</div>';
	html += '</div>';

	// Updated info
	html += updated_info;

	html += '</div>';

	d.fields_dict.qc_content.$wrapper.html(html);
	d.show();
}

function bind_spectro_row_clicks() {
	$("#mk_spectro_table tbody tr").off("click").on("click", function () {
		var sample_name = $(this).data("sample-name");
		if (sample_name) {
			// Load from context data for quick display
			if (mk_spectro_context && mk_spectro_context.samples) {
				var sample_data = mk_spectro_context.samples.find(function (s) {
					return s.name === sample_name;
				});
				if (sample_data) {
					render_qc_detail_panel(sample_data);
				}
			}
			// Also load detailed feedback via API
			load_qc_feedback(sample_name);
			$(this).addClass("table-active").siblings().removeClass("table-active");
		}
	});
}

function load_qc_feedback(sample_name) {
	if (!sample_name) {
		$("#mk-qc-feedback").addClass("hide");
		$("#mk-qc-detail-panel").addClass("hide");
		return;
	}

	// Load from context data if available, otherwise call API
	var sample_data = null;
	if (mk_spectro_context && mk_spectro_context.samples) {
		sample_data = mk_spectro_context.samples.find(function (s) {
			return s.name === sample_name;
		});
	}

	if (sample_data) {
		// Use context data for quick display
		render_qc_detail_panel(sample_data);
	}

	// Also load detailed feedback via API
	frappe.call({
		method: "swynix_mes.swynix_mes.api.melting_kiosk.get_sample_qc_feedback",
		args: { sample_name: sample_name },
		freeze: false,
		callback: function (r) {
			if (!r.message) {
				$("#mk-qc-feedback").addClass("hide");
				return;
			}

			var data = r.message;

			// Show header
			$("#mk-qc-feedback").removeClass("hide");
			$("#mk-qc-sample-label").text(data.sample_id || data.sample_name || "");
			$("#mk-qc-batch").text(data.batch || "");
			$("#mk-qc-alloy").text(data.alloy || "");
			$("#mk-qc-product").text(data.product || "");
			$("#mk-qc-furnace").text(data.furnace || "");

			// Status badge
			var $badge = $("#mk-qc-status-badge");
			$badge.removeClass().addClass("badge");
			var label = data.qc_status || "Pending";
			var cls = "badge-secondary";
			if (label === "Within Spec") {
				cls = "badge-success";
			} else if (label === "Out of Spec") {
				cls = "badge-danger";
			} else if (label === "Correction Required") {
				cls = "badge-warning";
			}
			$badge.addClass(cls).text(label);

			// Comment
			$("#mk-qc-comment").text(data.qc_comment || "No specific instructions from QC.");

			// Deviations
			var $list = $("#mk-qc-deviation-list").empty();
			if (!data.deviations || !data.deviations.length) {
				$("<div class='qc-dev-card good'>No deviations. Sample within spec.</div>").appendTo($list);
			} else {
				data.deviations.forEach(function (dev) {
					var cls = dev.severity === "high" ? "bad" : (dev.severity === "medium" ? "warn" : "good");
					var $card = $("<div class='qc-dev-card " + cls + "'>");
					$card.append($("<strong>").text(dev.label || dev.code || ""));
					$card.append($("<br/>"));
					$card.append($("<small>").text("Expected: " + (dev.expected || "") + ", actual: " + (dev.actual || "")));
					$list.append($card);
				});
			}
		}
	});
}

function render_qc_detail_panel(sample_data) {
	if (!sample_data) {
		$("#mk-qc-detail-panel").addClass("hide");
		return;
	}

	$("#mk-qc-detail-panel").removeClass("hide");
	$("#mk-qc-detail-sample-id").text(sample_data.sample_id || "");

	// Render deviations
	var $deviations = $("#mk-qc-detail-deviations");
	$deviations.empty();

	if (sample_data.qc_deviation_summary && sample_data.qc_deviation_summary.trim()) {
		var deviation_lines = sample_data.qc_deviation_summary.split("\n").filter(function (line) {
			return line.trim().length > 0;
		});

		if (deviation_lines.length > 0) {
			$deviations.html('<label class="text-muted small mb-2">Specification Deviations</label>');
			var $list = $('<ul class="list-unstyled" style="margin-bottom: 0;"></ul>');

			deviation_lines.forEach(function (line) {
				$list.append('<li class="mb-1"><i class="fa fa-exclamation-circle text-danger"></i> ' +
					frappe.utils.escape_html(line) + '</li>');
			});

			$deviations.append($list);
		} else {
			$deviations.html('<div class="text-success"><i class="fa fa-check-circle"></i> No deviations. Sample within spec.</div>');
		}
	} else {
		$deviations.html('<div class="text-muted"><i class="fa fa-info-circle"></i> No QC evaluation available yet.</div>');
	}

	// Render comment
	$("#mk-qc-detail-comment").text(sample_data.qc_comment || "No specific instructions from QC.");

	// Render last updated info
	var updated_by = sample_data.qc_last_updated_by || "N/A";
	var updated_on = sample_data.qc_last_updated_on ?
		frappe.datetime.str_to_user(sample_data.qc_last_updated_on) : "N/A";
	$("#mk-qc-detail-updated-by").text(updated_by);
	$("#mk-qc-detail-updated-on").text(updated_on);
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
		$("#mk_btn_complete_transfer").on("click", function () {
			complete_transfer();
		});
	}
}

async function check_furnace_free(furnace) {
	/**
	 * Check if furnace is free (no active batch running).
	 * Throws error if furnace is busy.
	 */
	const r = await frappe.call({
		method: "swynix_mes.swynix_mes.api.melting_kiosk.check_furnace_availability",
		args: { furnace: furnace }
	});

	if (r.message && !r.message.is_free) {
		frappe.throw(
			__("<b>Furnace Busy</b><br><br>" +
				"Furnace <b>{0}</b> already has an active batch <b>{1}</b> (Status: {2}).<br><br>" +
				"Complete or Transfer the existing batch before starting a new one.",
				[furnace, r.message.active_batch, r.message.active_status])
		);
	}

	return true;
}

function is_batch_status_active(status) {
	/**
	 * Check if a batch status indicates the batch is active (occupying furnace).
	 */
	return MK_ACTIVE_BATCH_STATUSES.includes(status);
}

async function open_new_batch_dialog() {
	if (!mk_current_furnace) {
		frappe.msgprint(__("Please select a furnace first."));
		return;
	}

	// Check if furnace is free before opening dialog
	try {
		await check_furnace_free(mk_current_furnace);
	} catch (e) {
		// Error already shown by check_furnace_free
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
				label: __("Charge Mix Ratio"),
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
		primary_action: function (values) {
			frappe.call({
				method: "swynix_mes.swynix_mes.api.melting_kiosk.create_melting_batch",
				args: { data: values },
				callback: function (r) {
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

	d.fields_dict.alloy.get_query = function () {
		return { filters: { item_group: "Alloy" } };
	};

	d.fields_dict.product_item.get_query = function () {
		return { filters: { item_group: "Product" } };
	};

	d.fields_dict.charge_mix_recipe.get_query = function () {
		var alloy = d.get_value("alloy");
		var filters = { is_active: 1, docstatus: 1 };
		if (alloy) filters.alloy = alloy;
		return { filters: filters };
	};

	d.show();
}

function check_batch_is_active_for_action(action_name) {
	/**
	 * Check if current batch is in an active status that allows actions.
	 * Shows error and returns false if batch is not active.
	 */
	if (!mk_current_batch_detail) {
		frappe.msgprint(__("No batch data loaded. Please select a batch first."));
		return false;
	}

	var status = mk_current_batch_detail.status;
	if (!is_batch_status_active(status)) {
		frappe.msgprint({
			title: __("Action Not Allowed"),
			message: __("Cannot perform <b>{0}</b> action.<br><br>" +
				"The batch status is <b>{1}</b>.<br>" +
				"Actions are only allowed when batch is in active status: {2}",
				[action_name, status, MK_ACTIVE_BATCH_STATUSES.join(", ")]),
			indicator: "orange"
		});
		return false;
	}
	return true;
}

function open_add_rm_dialog(is_correction) {
	if (!mk_current_batch) {
		frappe.msgprint(__("Select a batch first."));
		return;
	}

	// For corrections, check if batch is in active status
	if (is_correction && !check_batch_is_active_for_action("Correction")) {
		return;
	}

	// Show confirmation for corrections
	if (is_correction) {
		confirm_irreversible_action(
			__("Alloy Correction"),
			__("You are about to add an <b>Alloy Correction</b> (chemical addition) for this batch.<br>" +
				"This will be recorded in the process log and raw materials."),
			function () {
				_open_add_rm_dialog_confirmed(true);
			}
		);
		return;
	}

	// For regular raw material addition, open dialog directly
	_open_add_rm_dialog_confirmed(is_correction);
}

function _open_add_rm_dialog_confirmed(is_correction) {
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
		primary_action: function (values) {
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
				callback: function () {
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

	// Check if batch is in active status
	if (!check_batch_is_active_for_action("Fluxing")) {
		return;
	}

	// Show confirmation first
	confirm_irreversible_action(
		__("Fluxing"),
		__("You are about to log a <b>Fluxing</b> event for this melting batch.<br>" +
			"This will record flux addition to the melt."),
		function () {
			_open_flux_dialog_confirmed();
		}
	);
}

function _open_flux_dialog_confirmed() {
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
		primary_action: function (values) {
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
				callback: function () {
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

	// Check if batch is in active status
	if (!check_batch_is_active_for_action(event_type)) {
		return;
	}

	// Show confirmation for Burner Start
	if (event_type === "Burner On") {
		confirm_irreversible_action(
			__("Burner Start"),
			__("You are about to log <b>Burner Start</b> for this melting batch.<br>" +
				"This marks the beginning of the melting process."),
			function () {
				_log_process_event_confirmed(event_type);
			}
		);
	} else {
		// Other events - log directly
		_log_process_event_confirmed(event_type);
	}
}

function _log_process_event_confirmed(event_type) {
	frappe.call({
		method: "swynix_mes.swynix_mes.api.melting_kiosk.log_process_event",
		args: {
			batch_name: mk_current_batch,
			event_type: event_type
		},
		callback: function () {
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

	// Check if batch is in active status
	if (!check_batch_is_active_for_action("Sample")) {
		return;
	}

	// Show confirmation first
	confirm_irreversible_action(
		__("Take Spectro Sample"),
		__("You are about to register a new <b>Spectro Sample</b> (S1, S2, etc.).<br>" +
			"This will create a sample record for lab analysis."),
		function () {
			_create_sample_confirmed();
		}
	);
}

function _create_sample_confirmed() {
	frappe.call({
		method: "swynix_mes.swynix_mes.api.melting_kiosk.create_sample",
		args: { batch_name: mk_current_batch },
		callback: function (r) {
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

	confirm_irreversible_action(
		__("Charging Complete"),
		__("You are about to mark <b>Charging as Complete</b>.<br>" +
			"This will change the batch status to <b>Melting</b>."),
		function () {
			frappe.call({
				method: "swynix_mes.swynix_mes.api.melting_kiosk.update_batch_status",
				args: {
					batch_name: mk_current_batch,
					new_status: "Melting"
				},
				callback: function () {
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

	confirm_irreversible_action(
		__("Mark Ready for Transfer"),
		__("You are about to mark this batch as <b>Ready for Transfer</b> to Holder.<br>" +
			"This indicates the melting process is complete and metal is ready to be transferred."),
		function () {
			frappe.call({
				method: "swynix_mes.swynix_mes.api.melting_kiosk.mark_ready_for_transfer",
				args: { batch_name: mk_current_batch },
				callback: function (r) {
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

	confirm_irreversible_action(
		__("Transfer Metal"),
		__("You are about to <b>complete this batch</b> and transfer metal to Holder.<br>" +
			"Tapped weight: <b>{0} MT</b><br><br>" +
			"This will finalize the melting batch and cannot be reversed.", [tapped]),
		function () {
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
				callback: function (r) {
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
