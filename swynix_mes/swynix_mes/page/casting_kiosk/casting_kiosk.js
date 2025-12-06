// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

/**
 * Casting Kiosk - Shop Floor Interface for Casting Operations
 * 
 * Features:
 * - Left panel: Casting Plans for selected caster & date
 * - Center panel: Active casting run with coils table
 * - Right panel: Selected coil details
 */

// Global state
var ck_state = {
	caster: null,
	date: null,
	selected_plan: null,
	active_run: null,
	selected_coil: null,
	coils: []
};

// Status constants
const CK_PLAN_STATUS_COLORS = {
	"Planned": "planned",
	"Released": "released",
	"Melting": "melting",
	"Metal Ready": "metal-ready",
	"Casting": "casting",
	"Coils Complete": "coils-complete",
	"Not Produced": "not-produced"
};

frappe.pages["casting-kiosk"].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Casting Kiosk",
		single_column: true
	});

	$(frappe.render_template("casting_kiosk", {})).appendTo(page.body);

	// Initialize date to today
	ck_state.date = frappe.datetime.get_today();
	$("#ck_date").val(ck_state.date);

	init_ck_events();
	load_casters();
};

frappe.pages["casting-kiosk"].on_page_show = function() {
	if (ck_state.caster) {
		refresh_all();
	}
};

function init_ck_events() {
	// Caster selection
	$(document).on("change", "#ck_caster_select", function() {
		ck_state.caster = $(this).val();
		ck_state.selected_plan = null;
		ck_state.active_run = null;
		ck_state.selected_coil = null;
		refresh_all();
	});

	// Date selection
	$(document).on("change", "#ck_date", function() {
		ck_state.date = $(this).val();
		ck_state.selected_plan = null;
		ck_state.active_run = null;
		ck_state.selected_coil = null;
		refresh_all();
	});

	// Refresh button
	$(document).on("click", "#ck_btn_refresh", function() {
		refresh_all();
	});

	// Plan card click
	$(document).on("click", ".ck-plan-card", function() {
		var plan_name = $(this).data("plan");
		$(".ck-plan-card").removeClass("active");
		$(this).addClass("active");
		ck_state.selected_plan = plan_name;
		
		// Load run for this plan if exists
		load_run_for_plan(plan_name);
	});

	// Start Casting button
	$(document).on("click", ".ck-btn-start-casting", function(e) {
		e.stopPropagation();
		var plan_name = $(this).data("plan");
		start_casting(plan_name);
	});

	// View Run button
	$(document).on("click", ".ck-btn-view-run", function(e) {
		e.stopPropagation();
		var plan_name = $(this).data("plan");
		ck_state.selected_plan = plan_name;
		$(".ck-plan-card").removeClass("active");
		$(this).closest(".ck-plan-card").addClass("active");
		load_run_for_plan(plan_name);
	});

	// Create Coil button
	$(document).on("click", "#ck_btn_create_coil", function() {
		create_coil();
	});

	// Finish Coil button
	$(document).on("click", "#ck_btn_finish_coil", function() {
		finish_current_coil();
	});

	// Stop Run button
	$(document).on("click", "#ck_btn_stop_run", function() {
		stop_run();
	});

	// Coil row click
	$(document).on("click", ".ck-coil-row", function() {
		var coil_name = $(this).data("coil");
		$(".ck-coil-row").removeClass("selected");
		$(this).addClass("selected");
		ck_state.selected_coil = coil_name;
		load_coil_detail(coil_name);
	});

	// Open Coil QC button
	$(document).on("click", "#ck_btn_open_qc", function() {
		if (ck_state.selected_coil) {
			open_coil_qc(ck_state.selected_coil);
		}
	});

	// Mark Scrap button
	$(document).on("click", "#ck_btn_mark_scrap", function() {
		if (ck_state.selected_coil) {
			mark_coil_scrap(ck_state.selected_coil);
		}
	});

	// Update Coil Dimensions button
	$(document).on("click", "#ck_btn_update_dims", function() {
		if (ck_state.selected_coil) {
			open_update_dims_dialog(ck_state.selected_coil);
		}
	});

	// Open Mother Coil Doc button
	$(document).on("click", "#ck_btn_open_coil_doc", function() {
		if (ck_state.selected_coil) {
			frappe.set_route("Form", "Mother Coil", ck_state.selected_coil);
		}
	});
}

