frappe.pages["config-pack-history"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Config Pack History"),
		single_column: true,
	});
	const state = { start: 0, page_length: 20 };
	const shell = $(
		`<div class="fcp-history-shell">
			<section class="fcp-history-hero"><div><p class="fcp-card-kicker">DEPLOYMENT HISTORY</p><h2>Installed configuration releases.</h2><p>Review each release, its restore point, and any rollback safety warnings.</p></div><button class="btn btn-default fcp-history-refresh">Refresh</button></section>
			<section class="fcp-history-results" aria-live="polite"></section>
		</div>`
	).appendTo(page.body);
	const results = shell.find(".fcp-history-results");
	shell.find(".fcp-history-refresh").on("click", () => load(0));
	load(0);

	function load(direction) {
		state.start = direction === 0 ? 0 : Math.max(0, state.start + direction * state.page_length);
		frappe.call({
			method: "frappe_config_pack.api.installations.list_installations",
			args: { start: state.start, page_length: state.page_length },
			callback: ({ message }) => render(message || {}),
		});
	}

	function render(response) {
		const items = response.items || [];
		results.empty();
		if (!items.length) {
			$("<div class='fcp-history-empty'></div>")
				.append($("<strong></strong>").text(__("No Config Pack installations yet.")))
				.append($("<p></p>").text(__("A restore point and history entry are created when a reviewed plan is applied.")))
				.appendTo(results);
			return;
		}

		const table_wrap = $("<div class='fcp-history-table-wrap'></div>").appendTo(results);
		const table = $("<table class='table fcp-history-table'></table>").appendTo(table_wrap);
		table.append(
			`<thead><tr><th>${__("Package")}</th><th>${__("Version")}</th><th>${__("Status")}</th><th>${__("Installed")}</th><th>${__("Actions")}</th></tr></thead>`
		);
		const body = $("<tbody></tbody>").appendTo(table);
		items.forEach((item) => render_row(body, item));
		render_pagination(response);
	}

	function render_row(body, item) {
		const row = $("<tr></tr>").appendTo(body);
		$("<td class='fcp-history-package'></td>").text(item.package_name).appendTo(row);
		$("<td></td>").text(item.package_version).appendTo(row);
		const status = $("<td></td>").appendTo(row);
		$("<span class='fcp-history-status'></span>")
			.addClass(`is-${String(item.status || "").toLowerCase().replace(/\s+/g, "-")}`)
			.text(item.status)
			.appendTo(status);
		$("<td></td>").text(item.installed_on || "—").appendTo(row);
		const actions = $("<td class='fcp-history-actions'></td>").appendTo(row);
		$("<button class='btn btn-sm btn-default'></button>")
			.text(__("View"))
			.on("click", () => frappe.set_route("Form", "Config Pack Installation", item.name))
			.appendTo(actions);
		if (item.snapshot) {
			$("<button class='btn btn-sm btn-default'></button>")
				.text(__("Snapshot"))
				.on("click", () => frappe.set_route("Form", "Config Pack Snapshot", item.snapshot))
				.appendTo(actions);
		}
		if (["Installed", "Partially Rolled Back"].includes(item.status)) {
			$("<button class='btn btn-sm btn-default'></button>")
				.text(__("Check Drift"))
				.on("click", () => {
					frappe.route_options = { installation: item.name };
					frappe.set_route("config-pack-drift");
				})
				.appendTo(actions);
		}
		if (["Installed", "Partially Rolled Back"].includes(item.status)) {
			$("<button class='btn btn-sm btn-danger'></button>")
				.text(__("Rollback"))
				.on("click", () => preview_rollback(item.name))
				.appendTo(actions);
		}
	}

	function render_pagination(response) {
		const pagination = $("<div class='fcp-history-pagination'></div>").appendTo(results);
		$("<span></span>").text(__("Page {0}", [state.start / state.page_length + 1])).appendTo(pagination);
		const actions = $("<div></div>").appendTo(pagination);
		$("<button class='btn btn-sm btn-default'></button>")
			.text(__("Previous"))
			.prop("disabled", state.start === 0)
			.on("click", () => load(-1))
			.appendTo(actions);
		$("<button class='btn btn-sm btn-default'></button>")
			.text(__("Next"))
			.prop("disabled", !response.has_more)
			.on("click", () => load(1))
			.appendTo(actions);
	}

	function preview_rollback(installation) {
		frappe.call({
			method: "frappe_config_pack.api.installations.get_rollback_preview",
			args: { installation },
			freeze: true,
			freeze_message: __("Checking rollback safety…"),
			callback: ({ message }) => show_rollback_dialog(installation, message || {}),
		});
	}

	function show_rollback_dialog(installation, preview) {
		const warnings = preview.warnings || [];
		if (!warnings.length) {
			frappe.confirm(
				__("Restore this installation's snapshot? The current resources match the installed release."),
				() => execute_rollback(installation, false)
			);
			return;
		}
		const warning_list = $("<ul></ul>");
		warnings.forEach((warning) => {
			$("<li></li>")
				.text(`${warning.resource_type}: ${warning.resource_identity}`)
				.appendTo(warning_list);
		});
		const dialog = new frappe.ui.Dialog({
			title: __("Local changes detected"),
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "warning_details",
					options: $("<div></div>")
						.append($("<p></p>").text(__("These resources changed after this release was installed:")))
						.append(warning_list)
						.append($("<p></p>").text(__("Skip keeps those local changes. Force Restore overwrites them.")))
						.prop("outerHTML"),
				},
			],
		});
		dialog.set_primary_action(__("Force Restore"), () => {
			dialog.hide();
			execute_rollback(installation, true);
		});
		dialog.set_secondary_action(__("Skip Modified Resources"), () => {
			dialog.hide();
			execute_rollback(installation, false);
		});
		dialog.show();
	}

	function execute_rollback(installation, force) {
		frappe.call({
			method: "frappe_config_pack.api.installations.rollback_installation",
			args: { installation, force: force ? 1 : 0 },
			freeze: true,
			freeze_message: __("Restoring Config Pack snapshot…"),
			callback: ({ message }) => {
				const summary = message.result.summary;
				frappe.show_alert({
					message: __("Rollback complete: {0} restored, {1} deleted, {2} skipped.", [summary.Restored, summary.Deleted, summary.Skipped]),
					indicator: summary.Skipped ? "orange" : "green",
				});
				load(0);
			},
		});
	}
};
