// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

let mk_current_furnace = null;
let mk_current_date = null;
let mk_current_batch = null;

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
		refresh_batches();
	}
};

function init_mk_events() {
	$(document).on("change", "#mk_furnace_select", function() {
		mk_current_furnace = $(this).val();
		refresh_batches();
	});

	$(document).on("change", "#mk_plan_date", function() {
		mk_current_date = $(this).val();
		refresh_batches();
	});

	$(document).on("click", "#mk_btn_refresh", function() {
		refresh_batches();
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

function refresh_batches() {
	if (!mk_current_furnace) {
		$("#mk_batch_list_container").html('<div class="text-center text-muted" style="padding: 40px;"><i class="fa fa-hand-pointer-o fa-3x"></i><p style="margin-top: 15px;">Select a furnace to see batches</p></div>');
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
		$container.html('<div class="text-center text-muted" style="padding: 40px;"><i class="fa fa-inbox fa-3x"></i><p style="margin-top: 15px;">No batches for this date</p><button class="btn btn-primary btn-sm" id="mk_btn_new_batch_empty"><i class="fa fa-plus"></i> Create First Batch</button></div>');
		clear_batch_detail();
		$("#mk_btn_new_batch_empty").on("click", function() {
			open_new_batch_dialog();
		});
		return;
	}

	var html = '<div class="list-group">';
	batches.forEach(function(b) {
		var label = b.melting_batch_id || b.name;
		var status_class = get_status_class(b.status);
		var subtitle = (b.alloy || "No Alloy") + " | " + (b.product_item || "No Product");
		var weight_info = b.charged_weight_mt ? flt(b.charged_weight_mt, 3) + " MT charged" : "";
		var active_class = mk_current_batch === b.name ? " active" : "";
		
		html += '<a href="javascript:void(0)" class="list-group-item mk-batch-item' + active_class + '" data-name="' + b.name + '">';
		html += '<div style="display: flex; justify-content: space-between; align-items: center;">';
		html += '<h5 class="list-group-item-heading" style="margin: 0;">' + label + '</h5>';
		html += '<span class="mk-status-badge ' + status_class + '">' + b.status + '</span>';
		html += '</div>';
		html += '<p class="list-group-item-text" style="margin: 5px 0 0 0;">' + subtitle;
		if (weight_info) {
			html += '<br><small>' + weight_info + '</small>';
		}
		html += '</p></a>';
	});
	html += '</div>';
	$container.html(html);

	if (!mk_current_batch && batches[0]) {
		mk_current_batch = batches[0].name;
		$(".mk-batch-item").first().addClass("active");
		load_batch_detail(mk_current_batch);
	} else if (mk_current_batch) {
		load_batch_detail(mk_current_batch);
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

function clear_batch_detail() {
	mk_current_batch = null;
	$("#mk_batch_title").html('<i class="fa fa-fire"></i> No batch selected');
	$("#mk_batch_summary").html('<div class="text-center text-muted" style="padding: 20px;">Select a batch from the list to view details</div>');
	$("#mk_raw_table").empty();
	$("#mk_process_table").empty();
	$("#mk_samples_table").empty();
	$("#mk_transfer_form").empty();
	$("#mk_action_buttons").hide();
}

function load_batch_detail(name) {
	if (!name) return;

	frappe.call({
		method: "frappe.client.get",
		args: {
			doctype: "Melting Batch",
			name: name
		},
		callback: function(r) {
			var doc = r.message;
			render_batch_header(doc);
			render_raw_table(doc);
			render_process_table(doc);
			render_samples_table(doc);
			render_transfer_form(doc);
			update_action_buttons(doc);
		}
	});
}

function render_batch_header(doc) {
	var title = doc.melting_batch_id || doc.name;
	var status_class = get_status_class(doc.status);
	
	$("#mk_batch_title").html('<i class="fa fa-fire"></i> ' + title + ' <span class="mk-status-badge ' + status_class + '" style="margin-left: 10px;">' + doc.status + '</span>');

	var planned = doc.planned_weight_mt ? flt(doc.planned_weight_mt, 3) + " MT" : "-";
	var charged = doc.charged_weight_mt ? flt(doc.charged_weight_mt, 3) + " MT" : "-";
	var tapped = doc.tapped_weight_mt ? flt(doc.tapped_weight_mt, 3) + " MT" : "-";
	var yield_pct = doc.yield_percent ? flt(doc.yield_percent, 2) + "%" : "-";
	var yield_class = "";
	if (doc.yield_percent >= 95) {
		yield_class = "text-success";
	} else if (doc.yield_percent < 90 && doc.yield_percent > 0) {
		yield_class = "text-warning";
	}

	var html = '<div class="mk-summary-row">';
	html += '<div class="mk-summary-item"><div class="label-text">Alloy</div><div class="value-text">' + (doc.alloy || "-") + '</div></div>';
	html += '<div class="mk-summary-item"><div class="label-text">Product</div><div class="value-text">' + (doc.product_item || "-") + '</div></div>';
	html += '<div class="mk-summary-item"><div class="label-text">Planned</div><div class="value-text">' + planned + '</div></div>';
	html += '<div class="mk-summary-item"><div class="label-text">Charged</div><div class="value-text">' + charged + '</div></div>';
	html += '<div class="mk-summary-item"><div class="label-text">Tapped</div><div class="value-text">' + tapped + '</div></div>';
	html += '<div class="mk-summary-item"><div class="label-text">Yield</div><div class="value-text ' + yield_class + '">' + yield_pct + '</div></div>';
	html += '</div>';
	
	$("#mk_batch_summary").html(html);
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

function render_raw_table(doc) {
	var $container = $("#mk_raw_table");
	
	if (!doc.raw_materials || !doc.raw_materials.length) {
		$container.html('<div class="text-center text-muted" style="padding: 30px;"><i class="fa fa-cubes fa-2x"></i><p style="margin-top: 10px;">No raw materials added yet</p></div>');
		return;
	}

	var total_kg = 0;
	var correction_kg = 0;

	var html = '<table class="table table-bordered table-striped table-condensed">';
	html += '<thead><tr><th style="width: 40px;">#</th><th>Type</th><th>Item</th><th>Batch / Heat</th><th>Bin</th><th>Bucket</th><th style="text-align: right;">Qty (kg)</th><th style="width: 80px;">Correction?</th></tr></thead>';
	html += '<tbody>';

	doc.raw_materials.forEach(function(r, idx) {
		total_kg += flt(r.qty_kg);
		if (r.is_correction) correction_kg += flt(r.qty_kg);
		
		var row_class = r.is_correction ? " class=\"warning\"" : "";
		html += '<tr' + row_class + '>';
		html += '<td>' + (idx + 1) + '</td>';
		html += '<td>' + (r.ingredient_type || "") + '</td>';
		html += '<td><strong>' + (r.item_code || "") + '</strong><br><small class="text-muted">' + (r.item_name || "") + '</small></td>';
		html += '<td>' + (r.batch_no || "") + '</td>';
		html += '<td>' + (r.source_bin || "") + '</td>';
		html += '<td>' + (r.bucket_no || "") + '</td>';
		html += '<td style="text-align: right; font-weight: 600;">' + flt(r.qty_kg, 3) + '</td>';
		html += '<td>' + (r.is_correction ? '<span class="label label-warning">Yes</span>' : '') + '</td>';
		html += '</tr>';
	});

	html += '</tbody>';
	html += '<tfoot>';
	html += '<tr style="font-weight: 600; background: #f5f5f5;"><td colspan="6" style="text-align: right;">Total:</td><td style="text-align: right;">' + flt(total_kg, 3) + ' kg</td><td></td></tr>';
	if (correction_kg > 0) {
		html += '<tr style="background: #fff3cd;"><td colspan="6" style="text-align: right;">Correction Total:</td><td style="text-align: right;">' + flt(correction_kg, 3) + ' kg</td><td></td></tr>';
	}
	html += '</tfoot></table>';

	$container.html(html);
}

function render_process_table(doc) {
	var $container = $("#mk_process_table");
	
	if (!doc.process_logs || !doc.process_logs.length) {
		$container.html('<div class="text-center text-muted" style="padding: 30px;"><i class="fa fa-list-ol fa-2x"></i><p style="margin-top: 10px;">No process events logged yet</p></div>');
		return;
	}

	var html = '<table class="table table-bordered table-striped table-condensed">';
	html += '<thead><tr><th>Time</th><th>Event</th><th style="text-align: right;">Temp</th><th style="text-align: right;">Pressure</th><th>Flux</th><th>Sample</th><th>Note</th></tr></thead>';
	html += '<tbody>';

	doc.process_logs.forEach(function(r) {
		var event_class = get_event_class(r.event_type);
		html += '<tr>';
		html += '<td>' + frappe.datetime.str_to_user(r.log_time) + '</td>';
		html += '<td><span class="label ' + event_class + '">' + (r.event_type || "") + '</span></td>';
		html += '<td style="text-align: right;">' + (r.temp_c || "") + '</td>';
		html += '<td style="text-align: right;">' + (r.pressure_bar || "") + '</td>';
		html += '<td>' + (r.flux_type || "") + (r.flux_qty_kg ? " (" + r.flux_qty_kg + " kg)" : "") + '</td>';
		html += '<td>' + (r.sample_id || "") + '</td>';
		html += '<td>' + (r.note || "") + '</td>';
		html += '</tr>';
	});

	html += '</tbody></table>';
	$container.html(html);
}

function get_event_class(event_type) {
	var map = {
		"Burner On": "label-success",
		"Fluxing": "label-info",
		"Sample Taken": "label-warning",
		"Correction": "label-danger",
		"Holding": "label-default",
		"Transfer": "label-primary"
	};
	return map[event_type] || "label-default";
}

function render_samples_table(doc) {
	var $container = $("#mk_samples_table");
	
	if (!doc.spectro_samples || !doc.spectro_samples.length) {
		$container.html('<div class="text-center text-muted" style="padding: 30px;"><i class="fa fa-flask fa-2x"></i><p style="margin-top: 10px;">No spectro samples taken yet</p></div>');
		return;
	}

	var html = '<table class="table table-bordered table-striped table-condensed">';
	html += '<thead><tr><th>Sample ID</th><th>Time</th><th>Si %</th><th>Fe %</th><th>Cu %</th><th>Mn %</th><th>Mg %</th><th>Zn %</th><th>Ti %</th><th>Al %</th><th>Status</th><th>Correction?</th></tr></thead>';
	html += '<tbody>';

	doc.spectro_samples.forEach(function(s) {
		var status_class = "label-default";
		if (s.result_status === "Within Limit") {
			status_class = "label-success";
		} else if (s.result_status === "Out of Limit") {
			status_class = "label-danger";
		}
		
		html += '<tr>';
		html += '<td><strong>' + (s.sample_id || "") + '</strong></td>';
		html += '<td>' + frappe.datetime.str_to_user(s.sample_time) + '</td>';
		html += '<td>' + (s.si_percent || "-") + '</td>';
		html += '<td>' + (s.fe_percent || "-") + '</td>';
		html += '<td>' + (s.cu_percent || "-") + '</td>';
		html += '<td>' + (s.mn_percent || "-") + '</td>';
		html += '<td>' + (s.mg_percent || "-") + '</td>';
		html += '<td>' + (s.zn_percent || "-") + '</td>';
		html += '<td>' + (s.ti_percent || "-") + '</td>';
		html += '<td>' + (s.al_percent || "-") + '</td>';
		html += '<td><span class="label ' + status_class + '">' + (s.result_status || "Pending") + '</span></td>';
		html += '<td>' + (s.correction_required ? '<span class="label label-warning">Yes</span>' : '') + '</td>';
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

	var html = '<div class="form-horizontal" style="max-width: 600px;">';
	html += '<div class="form-group"><label class="col-sm-4 control-label">Tapped Metal (MT)</label><div class="col-sm-6"><input type="number" step="0.001" class="form-control" id="mk_tapped_weight" value="' + (doc.tapped_weight_mt || "") + '"' + disabled + '></div></div>';
	html += '<div class="form-group"><label class="col-sm-4 control-label">FO Temp (C)</label><div class="col-sm-6"><input type="number" class="form-control" id="mk_fo_temp" value="' + (doc.fo_temp_c || "") + '"' + disabled + '></div></div>';
	html += '<div class="form-group"><label class="col-sm-4 control-label">FO Pressure (bar)</label><div class="col-sm-6"><input type="number" step="0.01" class="form-control" id="mk_fo_press" value="' + (doc.fo_pressure_bar || "") + '"' + disabled + '></div></div>';
	html += '<div class="form-group"><label class="col-sm-4 control-label">Dross (kg)</label><div class="col-sm-6"><input type="number" step="0.1" class="form-control" id="mk_dross" value="' + (doc.dross_weight_kg || "") + '"' + disabled + '></div></div>';
	html += '<div class="form-group"><label class="col-sm-4 control-label">Fuel (L/SCM)</label><div class="col-sm-6"><input type="number" step="0.1" class="form-control" id="mk_fuel" value="' + (doc.energy_fuel_litre || "") + '"' + disabled + '></div></div>';
	html += '<div class="form-group"><label class="col-sm-4 control-label">Note</label><div class="col-sm-6"><textarea class="form-control" id="mk_transfer_note" rows="2"' + disabled + '>' + (doc.remarks || "") + '</textarea></div></div>';
	
	html += '<div class="form-group"><div class="col-sm-offset-4 col-sm-6">';
	if (editable) {
		html += '<button class="btn btn-primary btn-lg" id="mk_btn_complete_transfer"><i class="fa fa-check"></i> Submit and Complete Transfer</button>';
	} else if (is_transferred) {
		html += '<div class="alert alert-success"><i class="fa fa-check-circle"></i> Transfer completed at ' + frappe.datetime.str_to_user(doc.transfer_end_datetime) + '</div>';
	} else {
		html += '<div class="alert alert-info"><i class="fa fa-info-circle"></i> Batch must be Ready for Transfer to complete transfer</div>';
	}
	html += '</div></div>';
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
					refresh_batches();
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
				label: __("Temp (C)"),
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
