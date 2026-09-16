# Frappe Cloud Marketplace listing

This file contains the prepared copy and links for the Frappe Cloud Marketplace
submission.

## Identity

- **App name:** `frappe_config_pack`
- **App title:** Frappe Config Pack
- **Category:** Developer
- **GitHub repository:** https://github.com/abdo-host/frappe_config_pack
- **Support URL:** https://github.com/abdo-host/frappe_config_pack/issues
- **Privacy policy URL:** https://github.com/abdo-host/frappe_config_pack/blob/main/PRIVACY.md

## Short description

Safely package, review, and deploy Frappe configuration changes.

## Long description

Frappe Config Pack provides a controlled workflow for moving supported Frappe
configuration between development, staging, and production sites. Build a
portable configuration package from selected resources, inspect its
compatibility, compare it with a target site, and review a dry-run plan before
applying any change.

Deployment actions are explicit and reviewable. Before mutable changes are
applied, the app captures snapshots to support rollback and records the
installation outcome. Drift detection then compares the installed package with
the current target state so administrators can identify configuration changes
made outside the deployment workflow.

Supported resource types include Custom Fields, Property Setters, Workflows,
Workflow States, Roles, Client Scripts, Server Scripts, Notifications, Print
Formats, Reports, and Custom DocPerms.

## Marketplace assets

- **Logo:** `frappe_config_pack/public/images/marketplace-logo.png`
- **Screenshots:** capture the Config Pack Builder and Config Pack Import
  workflows from a real site before submission.
- **Demo video:** record a short end-to-end workflow: build a package, inspect
  it, compare it with a target, run a dry run, and apply or roll back a reviewed
  plan.