function load_casters() {
	frappe.call({
		method: "swynix_mes.swynix_mes.api.casting_kiosk.get_casters",
		callback: function(r) {
			var casters = r.message || [];
			var $select = $("#ck_caster_select");
			$select.empty();
			$select.append('<option value="">-- Select Caster --</option>');
			casters.forEach(function(c) {
				$select.append('<option value="' + c.name + '">' + 
					(c.caster_name || c.caster_id || c.name) + '</option>');
			});
		}
	});
}

function refresh_all() {
	load_plans();
	load_active_run();
	clear_coil_detail();
}

// ==================== PLANS ====================

function load_plans() {
	var $container = $("#ck_plans_list");
	
	if (!ck_state.caster) {
		$container.html(render_empty_state("fa-calendar", "Select a caster to see casting plans"));
		return;
	}

	frappe.call({
		method: "swynix_mes.swynix_mes.api.casting_kiosk.get_casting_plans",
		args: {
			caster: ck_state.caster,
			for_date: ck_state.date
		},
		callback: function(r) {
			var plans = r.message || [];
			render_plans(plans);
		}
	});
}

function render_plans(plans) {
	var $container = $("#ck_plans_list");
	
	if (!plans.length) {
		$container.html(render_empty_state("fa-calendar-o", "No casting plans for this date"));
		return;
	}

	var html = "";
	plans.forEach(function(p) {
		var status_class = CK_PLAN_STATUS_COLORS[p.status] || "planned";
		var is_active = ck_state.selected_plan === p.name ? " active" : "";
		
		// Format time
		var time_str = "";
		if (p.start_datetime) {
			var start_time = frappe.datetime.str_to_user(p.start_datetime).split(" ")[1] || "";
			var end_time = p.end_datetime ? (frappe.datetime.str_to_user(p.end_datetime).split(" ")[1] || "") : "";
			time_str = start_time + (end_time ? " → " + end_time : "");
		}

		// Determine button to show
		var btn_html = "";
		if (p.status === "Metal Ready") {
			btn_html = '<button class="btn btn-sm btn-primary ck-btn-start-casting" data-plan="' + p.name + '">' +
				'<i class="fa fa-play"></i> Start Casting</button>';
		} else if (p.status === "Casting") {
			btn_html = '<button class="btn btn-sm btn-default ck-btn-view-run" data-plan="' + p.name + '">' +
				'<i class="fa fa-eye"></i> View Run</button>';
		} else if (p.status === "Coils Complete") {
			btn_html = '<button class="btn btn-sm btn-success ck-btn-view-run" data-plan="' + p.name + '">' +
				'<i class="fa fa-check"></i> View Coils</button>';
		} else if (p.status === "Planned" || p.status === "Melting") {
			btn_html = '<button class="btn btn-sm btn-default" disabled title="Melting not ready">' +
				'<i class="fa fa-clock-o"></i> Waiting</button>';
		}

		html += '<div class="ck-plan-card' + is_active + '" data-plan="' + p.name + '">' +
			'<div class="plan-header">' +
				'<div>' +
					'<div class="plan-product">' + frappe.utils.escape_html(p.product_item || "No Product") + '</div>' +
					'<div class="plan-alloy">' + frappe.utils.escape_html(p.alloy || "-") + 
						(p.temper ? " / " + p.temper : "") + '</div>' +
				'</div>' +
				'<span class="ck-status ' + status_class + '">' + frappe.utils.escape_html(p.status || "Planned") + '</span>' +
			'</div>' +
			'<div class="plan-time"><i class="fa fa-clock-o"></i> ' + time_str + '</div>' +
			'<div class="plan-dims">' +
				'W: ' + (p.planned_width_mm || "-") + 'mm | ' +
				'G: ' + (p.planned_gauge_mm || "-") + 'mm | ' +
				'Wt: ' + (p.planned_weight_mt || "-") + ' MT' +
			'</div>' +
			'<div style="margin-top: 10px;">' + btn_html + '</div>' +
		'</div>';
	});
	
	$container.html(html);
}

// ==================== CASTING RUN ====================

