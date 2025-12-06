// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

/**
 * QC Kiosk - Chemical Composition Quality Control
 * 
 * A Google-style kiosk page for lab technicians to review and approve
 * spectro samples from Melting Batches.
 * 
 * Features:
 * - Sample queue with filters
 * - Detailed spec vs actual comparison
 * - Editable element readings
 * - Actions: Save, Approve, Reject, Request Correction
 */

// Global state
let qc_state = {
	current_sample_name: null,
	current_sample_data: null,
	samples: []
};

/**
 * Parse URL query parameters
 * @returns {Object} Key-value pairs of query parameters
 */
function get_query_params() {
	let params = {};
	let search = window.location.search;
	if (search) {
		let urlParams = new URLSearchParams(search);
		for (let [key, value] of urlParams) {
			params[key] = value;
		}
	}
	return params;
}

frappe.pages['qc-kiosk'].on_page_load = function(wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'QC Kiosk',
		single_column: true
	});

	// Render template
	$(frappe.render_template("qc_kiosk", {})).appendTo(page.body);

	// Initialize
	init_qc_kiosk();
};

frappe.pages['qc-kiosk'].on_page_show = function() {
	// Check for query params and auto-load
	let params = get_query_params();
	if (params.sample) {
		qc_state.current_sample_name = params.sample;
	}
	
	// Refresh samples list
	load_samples();
};

function init_qc_kiosk() {
	// Set default dates
	let today = frappe.datetime.get_today();
	$('#qc_from_date').val(today);
	$('#qc_to_date').val(today);

	// Load filter options
	load_filter_options();

	// Bind events
	bind_events();

	// Check URL params
	let params = get_query_params();
	if (params.sample) {
		qc_state.current_sample_name = params.sample;
	}

	// Initial load
	load_samples();
}

function bind_events() {
	// Refresh button
	$('#qc_btn_refresh').on('click', function() {
		load_samples();
	});

	// Export button
	$('#qc_btn_export').on('click', function() {
		export_samples();
	});

	// Filter changes
	$('#qc_from_date, #qc_to_date, #qc_alloy_filter, #qc_status_filter, #qc_source_filter').on('change', function() {
		load_samples();
	});

	// Sample selection
	$(document).on('click', '.qc-sample-item', function() {
		let sample_name = $(this).data('sample-name');
		select_sample(sample_name);
	});

	// Tab switching
	$(document).on('click', '.qc-tab', function() {
		let tab = $(this).data('tab');
		switch_tab(tab);
	});

	// Action buttons
	$('#qc_btn_save').on('click', function() {
		save_sample('save');
	});

	$('#qc_btn_approve').on('click', function() {
		confirm_action('approve');
	});

	$('#qc_btn_reject').on('click', function() {
		confirm_action('reject');
	});

	$('#qc_btn_correction').on('click', function() {
		confirm_action('correction_required');
	});

	$('#qc_btn_hold').on('click', function() {
		confirm_action('hold');
	});

	// Element input change - update styling
	$(document).on('input', '.qc-actual-input', function() {
		update_element_status($(this));
	});
}

/**
 * Switch between Analysis and History tabs
 */
function switch_tab(tab) {
	// Update tab buttons
	$('.qc-tab').removeClass('active');
	$(`.qc-tab[data-tab="${tab}"]`).addClass('active');
	
	// Update tab content
	$('.qc-tab-content').removeClass('active');
	$(`#qc_tab_${tab}`).addClass('active');
	
	// Load history data if switching to history tab and we have sample data
	if (tab === 'history' && qc_state.current_sample_data) {
		load_sample_history();
	}
}

/**
 * Load charge and correction history for the current sample
 */
function load_sample_history() {
	if (!qc_state.current_sample_data) {
		return;
	}
	
	let sample_name = qc_state.current_sample_data.sample_info.name;
	
	$('#qc_history_window').html('<i class="fa fa-spinner fa-spin"></i> Loading history...');
	$('#qc_charges_tbody').empty();
	$('#qc_corrections_tbody').empty();
	$('#qc_samples_history_list').empty();
	
	frappe.call({
		method: "swynix_mes.swynix_mes.page.qc_kiosk.qc_kiosk.get_qc_history_for_sample",
		args: { sample_name: sample_name },
		callback: function(r) {
			if (r.message) {
				render_history(r.message);
			}
		}
	});
}

