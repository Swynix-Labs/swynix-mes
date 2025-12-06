// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

let ppc_calendar = null;
let current_caster = null;

frappe.pages['ppc-caster-kiosk'].on_page_load = function (wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'PPC Caster Kiosk',
		single_column: true
	});

	$(frappe.render_template("ppc_caster_kiosk", {})).appendTo(page.body);

	// Load FullCalendar dynamically
	load_fullcalendar().then(() => {
		init_header_controls();
		load_casters().then(() => {
			init_calendar();
			refresh_events();
		});
	});
};

frappe.pages['ppc-caster-kiosk'].on_page_show = function () {
	// Refresh data when page is shown
	if (ppc_calendar) {
		refresh_events();
	}
};

// Load FullCalendar CSS and JS dynamically
function load_fullcalendar() {
	return new Promise((resolve, reject) => {
		// Check if already loaded
		if (window.FullCalendar) {
			resolve();
			return;
		}

		// Load CSS
		if (!document.querySelector('link[href*="fullcalendar"]')) {
			const link = document.createElement('link');
			link.rel = 'stylesheet';
			link.href = 'https://cdn.jsdelivr.net/npm/fullcalendar@6.1.10/index.global.min.css';
			document.head.appendChild(link);
		}

		// Load JS
		const script = document.createElement('script');
		script.src = 'https://cdn.jsdelivr.net/npm/fullcalendar@6.1.10/index.global.min.js';
		script.onload = () => resolve();
		script.onerror = () => reject(new Error('Failed to load FullCalendar'));
		document.head.appendChild(script);
	});
}

function init_header_controls() {
	// Caster dropdown change -> reload events
	$(document).on('change', '#caster_select', function () {
		current_caster = $(this).val();
		refresh_events();
	});

	// View selection
	$(document).on('change', '#view_select', function () {
		if (!ppc_calendar) return;
		let view = $(this).val();
		ppc_calendar.changeView(view);
		refresh_events();
	});

	// Date navigation
	$(document).on('click', '#btn_prev', function () {
		if (ppc_calendar) {
			ppc_calendar.prev();
			refresh_events();
		}
	});

	$(document).on('click', '#btn_today', function () {
		if (ppc_calendar) {
			ppc_calendar.today();
			refresh_events();
		}
	});

	$(document).on('click', '#btn_next', function () {
		if (ppc_calendar) {
			ppc_calendar.next();
			refresh_events();
		}
	});

	// Create Plan button
	$(document).on('click', '#btn_create_plan', function () {
		if (!ppc_calendar) {
			frappe.msgprint(__("Calendar not ready."));
			return;
		}
		open_create_plan_dialog();
	});

	// Export Excel option
	$(document).on('click', '#export_excel', function (e) {
		e.preventDefault();
		export_plans('xlsx');
	});

	// Export CSV option
	$(document).on('click', '#export_csv', function (e) {
		e.preventDefault();
		export_plans('csv');
	});
}

function load_casters() {
	return frappe.call({
		method: "swynix_mes.swynix_mes.api.ppc_caster_kiosk.get_casters",
		freeze: true
	}).then(r => {
		let select = $("#caster_select");
		select.empty();
		select.append(`<option value="">Select Caster</option>`);
		(r.message || []).forEach(c => {
			select.append(`<option value="${c.name}">${c.name}</option>`);
		});

		// auto select first caster if available
		if (!current_caster && r.message && r.message.length) {
			current_caster = r.message[0].name;
			select.val(current_caster);
		}
	});
}

/**
 * Get status color based on plan status
 * @param {string} status - Plan status
 * @returns {string} Hex color code
 */
function getStatusColor(status) {
	switch (status) {
		case "Planned": return "#9e9e9e"; // grey
		case "Released": return "#607d8b"; // blue-grey
		case "Melting": return "#2196f3"; // blue
		case "Metal Ready": return "#00bcd4"; // teal
		case "Casting": return "#ff9800"; // orange
		case "Coils Complete": return "#4caf50"; // green
		case "Not Produced": return "#f44336"; // red
		default: return "#9e9e9e"; // grey
	}
}

/**
 * Format time as HH:MM
 * @param {string|Date} datetime - Datetime to format
 * @returns {string} Formatted time
 */
function formatTime(datetime) {
	if (!datetime) return '';
	const dt = typeof datetime === 'string' ? new Date(datetime) : datetime;
	return dt.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
}

/**
 * Build tooltip content for a plan
 * @param {Object} p - Plan object
 * @returns {string} HTML tooltip content
 */
