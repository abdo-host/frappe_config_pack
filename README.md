# Frappe Config Pack

**Safe, versioned configuration releases for Frappe Framework.**

Frappe Config Pack turns a deliberately selected set of Frappe configuration into a portable, inspectable `.fpack` release artifact. On a target site, the artifact is validated, compared with the live configuration, reviewed through a dry run, snapshotted, and only then applied.

The central promise is simple:

> Know exactly what will change before touching UAT or Production.

It also keeps a record of installed releases, detects configuration drift after deployment, and provides a guarded rollback path.

## Contents

- [Why Frappe Config Pack?](#why-frappe-config-pack)
- [What it is and is not](#what-it-is-and-is-not)
- [Supported configuration](#supported-configuration)
- [Release lifecycle](#release-lifecycle)
- [Safety model](#safety-model)
- [Requirements and installation](#requirements-and-installation)
- [Using the Desk workspace](#using-the-desk-workspace)
- [CLI reference](#cli-reference)
- [Package format](#package-format)
- [Architecture](#architecture)
- [Deployment states and actions](#deployment-states-and-actions)
- [Security and data boundaries](#security-and-data-boundaries)
- [Operations and troubleshooting](#operations-and-troubleshooting)
- [Development](#development)
- [Roadmap](#roadmap)
- [License](#license)

## Why Frappe Config Pack?

Frappe teams often promote configuration across Development, UAT, and Production using a mixture of fixtures, Export Customizations, JSON files, patches, scripts, and manual copy/paste. That approach works for small changes, but it makes release review and recovery increasingly difficult.

Common problems include:

- forgetting which customizations belong to a release;
- exporting more configuration than intended;
- overwriting a Production customization without seeing the difference first;
- missing a Workflow role, state, or referenced DocType dependency;
- having no reliable record of what was installed and by whom;
- discovering a production-only change too late; and
- having no safe, resource-level restore point.

Frappe Config Pack replaces that ad-hoc handoff with a reviewable release lifecycle. It removes repeated manual inspection and creates a consistent deployment record; the actual time saved depends on a team's release size and approval process, so the project intentionally does not claim a fixed number of hours saved.

## What it is and is not

Frappe Config Pack is **configuration release management** for Frappe sites.

It is designed for this workflow:

```text
Development site
  → choose an explicit configuration scope
  → build a versioned .fpack artifact
  → inspect it on the target site
  → review differences and dependencies
  → dry run
  → snapshot
  → apply approved actions
  → track installation health and drift
  → roll back when explicitly approved
```

It is **not**:

- a Git client or a replacement for Git;
- a remote pull/push/sync tool;
- a replacement for Bench, fixtures, or Export Customizations;
- a whole-site backup, database migration, or application-source migration tool;
- a transactional or master-data synchronization engine; or
- an automatic conflict resolver.

The app complements Frappe's native tools. Its focus is an explicit, inspectable release artifact and a safe target-site deployment decision.

## Supported configuration

The current implementation packages and deploys these resource types:

| Resource type | Typical use |
| --- | --- |
| Custom Field | Add or configure fields on an existing DocType |
| Property Setter | Change metadata properties without editing core DocTypes |
| Client Script | Client-side form behavior |
| Workflow | Approval and document state flow |
| Workflow State | States used by Workflows |
| Role | Role definitions used by configuration |
| Custom DocPerm | Custom per-DocType permission rules; shown as a security change in the builder |
| Server Script | Server-side automation configuration; target must explicitly enable Server Scripts |
| Notification | Custom document notifications and recipient rules, without related credentials |
| Print Format | Custom Jinja/JS print format source and settings |
| Report | Custom report definitions, filters, columns, roles, and report source |

Each type has a dedicated handler responsible for deterministic identity, serialization, validation, comparison, application, and rollback behavior. A package is not a generic dump of arbitrary Frappe records.

Standard Frappe Notifications, Print Formats, and Reports are intentionally excluded. Server Script text is stored and validated as configuration data; it is never executed while an archive is read or inspected. A target package containing Server Scripts is incompatible until its Bench common-site configuration explicitly enables `server_script_enabled`.

### Explicitly out of scope

Do not use a Config Pack for passwords, API keys, OAuth secrets, private keys, session data, payment credentials, or other secrets. It also does not package business or transactional data such as Sales Invoices, Customers, Suppliers, Stock Ledger Entries, GL Entries, or Employees.

## Release lifecycle

```text
SOURCE SITE                                      TARGET SITE
───────────                                      ───────────
Create Config Pack
  → select resources
  → scan dependencies
  → build .fpack
                                                  upload .fpack
                                                    → archive and manifest validation
                                                    → compatibility and dependency preflight
                                                    → field-level target comparison
                                                    → choose actions for changed resources
                                                    → dry run
                                                    → re-check target checksums
                                                    → create restore point
                                                    → apply
                                                    → installation history and drift audit
                                                    → guarded rollback, if required
```

### Benefits in practice

- **Smaller, intentional releases:** a package contains only selected configuration resources.
- **Review before mutation:** target differences and blockers are visible before any target record changes.
- **Reduced deployment risk:** an incoming package cannot silently overwrite an unresolved conflict.
- **Repeatable handoffs:** the same `.fpack` can be inspected on each target environment.
- **Traceability:** installations, per-resource outcomes, and snapshots are persisted in Frappe.
- **Operational visibility:** drift checks identify records changed or deleted after installation.

## Safety model

Safety is the product's primary constraint. Convenience never bypasses these rules.

| Guardrail | Behavior |
| --- | --- |
| Untrusted input | Uploaded `.fpack` archives are validated before their contents are used. Unsafe archive paths, malformed data, unsupported formats, duplicate identities, and checksum mismatches are rejected. |
| Compatibility preflight | Declared Frappe, ERPNext, and required-app version constraints are checked before comparison or deployment. |
| Deterministic checksums | Irrelevant Frappe metadata such as `creation`, `modified`, `owner`, and `idx` does not affect normalized resource checksums. |
| Explicit decisions | Modified resources require `Safe Update` or `Skip`; conflicts require an explicit resolution. |
| Dry run first | A deployment plan is generated without mutating target configuration. |
| Revalidation | Target checksums are checked again immediately before an approved mutation. A stale preview is rejected. |
| Restore point | A snapshot of every resource that may change is captured before deployment. |
| Rollback protection | A rollback skips post-install local changes unless `--force` is explicitly supplied. |
| Drift visibility | Installed checksums are compared with live target state; drift is reported, never corrected automatically. |

## Requirements and installation

### Compatibility

- Frappe Framework **15** or **16**
- ERPNext is optional. When a package declares ERPNext compatibility, the target version is checked during preflight.
- Python **3.10+** for development tooling; use the Python version supported by your Frappe/Bench installation in production.

### Install from a Bench

From an existing Frappe Bench, install the current stable release with the
immutable release tag. Pinning a tag makes the deployment repeatable even
after newer releases are published.

```bash
cd /path/to/frappe-bench
bench get-app --branch v1.0.0 https://github.com/abdo-host/frappe_config_pack.git
bench --site your-site.local install-app frappe_config_pack
bench --site your-site.local migrate
bench build --app frappe_config_pack
bench restart
```

`bench restart` applies to production benches managed by Supervisor or
systemd. In a development bench, run `bench start` instead and refresh the
browser after `bench build`.

### Choose the right branch

| Use case | Command |
| --- | --- |
| Stable, exact production release | `bench get-app --branch v1.0.0 https://github.com/abdo-host/frappe_config_pack.git` |
| Latest stable release | `bench get-app https://github.com/abdo-host/frappe_config_pack.git` (uses the default `main` branch) |
| Development or contribution | `bench get-app --branch develop https://github.com/abdo-host/frappe_config_pack.git` |

After a future app update, run the last three commands again: `migrate`,
`build --app frappe_config_pack`, and `restart` (or restart `bench start` in
a development environment).

After installation, open **Frappe Config Pack** from the Desk workspace. The workspace is available to users with the **System Manager** role.

### Upgrade an existing installation

```bash
cd /path/to/frappe-bench
bench update --apps frappe_config_pack
bench --site your-site.local migrate
bench build --app frappe_config_pack
```

Follow your normal change-management and backup policy before upgrading a production site.

## Using the Desk workspace

The **Frappe Config Pack** workspace provides these entry points:

| Entry point | Purpose |
| --- | --- |
| **New Config Pack** | Define package metadata and select source resources. |
| **Export Config Pack** | Browse supported resources, search, select, scan dependencies, and build a private `.fpack` file. |
| **Import Config Pack** | Upload a package, inspect preflight results, compare the target, dry run, and apply an approved plan. |
| **Deployment History** | Inspect installations, snapshots, rollback preview, and rollback status. |
| **Configuration Drift** | Check an installed release against the current target configuration. |

### Recommended first release

1. On the source site, create a **Config Pack** with a meaningful name, slug, version, description, and compatibility constraints.
2. Open **Export Config Pack**, select only the resources belonging to the release, then run the dependency scan.
3. Build the package and download the generated private `.fpack` file.
4. On UAT or Production, open **Import Config Pack** and upload that file.
5. Resolve every modified resource or conflict deliberately; do not treat a dry run as an approval.
6. Run the dry run, review the plan, and apply only after the target-side review is complete.
7. Use **Deployment History** and **Configuration Drift** as part of normal release follow-up.

## CLI reference

The Bench command group is `config-pack`. Commands use the same package, preflight, diff, dependency, deployment, snapshot, rollback, and drift services as the Desk UI.

Every command that returns structured data supports `--json` for automation-friendly output.

```bash
bench --site your-site.local config-pack --help
```

### Source-site commands

```bash
# Show Config Pack records
bench --site your-site.local config-pack list --json

# Build a package from the selected resources of an existing Config Pack
bench --site your-site.local config-pack build "Sales Customizations" --json

# Write a built private package file to a local path
bench --site your-site.local config-pack export "Sales Customizations" \
  --output ./sales-customizations-1.0.0.fpack
```

### Target-site inspection commands

These commands never mutate target configuration:

```bash
# Validate archive integrity, resource payloads, and target compatibility
bench --site uat.local config-pack inspect ./sales-customizations-1.0.0.fpack --json

# Show target comparison and dependency-related resource state
bench --site uat.local config-pack diff ./sales-customizations-1.0.0.fpack --json

# Build an action plan without applying it
bench --site uat.local config-pack apply ./sales-customizations-1.0.0.fpack --dry-run --json
```

### Applying an approved plan

An apply requires `--yes`, explicit choices for resources that need them, and the target checksums printed by the reviewed dry-run. This protects against a target change that happens between review and mutation.

```bash
bench --site uat.local config-pack apply ./sales-customizations-1.0.0.fpack --dry-run --json

bench --site uat.local config-pack apply ./sales-customizations-1.0.0.fpack --yes \
  --selection "Custom Field:Item.custom_region=Safe Update" \
  --expected-checksum "Custom Field:Item.custom_region=<checksum-from-dry-run>"
```

For a new resource, the dry-run's expected checksum is `null`; express that in the CLI as an empty value after `=`:

```bash
--expected-checksum "Custom Field:Item.custom_region="
```

If preflight fails or the plan has a missing dependency, unresolved conflict, or a modified resource with no selected action, the command exits with a non-zero status and performs no mutation.

### Drift and rollback

```bash
# Read-only health check: Clean, Modified, or Missing per installed resource
bench --site production.local config-pack drift <installation-id> --json

# Restore the package snapshot after explicit confirmation
bench --site production.local config-pack rollback <installation-id> --yes --json

# Overwrite resources changed after installation only when this has been reviewed
bench --site production.local config-pack rollback <installation-id> --yes --force --json
```

`--force` is deliberately separate from `--yes`: confirmation alone does not authorize overwriting later local changes.

## Package format

`.fpack` is a ZIP-compatible, human-inspectable release artifact. Its logical checksum is based on normalized manifest and resource data, not on incidental ZIP byte layout.

An archive contains a manifest, one JSON resource file per selected resource, and integrity metadata:

```text
manifest.json
resources/
  custom_fields/
  property_setters/
  client_scripts/
  workflows/
  workflow_states/
  roles/
meta/
  checksums.json
```

Dependencies are derived from normalized resource payloads during the builder and target preflight; they are not a separate archive member in the current package format. The manifest keeps the package name, slug, version, author, compatibility constraints, required apps, resource counts, and package checksum. Package format version and app version are intentionally independent.

## Architecture

The project is intentionally layered so that Desk pages and CLI commands do not own business logic.

```text
Desk pages / Bench CLI
        │
        ▼
Thin Frappe adapters (API and persistence)
        │
        ▼
Services: build · preflight · diff · dependency · deployment · snapshot · drift
        │
        ▼
Resource registry → dedicated resource handlers
        │
        ▼
Deterministic serializer, checksum, manifest, and safe archive primitives
```

### Key design decisions

- **Resource handlers instead of a monolithic importer:** each supported resource type owns its normalization and Frappe behavior.
- **Deterministic serialization:** equal logical configuration produces equal resource checksums even when irrelevant database metadata differs.
- **Thin UI and API layers:** pages display results and collect decisions; services remain authoritative.
- **Frappe-first:** ERPNext is a supported target when declared, not a hard dependency of the core app.
- **No remote synchronization:** this is deliberately not a competitor to Git-oriented Frappe sync tools.

### Frappe records created by the app

| Record | Role |
| --- | --- |
| `Config Pack` | Source package definition and private built archive reference. |
| `Config Pack Resource` | Selected resource inside a source package definition. |
| `Config Pack Installation` | Target-side release record and aggregate outcome. |
| `Config Pack Installation Item` | Per-resource selected action, checksums, and status. |
| `Config Pack Snapshot` | Restore point associated with an installation. |
| `Config Pack Snapshot Item` | Pre-install state for one mutable resource. |

## Deployment states and actions

| Target state | Meaning | Allowed deployment behavior |
| --- | --- | --- |
| `New` | The target does not contain the resource. | Create by default, or explicitly Skip. |
| `Unchanged` | Target checksum matches the package. | Skip. |
| `Modified` | Target differs from the package. | Choose `Safe Update` or `Skip`. |
| `Conflict` | Target has a conflicting change. | Explicitly choose `Keep Target`, `Use Package`, or `Skip`; otherwise deployment is blocked. |
| `Missing Dependency` | A required resource or DocType is unavailable. | Blocked until the dependency is available. |

The dry run creates a reviewed plan. Apply creates a fresh plan and compares expected target checksums again before changing each resource.

## Security and data boundaries

- Treat every uploaded package as untrusted input.
- The reader rejects unsafe archive layouts and does not execute code from Client Scripts or other package files while validating them.
- Private package files are stored as Frappe private files.
- Packages are configuration artifacts, not secret stores or data exports.
- The app does not automatically apply a package, resolve a conflict, restore drift, or force a rollback.

Run the app under your normal Frappe role, access-control, review, backup, and production-change policies. A Config Pack is an additional release control; it is not a substitute for those controls.

## Operations and troubleshooting

### “Package is incompatible with this site”

Run `inspect --json` and check the reported Frappe, ERPNext, and required-app constraints. Build the package for a compatible target or update the target deliberately.

### “Deployment is blocked until every issue is resolved”

Run `apply <package> --dry-run --json`. Resolve each modified resource or conflict with a `--selection`, and satisfy every missing dependency. A blocked plan is intentionally not deployable.

### “Target resource changed since preview”

The target changed after the reviewed dry run. Run the dry run again, review the new state, and use the newly returned expected checksum. Do not reuse an old checksum to bypass the check.

### Rollback skipped a resource

The resource was changed after installation. Review the local change. Use `--force` only when overwriting that later change is intentional and approved.

### Drift shows no resources

Drift reports resources that were actually applied by an installation. A release whose plan skipped every resource has no installed resource checksum to audit.

## Development

### Local checks

From the app directory:

```bash
python -m pytest frappe_config_pack/tests -q
ruff check frappe_config_pack
```

The project uses `pytest` for automated behavior tests and `ruff` for Python linting. Run the applicable Frappe migration and asset build commands when changing DocTypes, workspace records, JavaScript, or SCSS.

### Contributing principles

1. Read [CONTRIBUTING.md](CONTRIBUTING.md) before making product changes.
2. Keep work phase-based; finish and test one phase before starting the next.
3. Keep business rules in `core`, `services`, and resource handlers—not in UI code.
4. Add automated tests for every new core behavior.
5. Do not add remote pull/push/sync behavior.
6. Never trade safety checks for a shorter deployment path.

## Roadmap

The initial release lifecycle is implemented for the currently supported resource types. Planned work focuses on additional dedicated handlers for configuration resources such as Workspace, Dashboard, Web Form, Translation, and other explicitly approved types.

Future handlers must follow the same registry and safety model. They are not supported merely because their Frappe DocTypes exist.

## License

Copyright © 2026 Abdo Hamoud.

Frappe Config Pack is licensed under the [GNU General Public License v3.0 or later](license.txt).