/**
 * Render history data
 */
function render_history(data) {
	// Render time window info
	let windowHtml = '';
	if (data.window) {
		let fromTime = data.window.from ? frappe.datetime.str_to_user(data.window.from) : 'Batch Start';
		let toTime = data.window.to ? frappe.datetime.str_to_user(data.window.to) : 'Current';
		windowHtml = `
			<strong>Time Window:</strong> ${fromTime} → ${toTime}
			<br>
			<span style="font-size: 11px; color: #94a3b8;">
				Sample ${data.current_sample.index} of ${data.current_sample.total}
			</span>
		`;
	}
	$('#qc_history_window').html(windowHtml);
	
	// Render charges table
	let charges = data.charges || [];
	if (charges.length > 0) {
		let chargesHtml = '';
		charges.forEach(c => {
			let timeStr = c.posting_datetime ? frappe.datetime.str_to_user(c.posting_datetime) : '-';
			let itemName = frappe.utils.escape_html(c.item_name || c.item_code || '-');
			let ingType = frappe.utils.escape_html(c.ingredient_type || '-');
			let source = frappe.utils.escape_html(c.source_bin || '-');
			
			let rowClass = c.is_correction ? 'style="background: #fef3c7;"' : '';
			
			chargesHtml += `
				<tr ${rowClass}>
					<td>${timeStr}</td>
					<td>${itemName}</td>
					<td>${ingType}${c.is_correction ? ' <span style="color: #b45309;">(Correction)</span>' : ''}</td>
					<td class="text-right">${flt(c.qty_kg, 2)}</td>
					<td>${source}</td>
				</tr>
			`;
		});
		$('#qc_charges_tbody').html(chargesHtml);
		$('#qc_charges_table').show();
		$('#qc_charges_empty').hide();
	} else {
		$('#qc_charges_table').hide();
		$('#qc_charges_empty').show();
	}
	
	// Render corrections table
	let corrections = data.corrections || [];
	if (corrections.length > 0) {
		let correctionsHtml = '';
		corrections.forEach(c => {
			let timeStr = c.log_time ? frappe.datetime.str_to_user(c.log_time) : '-';
			let note = frappe.utils.escape_html(c.note || '-');
			let sampleId = frappe.utils.escape_html(c.sample_id || '-');
			let temp = c.temp_c ? flt(c.temp_c, 1) : '-';
			
			correctionsHtml += `
				<tr>
					<td>${timeStr}</td>
					<td>${sampleId}</td>
					<td>${note}</td>
					<td class="text-center">${temp}</td>
				</tr>
			`;
		});
		$('#qc_corrections_tbody').html(correctionsHtml);
		$('#qc_corrections_table').show();
		$('#qc_corrections_empty').hide();
	} else {
		$('#qc_corrections_table').hide();
		$('#qc_corrections_empty').show();
	}
	
	// Render samples list
	let samples = data.samples || [];
	let samplesHtml = '';
	samples.forEach(s => {
		let statusClass = '';
		if (s.status === 'Within Spec') statusClass = 'within-spec';
		else if (s.status === 'Out of Spec') statusClass = 'out-of-spec';
		else if (s.status === 'Correction Asked') statusClass = 'correction';
		else statusClass = 'pending';
		
		let currentClass = s.is_current ? 'current' : '';
		let timeStr = s.sample_time ? frappe.datetime.str_to_user(s.sample_time).split(' ')[1] || frappe.datetime.str_to_user(s.sample_time) : '-';
		
		samplesHtml += `
			<div class="qc-sample-history-item ${currentClass}">
				<span class="sample-id">${frappe.utils.escape_html(s.sample_id)}</span>
				<span class="sample-time">${timeStr}</span>
				<span class="sample-status ${statusClass}">${frappe.utils.escape_html(s.status)}</span>
			</div>
		`;
	});
	$('#qc_samples_history_list').html(samplesHtml);
}