function load_active_run() {
	var $container = $("#ck_run_area");
	
	if (!ck_state.caster) {
		$container.html(render_empty_state("fa-industry", "Select a caster to see active runs"));
		return;
	}

	frappe.call({
		method: "swynix_mes.swynix_mes.api.casting_kiosk.get_active_run",
		args: {
			caster: ck_state.caster,
			for_date: ck_state.date
		},
		callback: function(r) {
			if (r.message && r.message.run) {
				ck_state.active_run = r.message.run;
				ck_state.coils = r.message.coils || [];
				render_run(r.message);
			} else {
				ck_state.active_run = null;
				ck_state.coils = [];
				render_no_active_run();
			}
		}
	});
}

function load_run_for_plan(plan_name) {
	if (!plan_name) return;

	frappe.call({
		method: "swynix_mes.swynix_mes.api.casting_kiosk.get_run_for_plan",
		args: {
			plan_name: plan_name
		},
		callback: function(r) {
			if (r.message && r.message.run) {
				ck_state.active_run = r.message.run;
				ck_state.coils = r.message.coils || [];
				render_run(r.message);
			} else {
				// No run yet - show empty state with start button if plan is ready
				render_no_active_run();
			}
		}
	});
}

function render_run(data) {
	var run = data.run;
	var coils = data.coils || [];
	var plan = data.plan || {};
	
	var is_casting = run.status === "Casting";
	var is_completed = run.status === "Completed";
	
	// Run summary card
	var html = '<div class="ck-run-summary">' +
		'<div class="run-header">' +
			'<div class="run-title">' +
				'<i class="fa fa-industry" style="color: #7c3aed;"></i> ' +
				frappe.utils.escape_html(run.name) +
				' <span class="ck-status ' + (is_casting ? 'casting' : (is_completed ? 'coils-complete' : 'planned')) + '">' +
					run.status + '</span>' +
			'</div>' +
		'</div>' +
		'<div class="run-info-grid">' +
			'<div class="info-item">' +
				'<label>Plan</label>' +
				'<div class="value">' + frappe.utils.escape_html(run.casting_plan || "-") + '</div>' +
			'</div>' +
			'<div class="info-item">' +
				'<label>Alloy</label>' +
				'<div class="value">' + frappe.utils.escape_html(plan.alloy || "-") + '</div>' +
			'</div>' +
			'<div class="info-item">' +
				'<label>Product</label>' +
				'<div class="value">' + frappe.utils.escape_html(plan.product_item || "-") + '</div>' +
			'</div>' +
			'<div class="info-item">' +
				'<label>Temper</label>' +
				'<div class="value">' + frappe.utils.escape_html(plan.temper || "-") + '</div>' +
			'</div>' +
		'</div>' +
		'<div class="run-info-grid">' +
			'<div class="info-item">' +
				'<label>Planned Width</label>' +
				'<div class="value">' + (plan.planned_width_mm || "-") + ' mm</div>' +
			'</div>' +
			'<div class="info-item">' +
				'<label>Planned Gauge</label>' +
				'<div class="value">' + (plan.planned_gauge_mm || "-") + ' mm</div>' +
			'</div>' +
			'<div class="info-item">' +
				'<label>Planned Weight</label>' +
				'<div class="value">' + (plan.planned_weight_mt || "-") + ' MT</div>' +
			'</div>' +
			'<div class="info-item">' +
				'<label>Melting Batch</label>' +
				'<div class="value">' + frappe.utils.escape_html(run.melting_batch || "-") + '</div>' +
			'</div>' +
		'</div>' +
		'<div class="run-actions">';
	
	if (is_casting) {
		html += '<button class="btn btn-primary" id="ck_btn_create_coil">' +
			'<i class="fa fa-plus-circle"></i> Create Coil</button>';
		html += '<button class="btn btn-warning" id="ck_btn_finish_coil">' +
			'<i class="fa fa-check"></i> Finish Current Coil</button>';
		html += '<button class="btn btn-danger" id="ck_btn_stop_run">' +
			'<i class="fa fa-stop"></i> Stop Run</button>';
	} else if (!is_completed) {
		html += '<button class="btn btn-default" disabled>Run not active</button>';
	}
	
	html += '</div></div>';
	
	// Coils table
	html += '<div class="ck-coils-section">' +
		'<div class="section-header">' +
			'<h5><i class="fa fa-th-list"></i> Coils (' + coils.length + ')</h5>' +
			'<div>' +
				'<span style="font-size: 12px; color: #6b7280;">' +
					'Total: ' + flt(run.total_cast_weight || 0, 3) + ' MT | ' +
					'Scrap: ' + flt(run.total_scrap_weight || 0, 3) + ' MT' +
				'</span>' +
			'</div>' +
		'</div>' +
		'<div class="ck-coils-table-wrapper">';
	
	if (coils.length) {
		html += '<table class="ck-coils-table">' +
			'<thead><tr>' +
				'<th>#</th>' +
				'<th>Temp ID</th>' +
				'<th>Final ID</th>' +
				'<th>Start</th>' +
				'<th>End</th>' +
				'<th>Width</th>' +
				'<th>Gauge</th>' +
				'<th>Weight</th>' +
				'<th>QC Status</th>' +
			'</tr></thead><tbody>';
		
		coils.forEach(function(c, idx) {
			var qc_class = get_qc_status_class(c.qc_status);
			var row_class = c.is_scrap ? " scrap-row" : "";
			var selected_class = ck_state.selected_coil === c.name ? " selected" : "";
			
			html += '<tr class="ck-coil-row' + row_class + selected_class + '" data-coil="' + c.name + '">' +
				'<td>' + (idx + 1) + '</td>' +
				'<td><strong>' + frappe.utils.escape_html(c.temp_coil_id || "-") + '</strong></td>' +
				'<td>' + (c.coil_id ? '<span style="color: #10b981;">' + frappe.utils.escape_html(c.coil_id) + '</span>' : '—') + '</td>' +
				'<td>' + (c.cast_start_time ? format_time(c.cast_start_time) : "-") + '</td>' +
				'<td>' + (c.cast_end_time ? format_time(c.cast_end_time) : "-") + '</td>' +
				'<td>' + (c.actual_width_mm || c.planned_width_mm || "-") + '</td>' +
				'<td>' + (c.actual_gauge_mm || c.planned_gauge_mm || "-") + '</td>' +
				'<td>' + (c.actual_weight_mt || c.planned_weight_mt || "-") + '</td>' +
				'<td><span class="ck-status ' + qc_class + '">' + (c.qc_status || "Pending") + '</span>' +
					(c.is_scrap ? ' <i class="fa fa-trash text-danger"></i>' : '') + '</td>' +
			'</tr>';
		});
		
		html += '</tbody></table>';
	} else {
		html += render_empty_state("fa-th-list", "No coils created yet. Click 'Create Coil' to start.");
	}
	
	html += '</div></div>';
	
	$("#ck_run_area").html(html);
}

