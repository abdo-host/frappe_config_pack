frappe.pages["config-pack-drift"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Configuration Drift"),
		single_column: true,
	});
	const installation = page.add_field({
		fieldname: "installation",
		fieldtype: "Link",
		label: __("Installation"),
		options: "Config Pack Installation",
	});
	const shell = $(
		`<div class="fcp-drift-shell">
			<section class="fcp-drift-hero"><div><p class="fcp-card-kicker">PACKAGE HEALTH</p><h2>${__("Check installed configuration health.")}</h2><p>${__("Compare the installed release checksums with the current target state. This check never restores or changes configuration.")}</p></div><button class="btn btn-primary fcp-check-drift">${__("Check Drift")}</button></section>
			<section class="fcp-drift-selector"><div class="fcp-drift-selector-copy"><p class="fcp-card-kicker">${__("INSTALLATION")}</p><p>${__("Choose the installed release you want to audit.")}</p></div><div class="fcp-drift-controls"></div></section>
			<section class="fcp-drift-results" aria-live="polite"><div class="fcp-drift-empty"><strong>${__("Choose an installation to begin.")}</strong><p>${__("Clean means the installed resource still matches. Modified and Missing require review; nothing is corrected automatically.")}</p></div></section>
		</div>`
	).appendTo(page.body);
	installation.$wrapper
		.removeClass("col-md-2 has-error")
		.addClass("fcp-drift-installation-field")
		.appendTo(shell.find(".fcp-drift-controls"));
	installation.$input.removeClass("input-xs");
	page.page_form.hide();
	const results = shell.find(".fcp-drift-results");
	shell.find(".fcp-check-drift").on("click", () => check_drift());
	const selected = frappe.route_options && frappe.route_options.installation;
	if (selected) {
		installation.set_value(selected);
		delete frappe.route_options.installation;
		check_drift(selected);
	}

	function check_drift(selected_installation) {
		const name = selected_installation || installation.get_value();
		if (!name) {
			frappe.msgprint(__("Select an installation first."));
			return;
		}
		frappe.call({
			method: "frappe_config_pack.api.installations.check_drift",
			args: { installation: name },
			freeze: true,
			freeze_message: __("Comparing installed resources…"),
			callback: ({ message }) => render(message || {}),
		});
	}

	function render(response) {
		const report = response.report || { summary: {}, resources: [] };
		const summary = report.summary || {};
		results.empty();
		const heading = $("<div class='fcp-drift-result-heading'></div>").appendTo(results);
		$("<div></div>")
			.append($("<p class='fcp-card-kicker'></p>").text(__(report.healthy ? "HEALTHY RELEASE" : "REVIEW REQUIRED")))
			.append($("<h3></h3>").text(response.package_name || installation.get_value()))
			.appendTo(heading);
		$("<span class='fcp-drift-health'></span>").addClass(report.healthy ? "is-clean" : "is-attention").text(report.healthy ? __("Clean") : __("Attention Needed")).appendTo(heading);
		const summary_grid = $("<div class='fcp-drift-summary'></div>").appendTo(results);
		["Clean", "Modified", "Missing"].forEach((status) => {
			$("<div class='fcp-drift-stat'></div>").append($("<span></span>").text(__(status))).append($("<strong></strong>").text(summary[status] || 0)).appendTo(summary_grid);
		});
		const table_wrap = $("<div class='fcp-drift-table-wrap'></div>").appendTo(results);
		const table = $("<table class='table fcp-drift-table'></table>").appendTo(table_wrap);
		table.append(`<thead><tr><th>${__("Resource")}</th><th>${__("Identity")}</th><th>${__("Status")}</th></tr></thead>`);
		const body = $("<tbody></tbody>").appendTo(table);
		(report.resources || []).forEach((item) => {
			const row = $("<tr></tr>").appendTo(body);
			$("<td></td>").text(item.resource_type).appendTo(row);
			$("<td class='fcp-drift-identity'></td>").text(item.identity).appendTo(row);
			$("<td></td>").append($("<span class='fcp-drift-status'></span>").addClass(`is-${item.status.toLowerCase()}`).text(__(item.status))).appendTo(row);
		});
	}
};