function load_filter_options() {
	// Load alloys
	frappe.call({
		method: "swynix_mes.swynix_mes.page.qc_kiosk.qc_kiosk.get_alloys",
		callback: function(r) {
			let $select = $('#qc_alloy_filter');
			$select.find('option:not(:first)').remove();
			(r.message || []).forEach(a => {
				$select.append(`<option value="${a.name}">${a.item_name || a.name}</option>`);
			});
		}
	});
}

function export_samples() {
	let filters = {
		from_date: $('#qc_from_date').val(),
		to_date: $('#qc_to_date').val(),
		alloy: $('#qc_alloy_filter').val(),
		status: $('#qc_status_filter').val(),
		source_type: $('#qc_source_filter').val()
	};

	let url = `/api/method/swynix_mes.swynix_mes.page.qc_kiosk.qc_kiosk.export_samples_to_excel?filters=${encodeURIComponent(JSON.stringify(filters))}`;
	window.open(url);
}

// ==================== SAMPLE LOADING ====================

function load_samples() {
	let filters = {
		from_date: $('#qc_from_date').val(),
		to_date: $('#qc_to_date').val(),
		alloy: $('#qc_alloy_filter').val(),
		status: $('#qc_status_filter').val(),
		source_type: $('#qc_source_filter').val()
	};

	$('#qc_sample_list').html(
		'<div class="qc-loading"><i class="fa fa-spinner fa-spin"></i> Loading samples...</div>'
	);

	frappe.call({
		method: "swynix_mes.swynix_mes.page.qc_kiosk.qc_kiosk.get_pending_samples",
		args: { filters: filters },
		callback: function(r) {
			qc_state.samples = r.message || [];
			render_sample_list(qc_state.samples);

			// Auto-select if specified
			if (qc_state.current_sample_name) {
				let found = qc_state.samples.find(s => s.name === qc_state.current_sample_name);
				if (found) {
					select_sample(found.name);
				}
				// Clear auto-select after first load
				qc_state.current_sample_name = null;
			} else if (qc_state.samples.length) {
				select_sample(qc_state.samples[0].name);
			}
		}
	});
}

function render_sample_list(samples) {
	let $container = $('#qc_sample_list');
	$('#qc_sample_count').text(`(${samples.length})`);

	if (!samples.length) {
		$container.html(
			'<div class="qc-no-results">' +
				'<i class="fa fa-flask"></i>' +
				'<div>No samples found</div>' +
				'<div style="font-size: 12px; margin-top: 4px;">Try adjusting your filters</div>' +
			'</div>'
		);
		// Clear sample details when no samples found
		clear_sample_details();
		return;
	}

	let html = '';
	samples.forEach(s => {
		let badgeClass = get_status_badge_class(s.status);
		let isActive = (qc_state.current_sample_data && 
			qc_state.current_sample_data.sample_info && 
			qc_state.current_sample_data.sample_info.name === s.name) ? ' active' : '';
		let sourceDoc = s.source_document || s.melting_batch || s.casting_run || s.mother_coil || '-';
		let sourceLabel = s.source_type ? `${s.source_type}` : 'Source';
		
		let sourceIcon = '<i class="fa fa-file-o"></i>';
		if (s.source_type === 'Melting') {
			sourceIcon = '<i class="fa fa-fire" style="color: #ea580c;"></i>'; // Orange
		} else if (s.source_type === 'Casting') {
			sourceIcon = '<i class="fa fa-industry" style="color: #0284c7;"></i>'; // Sky Blue
		}

		let metaParts = [
			s.alloy || '-',
			s.furnace || '-',
			s.caster || ''
		].filter(part => part && part !== '').join(' | ');

		html += `
			<div class="qc-sample-item${isActive}" data-sample-name="${s.name}">
				<div class="qc-sample-row">
					<div>
						<div class="qc-sample-id">${frappe.utils.escape_html(s.sample_id || '')}${s.sample_sequence_no ? ' #' + s.sample_sequence_no : ''}</div>
						<div class="qc-sample-batch" style="display: flex; align-items: center; gap: 4px;">
							${sourceIcon} 
							<span>${frappe.utils.escape_html(sourceLabel)}: ${frappe.utils.escape_html(sourceDoc)}</span>
						</div>
					</div>
					<span class="qc-sample-badge ${badgeClass}">${frappe.utils.escape_html(s.status)}</span>
				</div>
				<div class="qc-sample-meta">
					${frappe.utils.escape_html(metaParts || '-')} | 
					${s.sample_time ? frappe.datetime.str_to_user(s.sample_time).split(' ')[1] || '' : '-'}
				</div>
			</div>
		`;
	});

	$container.html(html);
}