function buildTooltip(p) {
	let lines = [];

	// First line: product_item (alloy / temper) | weight MT
	let line1 = `${p.product_item || 'N/A'} (${p.alloy || '-'} / ${p.temper || '-'})`;
	if (p.planned_weight_mt) {
		line1 += ` | ${p.planned_weight_mt} MT`;
	}
	lines.push(line1);

	// Second line: Melt timing if available
	if (p.melting_start || p.melting_end) {
		let meltLine = 'Melt: ';
		meltLine += formatTime(p.melting_start) || '--:--';
		meltLine += ' – ';
		meltLine += formatTime(p.melting_end) || '--:--';
		lines.push(meltLine);
	}

	// Third line: Cast timing if available
	if (p.casting_start || p.casting_end) {
		let castLine = 'Cast: ';
		castLine += formatTime(p.casting_start) || '--:--';
		castLine += ' – ';
		castLine += formatTime(p.casting_end) || '--:--';
		lines.push(castLine);
	}

	// Status
	lines.push(`Status: ${p.status || 'Unknown'}`);

	// Furnace if available
	if (p.furnace) {
		lines.push(`Furnace: ${p.furnace}`);
	}

	// Customer if available
	if (p.customer) {
		lines.push(`Customer: ${p.customer}`);
	}

	// Overlap warning if flagged
	if (p.overlap_flag) {
		lines.push(`⚠️ Schedule Conflict`);
	}

	return lines.join('\n');
}

function init_calendar() {
	let calendarEl = document.getElementById('ppc_calendar');
	if (!calendarEl) return;

	ppc_calendar = new FullCalendar.Calendar(calendarEl, {
		initialView: 'timeGridWeek',
		slotDuration: '00:30:00',
		slotLabelInterval: '01:00',
		allDaySlot: false,
		editable: false,
		selectable: false,
		height: 'auto',
		nowIndicator: true,
		headerToolbar: false, // We use custom header controls
		dayHeaderFormat: { weekday: 'short', month: 'numeric', day: 'numeric' },

		// Do nothing on empty-slot click
		dateClick: function (info) {
			return;
		},

		// When user clicks existing event -> open doc
		eventClick: function (info) {
			if (info.event.extendedProps && info.event.extendedProps.docname) {
				frappe.set_route('Form', 'PPC Casting Plan', info.event.extendedProps.docname);
			}
		},

		// Fetch events dynamically
		events: function (fetchInfo, successCallback, failureCallback) {
			fetch_events(fetchInfo.startStr, fetchInfo.endStr)
				.then(events => successCallback(events))
				.catch(err => failureCallback(err));
		},

		// Event rendering - add tooltip
		eventDidMount: function (info) {
			const tooltip = info.event.extendedProps.tooltip;
			if (tooltip) {
				info.el.setAttribute('title', tooltip);
			}

			// Add overlap indicator
			if (info.event.extendedProps.overlap_flag) {
				info.el.style.border = '2px dashed #f44336';
			}
		}
	});

	ppc_calendar.render();
}

function refresh_events() {
	if (ppc_calendar) {
		ppc_calendar.refetchEvents();
	}
}

// Backend call to get events for range
function fetch_events(start, end) {
	if (!current_caster) {
		return Promise.resolve([]);
	}

	return frappe.call({
		method: "swynix_mes.swynix_mes.api.ppc_caster_kiosk.get_plan_for_range",
		args: {
			caster: current_caster,
			start: start,
			end: end
		}
	}).then(r => {
		const plans = r.message || [];
		return plans.map(p => {
			// Build title
			let title = p.plan_type === "Downtime"
				? `DT: ${p.downtime_type || ''}`
				: `${p.product_item || ''} (${p.alloy || ''} / ${p.temper || ''})`;

			// Add weight info if available
			if (p.plan_type !== "Downtime" && p.planned_weight_mt) {
				title += ` | ${p.planned_weight_mt} MT`;
			}

			// Determine event start/end using actual times when available
			// Priority: actual_start > melting_start > start_datetime (planned)
			const eventStart = p.actual_start || p.melting_start || p.start_datetime;
			// Priority: actual_end > casting_end > end_datetime (planned)
			const eventEnd = p.actual_end || p.casting_end || p.end_datetime;

			// Get color based on status
			let color = p.plan_type === "Downtime" ? '#e74c3c' : getStatusColor(p.status);

			// If overlap flagged, use a warning color
			if (p.overlap_flag) {
				color = '#ff5722'; // deep orange for overlap warning
			}

			return {
				id: p.name,
				title: title,
				start: eventStart,
				end: eventEnd,
				backgroundColor: color,
				borderColor: color,
				extendedProps: {
					docname: p.name,
					plan_type: p.plan_type,
					status: p.status,
					furnace: p.furnace,
					tooltip: buildTooltip(p),
					overlap_flag: p.overlap_flag,
					overlap_note: p.overlap_note,
					// Actual timing info (from production)
					actual_start: p.actual_start,
					actual_end: p.actual_end
				}
			};
		});
	});
}

