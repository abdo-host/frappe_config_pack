# Changelog

All notable changes to Frappe Config Pack are documented here.

## [1.0.0] - 2026-09-16

### Added

- Deterministic, inspectable `.fpack` archives for selected Frappe configuration.
- Builder, import inspection, preflight, field-level comparison, reviewed dry runs, and guarded apply actions.
- Dependency analysis, snapshots, installation history, drift checks, and guarded rollback.
- Bench CLI commands for listing, building, exporting, inspecting, comparing, dry-running, applying, auditing drift, and rolling back packages.
- Dedicated handlers for Custom Field, Property Setter, Client Script, Workflow, Workflow State, Role, Custom DocPerm, Server Script, Notification, Print Format, and Report.

### Security

- Packages are validated as untrusted input and unsafe archive layouts are rejected.
- Notification Slack webhook URLs are never serialized into a package.
- Server Scripts require an explicitly enabled target capability before deployment.
- Apply and rollback require explicit confirmation and preserve target checksums for review.

### Compatibility

- Supports Frappe Framework 15 and 16 through declared package compatibility constraints.