function get_status_badge_class(status) {
	switch (status) {
		case 'Approved':
		case 'Accepted':
		case 'Within Limit':
		case 'Within Spec':
			return 'qc-badge-approved';
		case 'Rejected':
		case 'Out of Limit':
			return 'qc-badge-rejected';
		case 'Correction Required':
			return 'qc-badge-correction';
		case 'Hold':
			return 'qc-badge-hold';
		default:
			return 'qc-badge-pending';
	}
}

// ==================== SAMPLE DETAIL ====================

/**
 * Clear sample details panel when no samples or changing filters
 */
function clear_sample_details() {
	qc_state.current_sample_data = null;
	$('#qc_detail_content').hide();
	$('#qc_empty_state').show();
	$('#qc_detail_header').html('');
	$('#qc_spec_tbody').empty();
	$('#qc_deviation_section').hide();
	$('#qc_all_ok_section').hide();
	$('#qc_comment').val('');
}

function select_sample(sample_name) {
	// Highlight in list
	$('.qc-sample-item').removeClass('active');
	$(`.qc-sample-item[data-sample-name="${sample_name}"]`).addClass('active');

	// Show loading
	$('#qc_empty_state').hide();
	$('#qc_detail_content').show();
	$('#qc_detail_header').html('<div class="qc-loading"><i class="fa fa-spinner fa-spin"></i> Loading...</div>');
	$('#qc_spec_tbody').empty();
	$('#qc_deviation_section').hide();

	frappe.call({
		method: "swynix_mes.swynix_mes.page.qc_kiosk.qc_kiosk.get_sample_details",
		args: { sample_name: sample_name },
		callback: function(r) {
			if (r.message) {
				qc_state.current_sample_data = r.message;
				render_sample_detail(r.message);
			}
		},
		error: function(r) {
			// Handle sample not found - refresh the list
			qc_state.current_sample_data = null;
			clear_sample_details();
			$('#qc_detail_header').html(
				'<div class="qc-error" style="padding: 20px; text-align: center; color: #dc2626;">' +
				'<i class="fa fa-exclamation-triangle"></i> ' +
				'<span>Sample not found. Refreshing...</span>' +
				'</div>'
			);
			// Reload samples after a brief delay
			setTimeout(function() {
				load_samples();
			}, 1000);
		}
	});
}