function render_no_active_run() {
	var html = '<div class="ck-run-summary">' +
		'<div class="ck-empty-state">' +
			'<i class="fa fa-industry"></i>' +
			'<p>No active casting run for this caster</p>' +
			'<p style="font-size: 12px; color: #9ca3af;">Select a "Metal Ready" plan from the left to start casting</p>' +
		'</div>' +
	'</div>';
	
	$("#ck_run_area").html(html);
}

function get_qc_status_class(status) {
	var map = {
		"Pending": "planned",
		"Approved": "coils-complete",
		"Correction Required": "released",
		"Rejected": "not-produced",
		"Hold": "melting"
	};
	return map[status] || "planned";
}

function format_time(datetime_str) {
	if (!datetime_str) return "-";
	try {
		var user_str = frappe.datetime.str_to_user(datetime_str);
		return user_str.split(" ")[1] || user_str;
	} catch(e) {
		return datetime_str;
	}
}

// ==================== COIL OPERATIONS ====================

function start_casting(plan_name) {
	if (!plan_name) {
		frappe.msgprint(__("Please select a plan first."));
		return;
	}

	frappe.confirm(
		__("<b>Start Casting?</b><br><br>" +
		   "This will create a Casting Run for the selected plan.<br>" +
		   "Make sure the metal is ready for transfer."),
		function() {
			frappe.call({
				method: "swynix_mes.swynix_mes.api.casting_kiosk.start_casting",
				args: { plan_name: plan_name },
				freeze: true,
				freeze_message: __("Starting casting run..."),
				callback: function(r) {
					if (r.message) {
						frappe.show_alert({
							message: __("Casting run {0} started!", [r.message.run_name]),
							indicator: "green"
						});
						ck_state.selected_plan = plan_name;
						refresh_all();
					}
				}
			});
		}
	);
}

