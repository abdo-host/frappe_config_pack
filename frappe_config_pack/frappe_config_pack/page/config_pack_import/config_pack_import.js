frappe.pages["config-pack-import"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("Import Config Pack"),
        single_column: true,
    });
    const state = {file_name: null, selections: {}, expected_target_checksums: {}, plan: null};
    const shell = $(
        `<div class="fcp-import-shell">
			<section class="fcp-import-hero"><div><p class="fcp-eyebrow">CONFIG PACK IMPORT</p><h2>Review package changes before applying them.</h2><p class="fcp-hero-copy">Upload, inspect, compare, then apply the actions you choose.</p></div><div class="fcp-trust-note"><span>✓</span><div><strong>Preview-first workflow</strong><small>No configuration changes during inspection or dry run.</small></div></div></section>
			<nav class="fcp-workflow" aria-label="Import workflow"><div class="fcp-step" data-stage="1"><span>1</span><div><strong>Upload</strong><small>Choose a .fpack file</small></div></div><div class="fcp-step" data-stage="2"><span>2</span><div><strong>Inspect</strong><small>Validate compatibility</small></div></div><div class="fcp-step" data-stage="3"><span>3</span><div><strong>Review</strong><small>Resolve every change</small></div></div><div class="fcp-step" data-stage="4"><span>4</span><div><strong>Apply</strong><small>Run reviewed plan</small></div></div></nav>
			<div class="fcp-import-layout"><main class="fcp-import-main"><section class="fcp-upload-card"><div class="fcp-upload-icon">⇧</div><div><p class="fcp-card-kicker">START HERE</p><h3>Import a Config Pack</h3><p>Only <code>.fpack</code> archives are accepted. The first step is always inspection—nothing is applied automatically.</p></div><button class="btn btn-primary fcp-start-upload">Upload .fpack</button></section><div class="config-pack-import-results"></div><div class="config-pack-diff-results"></div></main><aside class="fcp-import-guide"><p class="fcp-card-kicker">HOW IT STAYS SAFE</p><ol><li><strong>Compatibility first</strong><span>Unsupported packages stop before comparison.</span></li><li><strong>Explicit choices</strong><span>Modified resources require a review action.</span></li><li><strong>Fresh target check</strong><span>The target is verified again right before apply.</span></li></ol></aside></div>
		</div>`
    ).appendTo(page.body);
    const results = shell.find(".config-pack-import-results");
    const diff_results = shell.find(".config-pack-diff-results");
    page.set_primary_action(__("Upload .fpack"), () => upload_pack());
    shell.find(".fcp-start-upload").on("click", () => upload_pack());
    set_stage(1);

    function set_stage(stage) {
        shell.find(".fcp-step").each(function () {
            const step = $(this);
            const position = Number(step.data("stage"));
            step.toggleClass("is-complete", position < stage);
            step.toggleClass("is-active", position === stage);
        });
    }

    function upload_pack() {
        new frappe.ui.FileUploader({
            dialog_title: __("Upload private Config Pack"),
            allow_multiple: false,
            restrictions: {allowed_file_types: [".fpack"]},
            upload_notes: __("The archive is inspected only; no configuration will be applied."),
            on_success: (file) => inspect_pack(file.name),
        });
    }

    function inspect_pack(file_name) {
        frappe.call({
            method: "frappe_config_pack.api.import_pack.inspect_uploaded_package",
            args: {file_name},
            freeze: true,
            freeze_message: __("Inspecting Config Pack…"),
            callback: ({message}) => {
                state.file_name = message.file_name;
                render_result(message);
            },
        });
    }

    function render_result(result) {
        results.empty();
        set_stage(2);
        const preflight = $("<section class='fcp-panel'></section>").appendTo(results);
        const indicator = {
            Compatible: "green",
            "Compatible With Warnings": "orange",
            Incompatible: "red",
        }[result.status] || "red";
        const heading = $("<div class='fcp-panel-header'></div>").appendTo(preflight);
        $("<div><p class='fcp-card-kicker'>PACKAGE PREFLIGHT</p><h3></h3></div>").find("h3").text(__("Preflight: {0}", [result.status])).end().appendTo(heading);
        $("<span class='fcp-status-badge'></span>").addClass(`is-${indicator}`).text(result.status).appendTo(heading);
        frappe.show_alert({message: __("Preflight: {0}", [result.status]), indicator});
        if (result.package) {
            const package_details = $("<div class='fcp-detail-grid'></div>").appendTo(preflight);
            add_detail(package_details, __("Package"), result.package.name);
            add_detail(package_details, __("Version"), result.package.version);
            add_detail(package_details, __("Format"), result.package.format_version);
            add_detail(package_details, __("Checksum"), result.package.package_checksum);
        }
        const resource_types = Object.entries(result.resources || {});
        if (resource_types.length) {
            const resource_details = $("<div class='fcp-resource-summary'></div>").appendTo(preflight);
            $("<h5></h5>").text(__("Validated Resources")).appendTo(resource_details);
            resource_types.forEach(([type, count]) => add_detail(resource_details, type, count));
        }
        const issues = result.issues || [];
        if (issues.length) {
            const list = $("<ul class='fcp-issue-list'></ul>").appendTo(preflight);
            issues.forEach((issue) => {
                $("<li></li>").text(`${issue.severity}: ${issue.message}`).appendTo(list);
            });
        }
        $("<p class='fcp-next-step'></p>")
            .text(__("Inspect and compare the package before preparing a dry run."))
            .appendTo(preflight);
        if (result.status !== "Incompatible") {
            $("<button class='btn btn-primary fcp-next-action'></button>")
                .text(__("Compare with Target"))
                .on("click", () => compare_target())
                .appendTo(preflight);
        }
    }

    function compare_target() {
        if (!state.file_name) {
            frappe.msgprint(__("Upload and inspect a Config Pack first."));
            return;
        }
        frappe.call({
            method: "frappe_config_pack.api.diff.compare_uploaded_package",
            args: {file_name: state.file_name},
            freeze: true,
            freeze_message: __("Comparing target configuration…"),
            callback: ({message}) => render_diff(message),
        });
    }

    function render_diff(result) {
        diff_results.empty();
        set_stage(3);
        state.selections = {};
        state.expected_target_checksums = {};
        state.plan = null;
        if (!result.diff) {
            $("<p class='text-danger'></p>")
                .text(__("Target comparison is blocked until preflight is compatible."))
                .appendTo(diff_results);
            return;
        }
        const review = $("<section class='fcp-panel'></section>").appendTo(diff_results);
        $("<div><p class='fcp-card-kicker'>TARGET REVIEW</p><h3>Target Comparison</h3><p class='fcp-next-step'>Choose a clear action for each resource before the dry run.</p></div>").appendTo(review);
        const summary = $("<div class='fcp-summary-grid'></div>").appendTo(review);
        Object.entries(result.diff.summary).forEach(([state_name, count]) => add_detail(summary, state_name, count));
        const filter = $("<select class='custom-select mb-3'></select>").appendTo(review);
        ["All", "NEW", "MODIFIED", "CONFLICT", "UNCHANGED", "MISSING_DEPENDENCY"].forEach((state_name) => {
            $("<option></option>").attr("value", state_name).text(state_name).appendTo(filter);
        });
        const table_container = $("<div class='fcp-table-wrap'></div>").appendTo(review);
        const actions_container = $("<div class='fcp-review-actions'></div>").appendTo(review);
        const render_rows = () => {
            const selected = filter.val();
            const resources = result.diff.resources.filter(
                (resource) => selected === "All" || resource.state === selected
            );
            table_container.empty();
            if (!resources.length) {
                $("<p class='text-muted'></p>").text(__("No resources match this filter.")).appendTo(table_container);
                return;
            }
            const table = $("<table class='table table-bordered fcp-review-table mb-3'></table>").appendTo(table_container);
            table.append(`<thead><tr><th>${__("Type")}</th><th>${__("Identity")}</th><th>${__("State")}</th><th></th></tr></thead>`);
            const body = $("<tbody></tbody>").appendTo(table);
            resources.forEach((resource) => {
                const row = $("<tr></tr>").appendTo(body);
                $("<td></td>").text(resource.resource_type).appendTo(row);
                $("<td></td>").text(resource.identity).appendTo(row);
                $("<td></td>").text(resource.state).appendTo(row);
                const actions = $("<td></td>").appendTo(row);
                const action_select = $("<select class='custom-select input-sm mb-2'></select>").appendTo(actions);
                configure_action_select(action_select, resource);
                $("<button class='btn btn-sm btn-default'></button>")
                    .text(__("Show Changes"))
                    .on("click", () => render_field_differences(resource))
                    .appendTo(actions);
            });
        };
        filter.on("change", render_rows);
        render_rows();
        $("<button class='btn btn-primary'></button>")
            .text(__("Validate Plan"))
            .on("click", () => run_dry_run())
            .appendTo(actions_container);
    }

    function configure_action_select(select, resource) {
        const key = resource.resource_type + ":" + resource.identity;
        const options = {
            NEW: ["Create", "Skip"],
            UNCHANGED: ["Skip"],
            MODIFIED: ["", "Safe Update", "Skip"],
            CONFLICT: ["", "Keep Target", "Use Package", "Skip"],
            MISSING_DEPENDENCY: [],
        }[resource.state] || [];
        if (!options.length) {
            select.prop("disabled", true);
            $("<option></option>").text(__("Blocked")).appendTo(select);
            return;
        }
        options.forEach((option) => {
            $("<option></option>").attr("value", option).text(option || __("Choose action")).appendTo(select);
        });
        if (state.selections[key]) {
            select.val(state.selections[key]);
        } else if (options[0]) {
            state.selections[key] = options[0];
        }
        select.on("change", () => {
            if (select.val()) {
                state.selections[key] = select.val();
            } else {
                delete state.selections[key];
            }
        });
    }

    function run_dry_run() {
        frappe.call({
            method: "frappe_config_pack.api.deployment.dry_run_uploaded_package",
            args: {file_name: state.file_name, selections: JSON.stringify(state.selections)},
            freeze: true,
            freeze_message: __("Validating deployment plan…"),
            callback: ({message}) => render_plan(message),
        });
    }

    function render_plan(result) {
        state.plan = result.plan;
        if (!result.plan) {
            frappe.msgprint(__("Dry run is blocked by preflight."));
            return;
        }
        state.expected_target_checksums = result.plan.expected_target_checksums;
        // A new validation supersedes the earlier preview and any outcome based on it.
        diff_results.find(".fcp-plan-card, .fcp-apply-result").remove();
        const plan_results = $("<section class='fcp-plan-card'></section>").appendTo(diff_results);
        $("<p class='fcp-card-kicker'>REVIEWED PLAN</p><h3>Dry Run Result</h3>").appendTo(plan_results);
        const plan_summary = $("<div class='fcp-summary-grid'></div>").appendTo(plan_results);
        Object.entries(result.plan.summary).forEach(([label, count]) => add_detail(plan_summary, label, count));
        if (result.plan.blockers.length) {
            const blockers = $("<ul class='text-danger'></ul>").appendTo(plan_results);
            result.plan.blockers.forEach((blocker) => {
                $("<li></li>").text(blocker.identity + ": " + blocker.message).appendTo(blockers);
            });
            return;
        }
        $("<p class='fcp-safe-message'></p>").text(__("Dry run passed. No target configuration was changed.")).appendTo(plan_results);
        $("<button class='btn btn-danger'></button>")
            .text(__("Apply Reviewed Plan"))
            .on("click", () => confirm_apply())
            .appendTo(plan_results);
    }

    function confirm_apply() {
        frappe.confirm(
            __("This will create or safely update the explicitly selected target configuration. Continue?"),
            () => apply_plan()
        );
    }

    function apply_plan() {
        frappe.call({
            method: "frappe_config_pack.api.deployment.apply_uploaded_package",
            args: {
                file_name: state.file_name,
                selections: JSON.stringify(state.selections),
                expected_target_checksums: JSON.stringify(state.expected_target_checksums),
            },
            freeze: true,
            freeze_message: __("Applying reviewed Config Pack plan…"),
            callback: ({message}) => render_apply_result(message),
        });
    }

    function render_apply_result(response) {
        const result = response.result;
        if (!result) {
            frappe.msgprint(__("Apply is blocked by preflight."));
            return;
        }
        set_stage(4);
        const applied = $("<section class='fcp-apply-result'></section>").appendTo(diff_results);
        $("<p class='fcp-card-kicker'>DEPLOYMENT COMPLETE</p><h3>Apply Result</h3>").appendTo(applied);
        const applied_summary = $("<div class='fcp-summary-grid'></div>").appendTo(applied);
        Object.entries(result.summary).forEach(([label, count]) => add_detail(applied_summary, label, count));
        const list = $("<ul class='fcp-applied-list'></ul>").appendTo(applied);
        result.resources.forEach((resource) => {
            $("<li></li>").text(resource.identity + ": " + resource.action + " — " + resource.status).appendTo(list);
        });
        if (response.installation) {
            $("<button class='btn btn-default fcp-view-installation'></button>")
                .text(__("View Installation"))
                .on("click", () => frappe.set_route("Form", "Config Pack Installation", response.installation.name))
                .appendTo(applied);
        }
    }

    function render_field_differences(resource) {
        const details = $("<section class='fcp-change-details'></section>").appendTo(diff_results);
        $("<h5></h5>").text(`${resource.resource_type}: ${resource.identity}`).appendTo(details);
        if (resource.missing_dependencies.length) {
            $("<p class='text-danger'></p>")
                .text(`${__("Missing dependencies")}: ${resource.missing_dependencies.join(", ")}`)
                .appendTo(details);
        }
        if (!resource.field_differences.length) {
            $("<p class='text-muted'></p>").text(__("No field-level changes.")).appendTo(details);
            return;
        }
        const table = $("<table class='table table-bordered'></table>").appendTo(details);
        table.append(`<thead><tr><th>${__("Property")}</th><th>${__("Current")}</th><th>${__("Package")}</th></tr></thead>`);
        const body = $("<tbody></tbody>").appendTo(table);
        resource.field_differences.forEach((difference) => {
            const row = $("<tr></tr>").appendTo(body);
            $("<td></td>").text(difference.field).appendTo(row);
            $("<td></td>").text(display_value(difference.target_value)).appendTo(row);
            $("<td></td>").text(display_value(difference.package_value)).appendTo(row);
        });
    }

    function display_value(value) {
        return typeof value === "object" && value !== null ? JSON.stringify(value) : String(value ?? "");
    }

    function add_detail(container, label, value) {
        const line = $("<div class='fcp-detail'></div>").appendTo(container);
        $("<span></span>").text(label).appendTo(line);
        $("<strong></strong>").text(value).appendTo(line);
    }
};