function render_sample_detail(data) {
	let batch = data.batch_info;
	let sample = data.sample_info;
	let elements = data.element_results || [];
	let failed = data.failed_rules || [];
	let deviation_messages = data.deviation_messages || [];
	let overall = data.overall_status;
	let accm = data.accm_name;
	let hasSpec = data.has_spec;
	let sumRules = data.sum_rules || [];
	let ratioRules = data.ratio_rules || [];

	// Render header
	let overallClass = overall === 'OK' ? 'qc-overall-ok' : 
		(overall === 'Out of Spec' ? 'qc-overall-out' : 'qc-overall-pending');
	let sourceLabel = batch.source_type || 'Source';
	let sourceLink = '';
	if (batch.source_type === 'Melting Batch') {
		sourceLink = `/app/melting-batch/${batch.name}`;
	} else if (batch.source_type === 'Casting Run') {
		sourceLink = `/app/casting-run/${batch.name}`;
	} else if (batch.source_type === 'Coil') {
		sourceLink = `/app/mother-coil/${batch.name}`;
	}
	let sourceValue = frappe.utils.escape_html(batch.batch_id || batch.name || '-');
	let sourceDisplay = sourceLink ? `<a href="${sourceLink}" target="_blank">${sourceValue}</a>` : sourceValue;

	let headerHtml = `
		<div class="qc-header-grid">
			<div class="qc-header-item">
				<span class="qc-header-label">${frappe.utils.escape_html(sourceLabel)}</span>
				<span class="qc-header-value">${sourceDisplay}</span>
			</div>
			<div class="qc-header-item">
				<span class="qc-header-label">Alloy</span>
				<span class="qc-header-value">${frappe.utils.escape_html(batch.alloy || '-')}</span>
			</div>
			<div class="qc-header-item">
				<span class="qc-header-label">Product</span>
				<span class="qc-header-value">${frappe.utils.escape_html(batch.product || '-')}</span>
			</div>
			<div class="qc-header-item">
				<span class="qc-header-label">Furnace</span>
				<span class="qc-header-value">${frappe.utils.escape_html(batch.furnace || '-')}</span>
			</div>
			<div class="qc-header-item">
				<span class="qc-header-label">Caster</span>
				<span class="qc-header-value">${frappe.utils.escape_html(batch.caster || '-')}</span>
			</div>
			<div class="qc-header-item">
				<span class="qc-header-label">Sample</span>
				<span class="qc-header-value">${frappe.utils.escape_html(sample.sample_id)} ${batch.sample_sequence_no ? '(' + batch.sample_sequence_no + ')' : ''} @ ${sample.sample_time ? frappe.datetime.str_to_user(sample.sample_time) : '-'}</span>
			</div>
			<div class="qc-header-item">
				<span class="qc-header-label">Status</span>
				<span class="qc-overall-badge ${overallClass}">${overall}</span>
			</div>
		</div>
	`;

	$('#qc_detail_header').html(headerHtml);

	// Spec reference
	if (hasSpec && accm) {
		$('#qc_spec_ref').html(
			`Spec from <a href="/app/alloy-chemical-composition-master/${accm}" target="_blank">${accm}</a>`
		);
	} else if (!hasSpec) {
		$('#qc_spec_ref').html(
			'<span style="color: #b45309;"><i class="fa fa-exclamation-triangle"></i> No composition spec found</span>'
		);
	} else {
		$('#qc_spec_ref').html('');
	}

	// Check if inputs should be readonly
	let isReadonly = false;
	if (sample.status === 'Approved' || sample.status === 'Accepted' || 
		sample.status === 'Rejected' || sample.status === 'Correction Required') {
		isReadonly = true;
	}
	
	// Render elements table
	let tbodyHtml = '';
	elements.forEach(el => {
		let resultIcon = '';
		let inputClass = '';
		
		if (el.actual !== null && el.actual !== undefined) {
			if (el.within_spec === true) {
				resultIcon = '<i class="fa fa-check-circle qc-result-icon qc-result-ok"></i>';
				inputClass = 'qc-in-spec';
			} else if (el.within_spec === false) {
				resultIcon = '<i class="fa fa-times-circle qc-result-icon qc-result-fail"></i>';
				inputClass = 'qc-out-spec';
			} else {
				resultIcon = '<i class="fa fa-minus-circle qc-result-icon qc-result-pending"></i>';
			}
		} else {
			resultIcon = '<i class="fa fa-minus-circle qc-result-icon qc-result-pending"></i>';
		}

		let readonlyAttr = isReadonly ? 'readonly' : '';
		if (isReadonly) {
			inputClass += ' qc-readonly';
		}

		tbodyHtml += `
			<tr>
				<td class="qc-element-name">${el.element}</td>
				<td class="text-center">${frappe.utils.escape_html(el.spec_text || '-')}</td>
				<td class="text-center">
					<input type="number" step="0.0001" class="qc-actual-input ${inputClass}"
						data-element="${el.element}"
						data-min="${el.lower_limit !== null ? el.lower_limit : ''}"
						data-max="${el.upper_limit !== null ? el.upper_limit : ''}"
						value="${el.actual !== null && el.actual !== undefined ? flt(el.actual, 4) : ''}"
						placeholder="Enter %"
						${readonlyAttr}>
				</td>
				<td class="text-center">${resultIcon}</td>
			</tr>
		`;
	});

	$('#qc_spec_tbody').html(tbodyHtml);

	// Render deviations with categorized styling
	// Use deviation_messages from backend (includes Sum Limit, Ratio, etc.)
	let hasDeviations = deviation_messages.length > 0 || failed.length > 0;
	let hasReadings = elements.some(el => el.actual !== null && el.actual !== undefined);
	
	if (hasDeviations) {
		let devHtml = '';
		
		// Use deviation_messages first (comprehensive from composition_check)
		deviation_messages.forEach(msg => {
			// Determine the type of deviation for styling
			let devClass = '';
			if (msg.includes('+') && msg.includes('should be')) {
				devClass = 'sum-limit';
			} else if (msg.includes('/') && msg.includes('should be')) {
				devClass = 'ratio';
			} else if (msg.toLowerCase().includes('remainder') || msg.toLowerCase().includes('al ')) {
				devClass = 'remainder';
			}
			
			devHtml += `<div class="qc-deviation-item ${devClass}">${frappe.utils.escape_html(msg)}</div>`;
		});
		
		// Fallback to failed_rules if no deviation_messages
		if (deviation_messages.length === 0 && failed.length > 0) {
			failed.forEach(f => {
				let devClass = '';
				if (f.condition_type === 'Sum Limit') devClass = 'sum-limit';
				else if (f.condition_type === 'Ratio') devClass = 'ratio';
				else if (f.condition_type === 'Remainder') devClass = 'remainder';
				
				devHtml += `<div class="qc-deviation-item ${devClass}">${frappe.utils.escape_html(f.message)}</div>`;
			});
		}
		
		$('#qc_deviation_list').html(devHtml);
		$('#qc_deviation_section').show();
		$('#qc_all_ok_section').hide();
	} else if (hasReadings && overall === 'OK') {
		// Show all OK message
		$('#qc_deviation_section').hide();
		$('#qc_all_ok_section').show();
	} else {
		$('#qc_deviation_section').hide();
		$('#qc_all_ok_section').hide();
	}

	// Clear comment and set readonly if needed
	$('#qc_comment').val(sample.remarks || '');
	if (isReadonly) {
		$('#qc_comment').prop('readonly', true).addClass('qc-readonly');
	} else {
		$('#qc_comment').prop('readonly', false).removeClass('qc-readonly');
	}

	// Update button states
	update_action_buttons(sample.status);
	
	// Reset to Analysis tab
	switch_tab('analysis');
}