function create_coil() {
	if (!ck_state.active_run) {
		frappe.msgprint(__("No active casting run. Start casting first."));
		return;
	}

	frappe.call({
		method: "swynix_mes.swynix_mes.api.casting_kiosk.create_coil",
		args: { 
			run_name: ck_state.active_run.name 
		},
		freeze: true,
		freeze_message: __("Creating coil..."),
		callback: function(r) {
			if (r.message) {
				frappe.show_alert({
					message: __("Coil {0} created!", [r.message.temp_coil_id]),
					indicator: "green"
				});
				ck_state.selected_coil = r.message.name;
				load_active_run();
				load_coil_detail(r.message.name);
			}
		}
	});
}

function finish_current_coil() {
	// Find the latest unfinished coil
	var unfinished = ck_state.coils.filter(function(c) {
		return c.cast_start_time && !c.cast_end_time;
	});
	
	if (!unfinished.length) {
		frappe.msgprint(__("No unfinished coil found. All coils have end times."));
		return;
	}
	
	var coil = unfinished[unfinished.length - 1]; // Get the most recent one
	
	// Open dialog for actual dimensions
	var d = new frappe.ui.Dialog({
		title: __("Finish Coil - {0}", [coil.temp_coil_id]),
		fields: [
			{
				fieldname: "actual_width_mm",
				label: __("Actual Width (mm)"),
				fieldtype: "Float",
				precision: 2,
				default: coil.planned_width_mm
			},
			{
				fieldname: "actual_gauge_mm",
				label: __("Actual Gauge (mm)"),
				fieldtype: "Float",
				precision: 3,
				default: coil.planned_gauge_mm
			},
			{
				fieldname: "actual_weight_mt",
				label: __("Actual Weight (MT)"),
				fieldtype: "Float",
				precision: 3,
				reqd: 1
			}
		],
		primary_action_label: __("Finish Coil"),
		primary_action: function(values) {
			frappe.call({
				method: "swynix_mes.swynix_mes.api.casting_kiosk.finish_coil",
				args: {
					coil_name: coil.name,
					actual_width_mm: values.actual_width_mm,
					actual_gauge_mm: values.actual_gauge_mm,
					actual_weight_mt: values.actual_weight_mt
				},
				callback: function(r) {
					d.hide();
					if (r.message) {
						frappe.show_alert({
							message: __("Coil {0} finished!", [coil.temp_coil_id]),
							indicator: "green"
						});
						load_active_run();
						if (ck_state.selected_coil === coil.name) {
							load_coil_detail(coil.name);
						}
					}
				}
			});
		}
	});
	d.show();
}

function stop_run() {
	if (!ck_state.active_run) {
		frappe.msgprint(__("No active run to stop."));
		return;
	}

	frappe.confirm(
		__("<b>Stop Casting Run?</b><br><br>" +
		   "This will complete the casting run.<br>" +
		   "Make sure all coils are finished and QC is done."),
		function() {
			frappe.call({
				method: "swynix_mes.swynix_mes.api.casting_kiosk.stop_run",
				args: { run_name: ck_state.active_run.name },
				freeze: true,
				freeze_message: __("Stopping run..."),
				callback: function(r) {
					if (r.message) {
						frappe.show_alert({
							message: __("Casting run completed!"),
							indicator: "green"
						});
						ck_state.active_run = null;
						refresh_all();
					}
				}
			});
		}
	);
}

// ==================== COIL DETAIL ====================

function load_coil_detail(coil_name) {
	if (!coil_name) {
		clear_coil_detail();
		return;
	}

	frappe.call({
		method: "swynix_mes.swynix_mes.api.casting_kiosk.get_coil_detail",
		args: { coil_name: coil_name },
		callback: function(r) {
			if (r.message) {
				render_coil_detail(r.message);
			} else {
				clear_coil_detail();
			}
		}
	});
}

