"""Shared valid input for package-engine unit tests."""

from __future__ import annotations

from copy import deepcopy

from frappe_config_pack.core.constants import FORMAT_VERSION


def manifest(resource_counts: dict[str, int] | None = None) -> dict:
    counts = resource_counts or {"Custom Field": 1, "Property Setter": 1}
    return {
        "format_version": FORMAT_VERSION,
        "name": "Core customizations",
        "slug": "core-customizations",
        "version": "1.0.0",
        "description": "A deterministic test package",
        "author": "Test Author",
        "created_at": "2026-09-13T19:00:00+03:00",
        "generator": {"app": "frappe_config_pack", "version": "1.0.0"},
        "compatibility": {"frappe": ">=15,<17", "erpnext": None},
        "required_apps": [{"app": "frappe", "version": ">=15,<17"}],
        "resources": counts,
        "total_resources": sum(counts.values()),
    }


def custom_field() -> dict:
    return {
        "name": "Sales Invoice-custom_branch",
        "dt": "Sales Invoice",
        "fieldname": "custom_branch",
        "label": "Branch",
        "fieldtype": "Link",
        "options": "Branch",
        "insert_after": "company",
        "reqd": "0",
        "read_only": 0,
        "hidden": False,
        "modified": "2026-09-13 19:00:00",
        "owner": "Administrator",
    }


def property_setter() -> dict:
    return {
        "name": "Sales Invoice-customer-reqd",
        "doc_type": "Sales Invoice",
        "field_name": "customer",
        "property": "reqd",
        "value": "0",
        "property_type": "Check",
        "doctype_or_field": "DocField",
        "modified": "2026-09-13 19:00:00",
    }


def changed_metadata(document: dict) -> dict:
    result = deepcopy(document)
    result["modified"] = "2030-01-01 00:00:00"
    result["owner"] = "Another User"
    return result