function update_element_status($input) {
	let value = parseFloat($input.val());
	let min = parseFloat($input.data('min'));
	let max = parseFloat($input.data('max'));

	$input.removeClass('qc-in-spec qc-out-spec');

	if (!isNaN(value)) {
		let ok = true;
		if (!isNaN(min) && value < min) ok = false;
		if (!isNaN(max) && value > max) ok = false;

		if (ok) {
			$input.addClass('qc-in-spec');
		} else {
			$input.addClass('qc-out-spec');
		}
	}
}

function update_action_buttons(status) {
	let $approve = $('#qc_btn_approve');
	let $reject = $('#qc_btn_reject');
	let $correction = $('#qc_btn_correction');
	let $hold = $('#qc_btn_hold');
	let $save = $('#qc_btn_save');

	// Enable all by default
	$approve.prop('disabled', false).text(__('Approve – Within Spec'));
	$reject.prop('disabled', false);
	$correction.prop('disabled', false);
	$hold.prop('disabled', false);
	$save.prop('disabled', false);

	// Disable based on status
	if (status === 'Approved' || status === 'Accepted' || status === 'Within Spec') {
		$approve.prop('disabled', true).text(__('Already Approved'));
		$hold.prop('disabled', true);
	}
	if (status === 'Rejected') {
		$approve.prop('disabled', true);
		$reject.prop('disabled', true).text(__('Already Rejected'));
		$hold.prop('disabled', true);
	}
	if (status === 'Hold') {
		$hold.prop('disabled', true).text(__('On Hold'));
	}
	if (status === 'Correction Required') {
		$correction.prop('disabled', true).text(__('Correction Requested'));
	}
}