function render_coil_detail(coil) {
	var qc_class = coil.qc_status === "Approved" ? "ok" : "";
	
	var html = '<div class="ck-coil-detail">' +
		'<h5><i class="fa fa-circle" style="color: #7c3aed;"></i> ' + 
			frappe.utils.escape_html(coil.temp_coil_id || coil.name) + '</h5>';
	
	// Identity section
	html += '<div class="ck-detail-section">' +
		'<div class="ck-detail-grid">' +
			'<div class="ck-detail-item">' +
				'<label>Temp ID</label>' +
				'<div class="value">' + frappe.utils.escape_html(coil.temp_coil_id || "-") + '</div>' +
			'</div>' +
			'<div class="ck-detail-item">' +
				'<label>Final ID</label>' +
				'<div class="value" style="color: ' + (coil.coil_id ? '#10b981' : '#9ca3af') + ';">' + 
					(coil.coil_id || "Not assigned") + '</div>' +
			'</div>' +
		'</div>' +
	'</div>';
	
	// Product info
	html += '<div class="ck-detail-section">' +
		'<div class="ck-detail-grid">' +
			'<div class="ck-detail-item">' +
				'<label>Alloy</label>' +
				'<div class="value">' + frappe.utils.escape_html(coil.alloy || "-") + '</div>' +
			'</div>' +
			'<div class="ck-detail-item">' +
				'<label>Temper</label>' +
				'<div class="value">' + frappe.utils.escape_html(coil.temper || "-") + '</div>' +
			'</div>' +
		'</div>' +
	'</div>';
	
	// Dimensions
	html += '<div class="ck-detail-section">' +
		'<label style="margin-bottom: 8px; display: block;">Dimensions (Planned → Actual)</label>' +
		'<div class="ck-detail-grid">' +
			'<div class="ck-detail-item">' +
				'<label>Width</label>' +
				'<div class="value">' + (coil.planned_width_mm || "-") + ' → ' + 
					(coil.actual_width_mm || "-") + ' mm</div>' +
			'</div>' +
			'<div class="ck-detail-item">' +
				'<label>Gauge</label>' +
				'<div class="value">' + (coil.planned_gauge_mm || "-") + ' → ' + 
					(coil.actual_gauge_mm || "-") + ' mm</div>' +
			'</div>' +
			'<div class="ck-detail-item">' +
				'<label>Weight</label>' +
				'<div class="value">' + (coil.planned_weight_mt || "-") + ' → ' + 
					(coil.actual_weight_mt || "-") + ' MT</div>' +
			'</div>' +
		'</div>' +
	'</div>';
	
	// QC Summary
	html += '<div class="ck-qc-summary ' + qc_class + '">' +
		'<div class="qc-status">' +
			'<i class="fa fa-' + (coil.qc_status === "Approved" ? 'check-circle' : 'exclamation-circle') + '"></i> ' +
			'QC: ' + (coil.qc_status || "Pending") +
		'</div>';
	
	if (coil.qc_deviation_summary) {
		html += '<div class="qc-deviations">' + frappe.utils.escape_html(coil.qc_deviation_summary) + '</div>';
	}
	
	html += '</div>';
	
	// Chemistry status from melting batch
	if (coil.chemistry_status) {
		var chem_class = coil.chemistry_status === "Within Spec" ? "ok" : "";
		html += '<div class="ck-qc-summary ' + chem_class + '">' +
			'<div class="qc-status"><i class="fa fa-flask"></i> Chemistry: ' + 
				frappe.utils.escape_html(coil.chemistry_status) + '</div>' +
		'</div>';
	}
	
	// Scrap info
	if (coil.is_scrap) {
		html += '<div class="ck-qc-summary" style="background: #fef2f2; border-left-color: #ef4444;">' +
			'<div class="qc-status" style="color: #b91c1c;">' +
				'<i class="fa fa-trash"></i> SCRAP COIL' +
			'</div>' +
			'<div class="qc-deviations">' + frappe.utils.escape_html(coil.scrap_reason || "No reason specified") + '</div>' +
		'</div>';
	}
	
	html += '</div>';
	
	// Actions
	html += '<div class="ck-coil-actions">' +
		'<button class="btn btn-primary" id="ck_btn_open_qc">' +
			'<i class="fa fa-clipboard"></i> Open Coil QC</button>' +
		'<button class="btn btn-default" id="ck_btn_update_dims">' +
			'<i class="fa fa-edit"></i> Update Dimensions</button>';
	
	if (!coil.is_scrap) {
		html += '<button class="btn btn-danger" id="ck_btn_mark_scrap">' +
			'<i class="fa fa-trash"></i> Mark as Scrap</button>';
	}
	
	html += '<button class="btn btn-default" id="ck_btn_open_coil_doc">' +
		'<i class="fa fa-external-link"></i> Open Full Record</button>' +
	'</div>';
	
	$("#ck_coil_detail_area").html(html);
}

