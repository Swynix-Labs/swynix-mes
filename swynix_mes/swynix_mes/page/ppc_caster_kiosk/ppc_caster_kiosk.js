// Copyright (c) 2025, Swynix and contributors
// For license information, please see license.txt

frappe.pages['ppc-caster-kiosk'].on_page_load = function(wrapper) {
	frappe.ppc_kiosk = new PPCCasterKiosk(wrapper);
};

frappe.pages['ppc-caster-kiosk'].on_page_show = function() {
	// Refresh data when page is shown
	if (frappe.ppc_kiosk && frappe.ppc_kiosk.initialized) {
		frappe.ppc_kiosk.load_timeline();
	}
};

class PPCCasterKiosk {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: 'PPC Caster Kiosk',
			single_column: true
		});
		this.initialized = false;
		this.controls = {};
		this.make();
	}

	make() {
		this.make_filters();
		this.make_timeline_section();
		this.make_form_section();
		this.bind_events();
		this.initialized = true;
	}

	make_filters() {
		// Add filters to page actions area
		this.page.add_inner_button(__('Refresh'), () => this.load_timeline(), null, 'primary');

		// Caster filter
		this.controls.caster = frappe.ui.form.make_control({
			df: {
				fieldtype: 'Link',
				options: 'Workstation',
				fieldname: 'caster',
				label: 'Caster',
				placeholder: 'Select Caster',
				get_query: () => ({
					filters: { workstation_type: 'Casting' }
				}),
				change: () => this.load_timeline()
			},
			parent: this.page.page_actions,
			render_input: true
		});
		this.controls.caster.$wrapper.addClass('ml-2').css('min-width', '180px');

		// Date filter
		this.controls.plan_date = frappe.ui.form.make_control({
			df: {
				fieldtype: 'Date',
				fieldname: 'plan_date',
				label: 'Date',
				default: frappe.datetime.get_today(),
				change: () => this.load_timeline()
			},
			parent: this.page.page_actions,
			render_input: true
		});
		this.controls.plan_date.$wrapper.addClass('ml-2').css('min-width', '140px');
		this.controls.plan_date.set_value(frappe.datetime.get_today());
	}

	make_timeline_section() {
		this.$timeline_container = $(`
			<div class="ppc-timeline-section frappe-card" style="margin:15px; padding:20px;">
				<div class="d-flex justify-content-between align-items-center mb-3">
					<h4 class="mb-0">Schedule</h4>
					<span class="timeline-info text-muted small"></span>
				</div>
				<div class="timeline-content" style="min-height:200px; border:1px solid var(--border-color); border-radius:8px; padding:15px; background:var(--fg-color);">
					<div class="text-center text-muted" style="padding:60px 20px;">
						<i class="fa fa-calendar-o fa-3x mb-3 d-block"></i>
						Select a caster and date to view schedule
					</div>
				</div>
			</div>
		`).appendTo(this.page.body);

		this.$timeline = this.$timeline_container.find('.timeline-content');
		this.$timeline_info = this.$timeline_container.find('.timeline-info');
	}

	make_form_section() {
		this.$form_container = $(`
			<div class="ppc-form-section frappe-card" style="margin:15px; padding:20px;">
				<h4 class="mb-4">Create New Plan</h4>
				<div class="row">
					<div class="col-md-4 common-fields"></div>
					<div class="col-md-4 casting-fields"></div>
					<div class="col-md-4 downtime-fields" style="display:none;"></div>
				</div>
				<div class="row mt-4">
					<div class="col-12">
						<button class="btn btn-primary btn-lg mr-2 create-plan-btn">
							<i class="fa fa-plus"></i> Create Plan
						</button>
						<button class="btn btn-default btn-lg clear-form-btn">
							<i class="fa fa-eraser"></i> Clear Form
						</button>
					</div>
				</div>
			</div>
		`).appendTo(this.page.body);

		this.make_common_fields();
		this.make_casting_fields();
		this.make_downtime_fields();
	}

	make_common_fields() {
		const $container = this.$form_container.find('.common-fields');

		// Plan Type
		this.controls.plan_type = frappe.ui.form.make_control({
			df: {
				fieldtype: 'Select',
				fieldname: 'plan_type',
				label: 'Plan Type',
				options: 'Casting\nDowntime',
				default: 'Casting',
				reqd: 1,
				change: () => this.toggle_plan_type_fields()
			},
			parent: $container,
			render_input: true
		});
		this.controls.plan_type.set_value('Casting');

		// Start Datetime
		this.controls.start_datetime = frappe.ui.form.make_control({
			df: {
				fieldtype: 'Datetime',
				fieldname: 'start_datetime',
				label: 'Start Datetime',
				reqd: 1
			},
			parent: $container,
			render_input: true
		});

		// End Datetime
		this.controls.end_datetime = frappe.ui.form.make_control({
			df: {
				fieldtype: 'Datetime',
				fieldname: 'end_datetime',
				label: 'End Datetime',
				reqd: 1
			},
			parent: $container,
			render_input: true
		});

		// Furnace
		this.controls.furnace = frappe.ui.form.make_control({
			df: {
				fieldtype: 'Link',
				options: 'Workstation',
				fieldname: 'furnace',
				label: 'Furnace (optional)',
				get_query: () => ({
					filters: { workstation_type: 'Foundry' }
				})
			},
			parent: $container,
			render_input: true
		});

		// Planned Weight
		this.controls.planned_weight_mt = frappe.ui.form.make_control({
			df: {
				fieldtype: 'Float',
				fieldname: 'planned_weight_mt',
				label: 'Planned Weight (MT)',
				precision: 3
			},
			parent: $container,
			render_input: true
		});
	}

	make_casting_fields() {
		const $container = this.$form_container.find('.casting-fields');

		// Product Item
		this.controls.product_item = frappe.ui.form.make_control({
			df: {
				fieldtype: 'Link',
				options: 'Item',
				fieldname: 'product_item',
				label: 'Product Item',
				reqd: 1,
				get_query: () => ({
					filters: { item_group: 'Product' }
				})
			},
			parent: $container,
			render_input: true
		});

		// Alloy
		this.controls.alloy = frappe.ui.form.make_control({
			df: {
				fieldtype: 'Link',
				options: 'Item',
				fieldname: 'alloy',
				label: 'Alloy',
				reqd: 1,
				get_query: () => ({
					filters: { item_group: 'Alloy' }
				})
			},
			parent: $container,
			render_input: true
		});

		// Temper
		this.controls.temper = frappe.ui.form.make_control({
			df: {
				fieldtype: 'Link',
				options: 'Temper',
				fieldname: 'temper',
				label: 'Temper'
			},
			parent: $container,
			render_input: true
		});

		// Width
		this.controls.width_mm = frappe.ui.form.make_control({
			df: {
				fieldtype: 'Float',
				fieldname: 'width_mm',
				label: 'Width (mm)',
				reqd: 1,
				precision: 2
			},
			parent: $container,
			render_input: true
		});

		// Final Gauge
		this.controls.final_gauge_mm = frappe.ui.form.make_control({
			df: {
				fieldtype: 'Float',
				fieldname: 'final_gauge_mm',
				label: 'Final Gauge (mm)',
				reqd: 1,
				precision: 3
			},
			parent: $container,
			render_input: true
		});
	}

	make_downtime_fields() {
		const $container = this.$form_container.find('.downtime-fields');

		// Downtime Type
		this.controls.downtime_type = frappe.ui.form.make_control({
			df: {
				fieldtype: 'Select',
				fieldname: 'downtime_type',
				label: 'Downtime Type',
				options: 'Roll Change\nScheduled Maintenance\nBreakdown\nTrial\nOther',
				default: 'Roll Change',
				reqd: 1
			},
			parent: $container,
			render_input: true
		});
		this.controls.downtime_type.set_value('Roll Change');

		// Downtime Reason
		this.controls.downtime_reason = frappe.ui.form.make_control({
			df: {
				fieldtype: 'Small Text',
				fieldname: 'downtime_reason',
				label: 'Reason'
			},
			parent: $container,
			render_input: true
		});
	}

	toggle_plan_type_fields() {
		const plan_type = this.controls.plan_type.get_value();
		const $casting = this.$form_container.find('.casting-fields');
		const $downtime = this.$form_container.find('.downtime-fields');

		if (plan_type === 'Casting') {
			$casting.show();
			$downtime.hide();
		} else {
			$casting.hide();
			$downtime.show();
		}
	}

	bind_events() {
		// Create plan button
		this.$form_container.find('.create-plan-btn').click(() => this.create_plan());

		// Clear form button
		this.$form_container.find('.clear-form-btn').click(() => this.clear_form());
	}

	load_timeline() {
		const caster = this.controls.caster.get_value();
		const date = this.controls.plan_date.get_value();

		if (!caster || !date) {
			this.$timeline.html(`
				<div class="text-center text-muted" style="padding:60px 20px;">
					<i class="fa fa-calendar-o fa-3x mb-3 d-block"></i>
					Select a caster and date to view schedule
				</div>
			`);
			this.$timeline_info.text('');
			return;
		}

		this.$timeline.html(`
			<div class="text-center" style="padding:60px 20px;">
				<i class="fa fa-spinner fa-spin fa-2x"></i>
				<p class="mt-3">Loading schedule...</p>
			</div>
		`);

		frappe.call({
			method: 'swynix_mes.swynix_mes.api.ppc_caster_kiosk.get_plans_for_day',
			args: { caster, date },
			callback: (r) => {
				const plans = r.message || [];
				this.$timeline_info.text(`${plans.length} plan(s) for ${frappe.datetime.str_to_user(date)}`);

				if (plans.length === 0) {
					this.$timeline.html(`
						<div class="text-center text-muted" style="padding:60px 20px;">
							<i class="fa fa-calendar-check-o fa-3x mb-3 d-block"></i>
							<p>No plans scheduled for this day</p>
						</div>
					`);
					return;
				}

				// Sort by start time
				plans.sort((a, b) => new Date(a.start_datetime) - new Date(b.start_datetime));
				this.render_timeline(plans);
			}
		});
	}

	render_timeline(plans) {
		let html = '<div class="timeline-plans">';

		plans.forEach(p => {
			const planClass = p.plan_type === 'Casting' ? 'casting' : 'downtime';
			const badgeColor = p.plan_type === 'Casting' ? 'green' : 'red';
			const startTime = this.format_time(p.start_datetime);
			const endTime = this.format_time(p.end_datetime);
			const duration = this.calculate_duration(p.start_datetime, p.end_datetime);

			let details = '';
			if (p.plan_type === 'Casting') {
				details = `
					<div class="mt-2">
						<strong>${frappe.utils.escape_html(p.product_item || 'N/A')}</strong><br>
						<span class="text-muted">
							Alloy: ${frappe.utils.escape_html(p.alloy || 'N/A')} | 
							Temper: ${frappe.utils.escape_html(p.temper || 'N/A')}<br>
							Width: ${p.width_mm || 'N/A'} mm | 
							Gauge: ${p.final_gauge_mm || 'N/A'} mm |
							Weight: ${p.planned_weight_mt || 'N/A'} MT
						</span>
					</div>
				`;
			} else {
				details = `
					<div class="mt-2">
						<strong>${frappe.utils.escape_html(p.downtime_type || 'Downtime')}</strong><br>
						<span class="text-muted">${frappe.utils.escape_html(p.downtime_reason || 'No reason specified')}</span>
					</div>
				`;
			}

			html += `
				<div class="plan-block ${planClass}" style="padding:15px; margin-bottom:10px; border-radius:8px; border-left:4px solid var(--${badgeColor}); background:var(--card-bg); box-shadow:0 1px 3px rgba(0,0,0,0.08);">
					<div class="d-flex justify-content-between align-items-center">
						<span class="badge badge-${badgeColor === 'green' ? 'success' : 'danger'}" style="font-size:11px;">${p.plan_type}</span>
						<span class="text-muted small">${startTime} - ${endTime} (${duration})</span>
					</div>
					${details}
					<div class="mt-2 d-flex align-items-center">
						<a href="/app/ppc-casting-plan/${p.name}" class="text-primary small">
							<i class="fa fa-external-link"></i> ${p.name}
						</a>
						<span class="ml-3 text-muted small">Status: <strong>${p.status}</strong></span>
					</div>
				</div>
			`;
		});

		html += '</div>';
		this.$timeline.html(html);
	}

	format_time(datetime) {
		if (!datetime) return '';
		const d = new Date(datetime);
		return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });
	}

	calculate_duration(start, end) {
		if (!start || !end) return '';
		const s = new Date(start);
		const e = new Date(end);
		const diffMs = e - s;
		const diffMins = Math.round(diffMs / 60000);
		if (diffMins < 60) {
			return `${diffMins} min`;
		}
		const hours = Math.floor(diffMins / 60);
		const mins = diffMins % 60;
		return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
	}

	create_plan() {
		const caster = this.controls.caster.get_value();
		const plan_type = this.controls.plan_type.get_value();
		const start_datetime = this.controls.start_datetime.get_value();
		const end_datetime = this.controls.end_datetime.get_value();

		// Validation
		if (!caster) {
			frappe.msgprint({ title: 'Validation Error', indicator: 'red', message: 'Please select a Caster in the filter above' });
			return;
		}
		if (!start_datetime || !end_datetime) {
			frappe.msgprint({ title: 'Validation Error', indicator: 'red', message: 'Please enter Start and End datetime' });
			return;
		}

		const data = {
			caster: caster,
			plan_type: plan_type,
			start_datetime: start_datetime,
			end_datetime: end_datetime,
			furnace: this.controls.furnace.get_value() || null,
			planned_weight_mt: this.controls.planned_weight_mt.get_value() || null
		};

		if (plan_type === 'Casting') {
			data.product_item = this.controls.product_item.get_value();
			data.alloy = this.controls.alloy.get_value();
			data.temper = this.controls.temper.get_value();
			data.width_mm = this.controls.width_mm.get_value() || null;
			data.final_gauge_mm = this.controls.final_gauge_mm.get_value() || null;

			// Casting validation
			if (!data.product_item) {
				frappe.msgprint({ title: 'Validation Error', indicator: 'red', message: 'Product Item is required for Casting' });
				return;
			}
			if (!data.alloy) {
				frappe.msgprint({ title: 'Validation Error', indicator: 'red', message: 'Alloy is required for Casting' });
				return;
			}
			if (!data.width_mm || data.width_mm <= 0) {
				frappe.msgprint({ title: 'Validation Error', indicator: 'red', message: 'Valid Width (mm) is required for Casting' });
				return;
			}
			if (!data.final_gauge_mm || data.final_gauge_mm <= 0) {
				frappe.msgprint({ title: 'Validation Error', indicator: 'red', message: 'Valid Final Gauge (mm) is required for Casting' });
				return;
			}
		} else {
			data.downtime_type = this.controls.downtime_type.get_value();
			data.downtime_reason = this.controls.downtime_reason.get_value();
		}

		frappe.call({
			method: 'swynix_mes.swynix_mes.api.ppc_caster_kiosk.create_plan',
			args: { data: data },
			freeze: true,
			freeze_message: 'Creating plan...',
			callback: (r) => {
				if (r.message) {
					frappe.show_alert({
						message: `Plan <a href="/app/ppc-casting-plan/${r.message}">${r.message}</a> created successfully`,
						indicator: 'green'
					}, 5);
					this.clear_form();
					this.load_timeline();
				}
			}
		});
	}

	clear_form() {
		// Clear all form controls
		const fields_to_clear = [
			'start_datetime', 'end_datetime', 'furnace', 'planned_weight_mt',
			'product_item', 'alloy', 'temper', 'width_mm', 'final_gauge_mm',
			'downtime_reason'
		];

		fields_to_clear.forEach(field => {
			if (this.controls[field]) {
				this.controls[field].set_value('');
			}
		});

		// Reset defaults
		this.controls.plan_type.set_value('Casting');
		this.controls.downtime_type.set_value('Roll Change');
		this.toggle_plan_type_fields();
	}
}