// ==================== ACTIONS ====================

function gather_readings() {
	let readings = {};
	$('.qc-actual-input').each(function() {
		let elem = $(this).data('element');
		let val = $(this).val();
		if (elem && val !== '') {
			readings[elem] = parseFloat(val);
		}
	});
	return readings;
}

function save_sample(action) {
	if (!qc_state.current_sample_data) {
		frappe.msgprint(__("Please select a sample first"));
		return;
	}

	let sample_name = qc_state.current_sample_data.sample_info.name;
	let readings = gather_readings();
	let comment = $('#qc_comment').val();

	frappe.call({
		method: "swynix_mes.swynix_mes.page.qc_kiosk.qc_kiosk.update_sample_result",
		args: {
			sample_name: sample_name,
			readings: readings,
			action: action,
			comment: comment
		},
		freeze: true,
		freeze_message: __("Processing..."),
		callback: function(r) {
			if (r.message && r.message.success) {
				let indicator = 'blue';
				if (action === 'approve') indicator = 'green';
				else if (action === 'reject') indicator = 'red';
				else if (action === 'correction_required') indicator = 'orange';
				else if (action === 'hold') indicator = 'yellow';
				
				frappe.show_alert({
					message: r.message.message,
					indicator: indicator
				}, 5);

				// Show stock entry notification if created
				if (r.message.stock_entry) {
					frappe.show_alert({
						message: __("Stock Entry {0} created", [r.message.stock_entry]),
						indicator: 'green'
					}, 8);
				}

				// Refresh
				load_samples();
				select_sample(sample_name);
			}
		},
		error: function(r) {
			// Check if it's a "not found" error and auto-refresh the list
			if (r && r.exc && (r.exc.includes("not found") || r.exc.includes("Not Found"))) {
				frappe.show_alert({
					message: __("Sample not found. Refreshing sample list..."),
					indicator: 'orange'
				}, 5);
				// Clear current selection and reload
				qc_state.current_sample_data = null;
				clear_sample_details();
				load_samples();
			}
		}
	});
}

function confirm_action(action) {
	if (!qc_state.current_sample_data) {
		frappe.msgprint(__("Please select a sample first"));
		return;
	}

	let messages = {
		'approve': __("Approve this sample as <b>Within Spec</b>?<br><br>This will mark the batch as QC OK and generate a Stock Entry for casting coils."),
		'reject': __("Reject this sample?<br><br>The operator may need to take a new sample. For casting coils, this will mark the coil as scrap."),
		'correction_required': __("Request correction for this sample?<br><br>A comment/instruction is recommended for the melting operator."),
		'hold': __("Put this sample on <b>Hold</b>?<br><br>The sample will be held for further review. No transfer or coil finalization will be allowed until resolved.")
	};

	let titles = {
		'approve': __("Approve Sample"),
		'reject': __("Reject Sample"),
		'correction_required': __("Request Correction"),
		'hold': __("Put on Hold")
	};

	// Check if comment is needed for correction
	if (action === 'correction_required') {
		let comment = $('#qc_comment').val().trim();
		if (!comment) {
			frappe.msgprint({
				title: __("Comment Required"),
				message: __("Please enter a correction instruction for the melting operator."),
				indicator: 'orange'
			});
			$('#qc_comment').focus();
			return;
		}
	}

	frappe.confirm(
		messages[action],
		function() {
			save_sample(action);
		},
		function() {
			// Cancelled
		}
	);
}