function clear_coil_detail() {
	ck_state.selected_coil = null;
	$("#ck_coil_detail_area").html(
		'<div class="ck-empty-state">' +
			'<i class="fa fa-hand-pointer-o"></i>' +
			'<p>Select a coil to view details</p>' +
		'</div>'
	);
}

function open_coil_qc(coil_name) {
	// Check if Coil QC exists
	frappe.call({
		method: "swynix_mes.swynix_mes.api.casting_kiosk.get_or_create_coil_qc",
		args: { coil_name: coil_name },
		callback: function(r) {
			if (r.message) {
				frappe.set_route("Form", "Coil QC", r.message.name);
			}
		}
	});
}

function mark_coil_scrap(coil_name) {
	var d = new frappe.ui.Dialog({
		title: __("Mark Coil as Scrap"),
		fields: [
			{
				fieldname: "scrap_reason",
				label: __("Scrap Reason"),
				fieldtype: "Small Text",
				reqd: 1
			},
			{
				fieldname: "scrap_weight_mt",
				label: __("Scrap Weight (MT)"),
				fieldtype: "Float",
				precision: 3
			}
		],
		primary_action_label: __("Mark as Scrap"),
		primary_action: function(values) {
			frappe.call({
				method: "swynix_mes.swynix_mes.api.casting_kiosk.mark_coil_scrap",
				args: {
					coil_name: coil_name,
					scrap_reason: values.scrap_reason,
					scrap_weight_mt: values.scrap_weight_mt
				},
				callback: function(r) {
					d.hide();
					frappe.show_alert({
						message: __("Coil marked as scrap"),
						indicator: "orange"
					});
					load_active_run();
					load_coil_detail(coil_name);
				}
			});
		}
	});
	d.show();
}

function open_update_dims_dialog(coil_name) {
	// Get current values
	var coil = ck_state.coils.find(function(c) { return c.name === coil_name; });
	if (!coil) {
		frappe.msgprint(__("Coil not found"));
		return;
	}

	var d = new frappe.ui.Dialog({
		title: __("Update Coil Dimensions"),
		fields: [
			{
				fieldname: "actual_width_mm",
				label: __("Actual Width (mm)"),
				fieldtype: "Float",
				precision: 2,
				default: coil.actual_width_mm || coil.planned_width_mm
			},
			{
				fieldname: "actual_gauge_mm",
				label: __("Actual Gauge (mm)"),
				fieldtype: "Float",
				precision: 3,
				default: coil.actual_gauge_mm || coil.planned_gauge_mm
			},
			{
				fieldname: "actual_weight_mt",
				label: __("Actual Weight (MT)"),
				fieldtype: "Float",
				precision: 3,
				default: coil.actual_weight_mt
			}
		],
		primary_action_label: __("Update"),
		primary_action: function(values) {
			frappe.call({
				method: "swynix_mes.swynix_mes.api.casting_kiosk.update_coil_dimensions",
				args: {
					coil_name: coil_name,
					actual_width_mm: values.actual_width_mm,
					actual_gauge_mm: values.actual_gauge_mm,
					actual_weight_mt: values.actual_weight_mt
				},
				callback: function(r) {
					d.hide();
					frappe.show_alert({
						message: __("Dimensions updated"),
						indicator: "green"
					});
					load_active_run();
					load_coil_detail(coil_name);
				}
			});
		}
	});
	d.show();
}

// ==================== UTILITIES ====================

function render_empty_state(icon, message) {
	return '<div class="ck-empty-state">' +
		'<i class="fa ' + icon + '"></i>' +
		'<p>' + message + '</p>' +
	'</div>';
}