// Dialog to create new plan (opened via Create Plan button)
function open_create_plan_dialog() {
	// Default start/end based on current calendar date
	let base_date = ppc_calendar ? ppc_calendar.getDate() : new Date();

	// Round to next hour for nicer default
	let start_date = new Date(base_date);
	let minutes = start_date.getMinutes();
	if (minutes > 0) {
		start_date.setMinutes(0);
		start_date.setHours(start_date.getHours() + 1);
	}
	start_date.setSeconds(0);
	start_date.setMilliseconds(0);

	let end_date = new Date(start_date);
	end_date.setHours(end_date.getHours() + 1); // 1 hour by default

	let start = frappe.datetime.get_datetime_as_string(start_date);
	let end = frappe.datetime.get_datetime_as_string(end_date);

	let d = new frappe.ui.Dialog({
		title: __('Create Caster Plan'),
		fields: [
			{
				fieldname: 'caster',
				label: __('Caster'),
				fieldtype: 'Link',
				options: 'Workstation',
				reqd: 1,
				default: current_caster
			},
			{
				fieldname: 'furnace',
				label: __('Furnace (Foundry)'),
				fieldtype: 'Link',
				options: 'Workstation',
				description: __('Optional: select the melting furnace / foundry for this cast.')
			},
			{
				fieldname: 'plan_type',
				label: __('Plan Type'),
				fieldtype: 'Select',
				options: ['Casting', 'Downtime'],
				default: 'Casting',
				reqd: 1
			},
			{
				fieldname: 'start_datetime',
				label: __('Start'),
				fieldtype: 'Datetime',
				default: start,
				reqd: 1
			},
			{
				fieldname: 'end_datetime',
				label: __('End'),
				fieldtype: 'Datetime',
				default: end,
				reqd: 1
			},

			{ fieldname: 'section_planned', fieldtype: 'Section Break', label: __('Planned Parameters') },

			// Core PPC casting fields (planned)
			{
				fieldname: 'product_item',
				label: __('Product Item'),
				fieldtype: 'Link',
				options: 'Item',
				depends_on: "eval:doc.plan_type=='Casting'",
				mandatory_depends_on: "eval:doc.plan_type=='Casting'"
			},
			{
				fieldname: 'alloy',
				label: __('Alloy'),
				fieldtype: 'Link',
				options: 'Item',
				depends_on: "eval:doc.plan_type=='Casting'",
				mandatory_depends_on: "eval:doc.plan_type=='Casting'"
			},
			{
				fieldname: 'customer',
				label: __('Customer'),
				fieldtype: 'Link',
				options: 'Customer',
				depends_on: "eval:doc.plan_type=='Casting'"
			},
			{
				fieldname: 'temper',
				label: __('Temper'),
				fieldtype: 'Link',
				options: 'Temper',
				depends_on: "eval:doc.plan_type=='Casting'",
				mandatory_depends_on: "eval:doc.plan_type=='Casting'"
			},
			{
				fieldname: 'planned_width_mm',
				label: __('Cast Width (mm)'),
				fieldtype: 'Float',
				depends_on: "eval:doc.plan_type=='Casting'",
				mandatory_depends_on: "eval:doc.plan_type=='Casting'"
			},
			{
				fieldname: 'planned_gauge_mm',
				label: __('Final Gauge (mm)'),
				fieldtype: 'Float',
				depends_on: "eval:doc.plan_type=='Casting'",
				mandatory_depends_on: "eval:doc.plan_type=='Casting'"
			},
			{
				fieldname: 'planned_weight_mt',
				label: __('Cast Weight (MT)'),
				fieldtype: 'Float',
				depends_on: "eval:doc.plan_type=='Casting'",
				mandatory_depends_on: "eval:doc.plan_type=='Casting'"
			},

			{ fieldname: 'section_final', fieldtype: 'Section Break', label: __('Final Parameters (Optional)') },

			{
				fieldname: 'final_width_mm',
				label: __('Final Width (mm)'),
				fieldtype: 'Float',
				depends_on: "eval:doc.plan_type=='Casting'"
			},
			{
				fieldname: 'final_gauge_mm',
				label: __('Final Gauge (mm)'),
				fieldtype: 'Float',
				depends_on: "eval:doc.plan_type=='Casting'"
			},
			{
				fieldname: 'final_weight_mt',
				label: __('Final Weight (MT)'),
				fieldtype: 'Float',
				depends_on: "eval:doc.plan_type=='Casting'"
			},

			{ fieldname: 'section_recipe', fieldtype: 'Section Break', label: __('Recipe & Remarks') },

			{
				fieldname: 'charge_mix_recipe',
				label: __('Charge Mix Ratio'),
				fieldtype: 'Link',
				options: 'Charge Mix Ratio',
				depends_on: "eval:doc.plan_type=='Casting'"
			},
			{
				fieldname: 'remarks',
				label: __('Remarks'),
				fieldtype: 'Small Text'
			},

			// Downtime fields
			{
				fieldname: 'downtime_type',
				label: __('Downtime Type'),
				fieldtype: 'Select',
				options: 'Roll Change\nScheduled Maintenance\nBreakdown\nTrial\nOther',
				depends_on: "eval:doc.plan_type=='Downtime'"
			},
			{
				fieldname: 'downtime_reason',
				label: __('Reason'),
				fieldtype: 'Small Text',
				depends_on: "eval:doc.plan_type=='Downtime'"
			}
		],
		primary_action_label: __('Create Plan'),
		primary_action(values) {
			if (!values.caster) {
				frappe.msgprint(__("Please select a caster."));
				return;
			}
			if (!values.start_datetime || !values.end_datetime) {
				frappe.msgprint(__("Please set Start and End time."));
				return;
			}

			// 🚫 Prevent scheduling in the past (client-side check)
			const now = frappe.datetime.now_datetime();
			if (values.start_datetime && frappe.datetime.str_to_obj(values.start_datetime) < frappe.datetime.str_to_obj(now)) {
				frappe.msgprint(__("You cannot create a plan in the past. Please choose a future time."));
				return;
			}

			// Validate mandatory fields for Casting plans
			if (values.plan_type === 'Casting') {
				const required = [
					['product_item', 'Product Item'],
					['alloy', 'Alloy'],
					['temper', 'Temper'],
					['planned_width_mm', 'Cast Width (mm)'],
					['planned_gauge_mm', 'Final Gauge (mm)'],
					['planned_weight_mt', 'Cast Weight (MT)'],
				];

				for (let [key, label] of required) {
					if (!values[key]) {
						frappe.msgprint(__("{0} is required to create a casting plan.", [label]));
						return;
					}
				}
			}

			// Ask backend for preview: suggested slot + affected plans
			frappe.call({
				method: "swynix_mes.swynix_mes.api.ppc_caster_kiosk.preview_plan_insertion",
				args: {
					caster: values.caster,
					start_datetime: values.start_datetime,
					end_datetime: values.end_datetime
				},
				freeze: true,
				callback: function (r) {
					const preview = r.message || {};
					const affected = preview.affected_plans || [];
					const shift_delta_seconds = preview.shift_delta_seconds || 0;

					const req_start = frappe.datetime.str_to_user(preview.requested_start);
					const req_end = frappe.datetime.str_to_user(preview.requested_end);
					const sug_start = frappe.datetime.str_to_user(preview.suggested_start);
					const sug_end = frappe.datetime.str_to_user(preview.suggested_end);

					// Check if suggested slot is same as requested
					const same_slot =
						preview.requested_start === preview.suggested_start &&
						preview.requested_end === preview.suggested_end;

					// If suggested == requested AND no affected plans -> create directly
					if (same_slot && !affected.length) {
						do_create_plan_from_dialog(d, values);
						return;
					}

					// Build confirmation message
					let msg = "";

					if (!same_slot) {
						msg += __(
							"You requested <b>{0} – {1}</b>.<br>" +
							"To maintain sequence, system suggests scheduling this plan at <b>{2} – {3}</b> (snapped to available slot).<br><br>",
							[req_start, req_end, sug_start, sug_end]
						);
					} else {
						msg += __(
							"You are creating a plan at <b>{0} – {1}</b>.<br><br>",
							[sug_start, sug_end]
						);
					}

					const count = affected.length;
					if (count) {
						// Format shift delta for display
						let shift_display = "";
						if (shift_delta_seconds > 0) {
							const hours = Math.floor(shift_delta_seconds / 3600);
							const minutes = Math.floor((shift_delta_seconds % 3600) / 60);
							if (hours > 0 && minutes > 0) {
								shift_display = __("{0}h {1}m", [hours, minutes]);
							} else if (hours > 0) {
								shift_display = __("{0} hour(s)", [hours]);
							} else {
								shift_display = __("{0} minute(s)", [minutes]);
							}
						}

						const shift_from_display = preview.shift_from
							? frappe.datetime.str_to_user(preview.shift_from)
							: sug_start;

						msg += __(
							"This will move <b>{0}</b> plan(s) starting from <b>{1}</b> forward by <b>{2}</b>.<br><br>",
							[count, shift_from_display, shift_display]
						);
						const first = affected[0];
						msg += __(
							"First affected plan: <b>{0}</b> ({1} – {2}).<br><br>",
							[
								first.name,
								frappe.datetime.str_to_user(first.start_datetime),
								frappe.datetime.str_to_user(first.end_datetime)
							]
						);
					}

					msg += __("Do you want to continue?");

					// On confirm, override values with suggested times and create
					frappe.confirm(
						msg,
						() => {
							values.start_datetime = preview.suggested_start;
							values.end_datetime = preview.suggested_end;
							do_create_plan_from_dialog(d, values);
						},
						() => {
							// User cancelled → do nothing
						}
					);
				}
			});
		}
	});

	// Filter Caster field to active Casting workstations
	d.fields_dict.caster.get_query = function () {
		return { filters: { workstation_type: 'Casting' } };
	};

	// Filter Furnace field to active Foundry workstations
	d.fields_dict.furnace.get_query = function () {
		return { filters: { workstation_type: 'Foundry' } };
	};

	// Product Item: Item Group = Product
	d.fields_dict.product_item.get_query = function () {
		return { filters: { item_group: 'Product' } };
	};

	// Alloy: Item Group = Alloy
	d.fields_dict.alloy.get_query = function () {
		return { filters: { item_group: 'Alloy' } };
	};

	// Charge Mix Recipe: filter by selected alloy
	if (d.fields_dict.charge_mix_recipe) {
		d.fields_dict.charge_mix_recipe.get_query = function () {
			const alloy = d.get_value('alloy');
			const filters = alloy ? { alloy: alloy, is_active: 1 } : { is_active: 1 };
			return { filters };
		};
	}

	// Auto-set recipe when alloy is chosen
	d.fields_dict.alloy.df.onchange = () => {
		const alloy = d.get_value('alloy');
		if (!alloy) return;
		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "Charge Mix Ratio",
				filters: { alloy: alloy, is_active: 1 },
				fields: ["name"],
				limit_page_length: 1
			},
			callback: r => {
				if (r.message && r.message.length) {
					d.set_value('charge_mix_recipe', r.message[0].name);
				}
			}
		});
	};

	// Refresh fields visibility when plan_type changes
	d.fields_dict.plan_type.df.onchange = () => {
		d.refresh();
	};

	d.show();

	// Trigger initial refresh to show/hide depends_on fields
	setTimeout(() => {
		d.refresh();
	}, 100);
}

