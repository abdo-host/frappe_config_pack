frappe.pages["config-pack-builder"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Config Pack Builder"),
		single_column: true,
	});
	const state = { start: 0, page_length: 10, selected_counts: {}, selected_resource_names: {} };
	const pack = page.add_field({
		fieldname: "config_pack",
		fieldtype: "Link",
		label: __("Config Pack"),
		options: "Config Pack",
		reqd: 1,
		change: () => {
			refresh_pack_summary();
		},
	});
	const resource_type = page.add_field({
		fieldname: "resource_type",
		fieldtype: "Select",
		label: __("Resource Type"),
		options: "All",
	});
	const query = page.add_field({
		fieldname: "query",
		fieldtype: "Data",
		label: __("Search"),
	});

	const shell = $(
		`<div class="fcp-builder-shell">
			<section class="fcp-builder-hero">
				<div class="fcp-builder-hero-copy"><p class="fcp-card-kicker">CONFIG PACK BUILDER</p><h2>Build a portable configuration package.</h2><p>Browse one resource type or search across all supported configuration resources.</p><div class="fcp-builder-pack-summary" aria-live="polite"></div></div>
				<div class="fcp-builder-hero-actions"><button class="btn fcp-scan-dependencies"><i class="fa fa-sitemap" aria-hidden="true"></i>${__("Scan Dependencies")}</button><button class="btn fcp-build-pack"><i class="fa fa-cube" aria-hidden="true"></i>${__("Build Package")}</button><button class="btn btn-primary fcp-create-pack">${__("Create Config Pack")}</button></div>
			</section>
			<section class="fcp-builder-search-card">
				<div class="fcp-builder-card-heading"><div><p class="fcp-card-kicker">RESOURCE BROWSER</p><h3>Find configuration resources</h3><p>Use <strong>All</strong> to browse results grouped by resource type.</p></div></div>
				<div class="fcp-builder-controls"></div>
				<div class="fcp-builder-search-actions"><button class="btn btn-primary fcp-search-resources">Search Resources</button></div>
			</section>
			<section class="fcp-builder-results" aria-live="polite"></section>
		</div>`
	).appendTo(page.body);
	const controls = shell.find(".fcp-builder-controls");
	const results = shell.find(".fcp-builder-results");
	const pack_summary = shell.find(".fcp-builder-pack-summary");
	const search_resources_button = shell.find(".fcp-search-resources");

	[pack, resource_type, query].forEach((control) => control.$wrapper.appendTo(controls));
	page.page_form.hide();
	pack.$wrapper.removeClass("has-error");
	render_pack_summary();
	shell.find(".fcp-create-pack").on("click", () => frappe.new_doc("Config Pack"));
	shell.find(".fcp-scan-dependencies").on("click", () => scan_dependencies(false));
	shell.find(".fcp-build-pack").on("click", () => build_pack());
	search_resources_button.on("click", () => load_resources(0));
	query.$wrapper.find("input").on("keydown", (event) => {
		if (event.key === "Enter") {
			event.preventDefault();
			load_resources(0);
		}
	});

	frappe.call({
		method: "frappe_config_pack.api.package.get_supported_resource_types",
		callback: ({ message }) => {
			resource_type.df.options = ["All", ...(message || [])];
			resource_type.refresh();
			resource_type.set_value("All");
		},
	});

	function load_resources(direction) {
		if (!pack.get_value()) {
			pack.$wrapper.addClass("has-error");
			pack.$wrapper.find("input").trigger("focus");
			frappe.msgprint({
				title: __("Choose a Config Pack first"),
				indicator: "orange",
				message: __(
					"Select the Config Pack you want to work on before searching. This lets us show which resources are already included in that pack."
				),
			});
			return;
		}
		pack.$wrapper.removeClass("has-error");
		state.start = direction === 0 ? 0 : Math.max(0, state.start + direction * state.page_length);
		frappe.call({
			method: "frappe_config_pack.api.package.search_resources",
			args: {
				resource_type: resource_type.get_value() || "All",
				query: query.get_value() || "",
				start: state.start,
				page_length: state.page_length,
				config_pack: pack.get_value() || null,
			},
			freeze: true,
			freeze_message: __("Searching configuration resources…"),
			callback: ({ message }) => render_results(message || {}),
		});
	}

	function refresh_pack_summary() {
		const config_pack = pack.get_value();
		if (!config_pack) {
			render_pack_summary();
			return;
		}
		frappe.call({
			method: "frappe_config_pack.api.package.get_config_pack_summary",
			args: { config_pack },
			callback: ({ message }) => {
				if (pack.get_value() === config_pack) render_pack_summary(message || {});
			},
		});
	}

	function render_pack_summary(summary) {
		pack_summary.empty();
		if (!summary || !summary.name) {
			$("<span class='fcp-pack-summary-empty'></span>")
				.text(__("Select a Config Pack to see its build scope."))
				.appendTo(pack_summary);
			return;
		}
		const heading = $("<div class='fcp-pack-summary-heading'></div>").appendTo(pack_summary);
		$("<span class='fcp-card-kicker'></span>").text(__("BUILD SCOPE")).appendTo(heading);
		$("<strong></strong>").text(summary.package_name).appendTo(heading);
		$("<span class='fcp-pack-version'></span>").text(`v${summary.version}`).appendTo(heading);
		const stats = $("<div class='fcp-pack-stats'></div>").appendTo(pack_summary);
		const counts = summary.selected_counts || {};
		if (!summary.selected_count) {
			$("<span class='fcp-pack-summary-empty'></span>")
				.text(__("No resources selected yet."))
				.appendTo(stats);
			return;
		}
		Object.entries(counts).forEach(([resource_type, count]) => {
			$("<span class='fcp-pack-stat'></span>")
				.append($("<strong></strong>").text(count))
				.append($("<span></span>").text(resource_type))
				.appendTo(stats);
		});
	}

	function render_results(message) {
		const sections = message.is_all
			? message.sections || []
			: [{ resource_type: resource_type.get_value(), items: message.items || [] }];
		const item_count = sections.reduce((count, section) => count + section.items.length, 0);
		results.empty();
		state.selected_counts = message.selected_counts || {};
		state.selected_resource_names = message.selected_resource_names || {};

		if (!item_count) {
			$("<div class='fcp-builder-empty'></div>")
				.append($("<strong></strong>").text(__("No resources found.")))
				.append($("<p></p>").text(__("Try another search term or resource type.")))
				.appendTo(results);
			return;
		}

		const heading = $("<div class='fcp-builder-results-heading'></div>").appendTo(results);
		$("<div><p class='fcp-card-kicker'>SEARCH RESULTS</p><h3></h3></div>")
			.find("h3")
			.text(message.is_all ? __("All resource types") : resource_type.get_value())
			.end()
			.appendTo(heading);
		$("<span class='fcp-results-count'></span>")
			.text(__("{0} shown", [item_count]))
			.appendTo(heading);

		sections.forEach((section) => render_section(section));
		render_pagination(message);
	}

	function render_section(section) {
		const resource_section = $("<section class='fcp-resource-section'></section>").appendTo(results);
		const section_heading = $("<div class='fcp-resource-section-heading'></div>").appendTo(resource_section);
		const title = $("<h4></h4>").text(section.resource_type).appendTo(section_heading);
		$("<span class='fcp-selected-count'></span>")
			.data("resource-type", section.resource_type)
			.toggleClass("is-empty", !selected_count(section.resource_type))
			.text(__("{0} selected", [selected_count(section.resource_type)]))
			.appendTo(title);
		if (section.resource_type === "Custom DocPerm") {
			$("<span class='fcp-security-change'></span>").text(__("Security change")).appendTo(title);
		}
		const section_actions = $("<div class='fcp-resource-section-actions'></div>").appendTo(section_heading);
		const table_toolbar = $("<div class='fcp-resource-table-toolbar'></div>").appendTo(section_actions);
		const table_search = $("<input type='search' class='form-control fcp-resource-table-search'>")
			.attr("placeholder", __("Filter this table"))
			.attr("aria-label", __("Filter {0} results", [section.resource_type]))
			.appendTo(table_toolbar);
		$("<span class='fcp-resource-section-results-count'></span>")
			.text(__("{0} results", [section.items.length]))
			.appendTo(section_actions);
		const table_wrap = $("<div class='fcp-builder-table-wrap'></div>").appendTo(resource_section);
		const table = $("<table class='table fcp-builder-table'></table>").appendTo(table_wrap);
		table.append(
			`<thead><tr><th>${__("Resource")}</th><th>${__("Identity")}</th><th>${__("Reference DocType")}</th><th>${__("Action")}</th></tr></thead>`
		);
		const body = $("<tbody></tbody>").appendTo(table);
		section.items.forEach((item) => {
			const row = $("<tr></tr>").appendTo(body);
			row.data(
				"search-text",
				[item.display_name || item.resource_name, item.resource_identity, item.reference_doctype || ""]
					.join(" ")
					.toLowerCase()
			);
			$("<td class='fcp-resource-name'></td>").text(item.display_name || item.resource_name).appendTo(row);
			$("<td class='fcp-resource-identity'></td>").text(item.resource_identity).appendTo(row);
			$("<td></td>").text(item.reference_doctype || "—").appendTo(row);
			const action = $("<td class='fcp-resource-action'></td>").appendTo(row);
			const button = $("<button class='btn btn-sm btn-primary fcp-add-resource'></button>")
				.text(__("Add to Pack"))
				.appendTo(action);
			if (is_selected(item)) {
				mark_added(button, item);
			} else {
				button.on("click", () => add_resource(item, button));
			}
		});
		const no_match = $("<div class='fcp-resource-table-empty'></div>")
			.text(__("No displayed resources match this filter."))
			.appendTo(resource_section)
			.hide();
		table_search.on("input", () => filter_section_rows(body, no_match, table_search.val()));
	}

	function render_pagination(message) {
		const pagination = $("<div class='fcp-builder-pagination'></div>").appendTo(results);
		const page_number = state.start / state.page_length + 1;
		$("<span></span>")
			.text(message.is_all ? __("Page {0} for every matching type", [page_number]) : __("Page {0}", [page_number]))
			.appendTo(pagination);
		const actions = $("<div></div>").appendTo(pagination);
		$("<button class='btn btn-sm btn-default'></button>")
			.text(__("Previous"))
			.prop("disabled", state.start === 0)
			.on("click", () => load_resources(-1))
			.appendTo(actions);
		$("<button class='btn btn-sm btn-default'></button>")
			.text(__("Next"))
			.prop("disabled", !message.has_more)
			.on("click", () => load_resources(1))
			.appendTo(actions);
	}

	function add_resource(item, button) {
		if (!pack.get_value()) {
			frappe.msgprint(__("Create or select a Config Pack first."));
			return;
		}
		frappe.call({
			method: "frappe_config_pack.api.package.add_resource",
			args: {
				config_pack: pack.get_value(),
				resource_type: item.resource_type,
				resource_name: item.resource_name,
			},
			callback: ({ message }) => {
				frappe.show_alert({ message: message.message, indicator: "green" });
				mark_resource_selected(item);
				mark_added(button, item);
				refresh_pack_summary();
			},
		});
	}

	function remove_resource(item, added_button) {
		const remove_button = added_button.parent().find(".fcp-remove-resource");
		remove_button.prop("disabled", true);
		frappe.call({
			method: "frappe_config_pack.api.package.remove_resource",
			args: {
				config_pack: pack.get_value(),
				resource_type: item.resource_type,
				resource_name: item.resource_name,
			},
			callback: ({ message }) => {
				if (!message.removed) {
					frappe.msgprint(message.message || __("This resource is no longer selected."));
					remove_button.prop("disabled", false);
					return;
				}
				frappe.show_alert({ message: message.message, indicator: "green" });
				mark_resource_removed(item, added_button);
				refresh_pack_summary();
			},
		});
	}

	function is_selected(item) {
		return (state.selected_resource_names[item.resource_type] || []).includes(item.resource_name);
	}

	function mark_resource_selected(item) {
		const names = state.selected_resource_names[item.resource_type] || [];
		if (names.includes(item.resource_name)) return;
		state.selected_resource_names[item.resource_type] = [...names, item.resource_name];
		state.selected_counts[item.resource_type] = selected_count(item.resource_type) + 1;
		update_selected_badge(item.resource_type);
	}

	function mark_added(button, item) {
		button
			.empty()
			.append("<i class='fa fa-check' aria-hidden='true'></i>")
			.append(document.createTextNode(` ${__("Added")}`))
			.prop("disabled", true)
			.attr("aria-label", __("Already added to this Config Pack"))
			.removeClass("btn-primary fcp-add-resource")
			.addClass("fcp-resource-added");
	button.parent().find(".fcp-remove-resource").remove();
	$("<button class='btn btn-sm fcp-remove-resource'></button>")
		.append("<i class='fa fa-times' aria-hidden='true'></i>")
		.append(document.createTextNode(` ${__("Remove")}`))
		.attr("aria-label", __("Remove from this Config Pack"))
		.on("click", () => remove_resource(item, button))
		.appendTo(button.parent());
	}

	function mark_resource_removed(item, added_button) {
		state.selected_resource_names[item.resource_type] = (state.selected_resource_names[item.resource_type] || []).filter(
			(resource_name) => resource_name !== item.resource_name
		);
		state.selected_counts[item.resource_type] = Math.max(0, selected_count(item.resource_type) - 1);
		update_selected_badge(item.resource_type);
		added_button
			.empty()
			.text(__("Add to Pack"))
			.prop("disabled", false)
			.removeAttr("aria-label")
			.removeClass("fcp-resource-added")
			.addClass("btn-primary fcp-add-resource")
			.off("click")
			.on("click", () => add_resource(item, added_button));
		added_button.parent().find(".fcp-remove-resource").remove();
	}

	function filter_section_rows(body, no_match, value) {
		const query_value = String(value || "").trim().toLowerCase();
		let matches = 0;
		body.children("tr").each(function () {
			const row = $(this);
			const visible = !query_value || row.data("search-text").includes(query_value);
			row.toggle(visible);
			if (visible) matches += 1;
		});
		no_match.toggle(!matches);
	}

	function selected_count(resource_type) {
		return state.selected_counts[resource_type] || 0;
	}

	function update_selected_badge(resource_type) {
		results.find(".fcp-selected-count").each(function () {
			const badge = $(this);
			if (badge.data("resource-type") !== resource_type) return;
			badge
				.toggleClass("is-empty", !selected_count(resource_type))
				.text(__("{0} selected", [selected_count(resource_type)]));
		});
	}

	function scan_dependencies(add_missing) {
		if (!pack.get_value()) {
			frappe.msgprint(__("Select a Config Pack first."));
			return;
		}
		frappe.call({
			method: "frappe_config_pack.api.package.scan_dependencies",
			args: { config_pack: pack.get_value(), add_missing: add_missing ? 1 : 0 },
			freeze: true,
			freeze_message: __("Scanning declared dependencies…"),
			callback: ({ message }) => {
				const missing = message.missing || [];
				const addable = missing.filter((dependency) => dependency.kind === "Resource");
				if (add_missing) {
					frappe.show_alert({
						message: __("Added {0} dependency resources.", [message.added.length]),
						indicator: message.unresolved.length ? "orange" : "green",
					});
					refresh_pack_summary();
					return;
				}
				if (!missing.length) {
					frappe.show_alert({ message: __("All declared dependencies are already included or valid."), indicator: "green" });
					return;
				}
				const labels = missing.map((dependency) => dependency.label).join("\n");
				frappe.msgprint({ title: __("Dependencies found"), message: `<pre>${frappe.utils.escape_html(labels)}</pre>` });
				if (addable.length) {
					frappe.confirm(
						__("Add {0} packageable dependencies to this Config Pack?", [addable.length]),
						() => scan_dependencies(true)
					);
				}
			},
		});
	}

	function build_pack() {
		if (!pack.get_value()) {
			frappe.msgprint(__("Select a Config Pack first."));
			return;
		}
		frappe.call({
			method: "frappe_config_pack.api.package.build_package",
			args: { config_pack: pack.get_value() },
			freeze: true,
			freeze_message: __("Building Config Pack…"),
			callback: ({ message }) => {
				frappe.show_alert({ message: __("Package built successfully."), indicator: "green" });
				window.open(message.file_url, "_blank", "noopener");
			},
		});
	}
};