// Helper function to actually create the plan after confirmation
function do_create_plan_from_dialog(dialog, values) {
	frappe.call({
		method: "swynix_mes.swynix_mes.api.ppc_caster_kiosk.create_plan",
		args: { data: values },
		freeze: true,
		callback: function (r) {
			dialog.hide();
			frappe.show_alert({
				message: __('Plan {0} created and schedule updated.', [r.message]),
				indicator: 'green'
			}, 5);
			// If caster changed inside dialog, sync header & refresh
			if (values.caster && values.caster !== current_caster) {
				current_caster = values.caster;
				$("#caster_select").val(current_caster);
			}
			refresh_events();
		}
	});
}

// Export plans to Excel or CSV
function export_plans(format) {
	if (!current_caster) {
		frappe.msgprint(__("Please select a caster before exporting."));
		return;
	}
	if (!ppc_calendar) return;

	const view = ppc_calendar.view;
	const start = view.currentStart.toISOString();
	const end = view.currentEnd.toISOString();

	// Build URL for direct download
	const url = `/api/method/swynix_mes.swynix_mes.api.ppc_caster_kiosk.export_plans?caster=${encodeURIComponent(current_caster)}&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&format=${encodeURIComponent(format)}`;

	// Open URL to trigger download
	window.open(url, '_blank');
}
