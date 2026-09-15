"""Thin Frappe adapters for Phase 3 package inspection only."""

from __future__ import annotations

import importlib
from typing import Any

import frappe

from frappe_config_pack.api._uploaded_package import read_private_fpack
from frappe_config_pack.services.dependency_engine import FrappeDependencyTarget
from frappe_config_pack.services.preflight import PackagePreflightService, TargetEnvironment


@frappe.whitelist()
def inspect_uploaded_package(file_name: str) -> dict[str, Any]:
    """Inspect one private uploaded .fpack file without creating target configuration records."""

    file_doc, content = read_private_fpack(file_name)
    result = PackagePreflightService().inspect(content, _target_environment(), FrappeDependencyTarget())
    return {"file_name": file_doc.name, "file_url": file_doc.file_url, **result.as_dict()}


def _target_environment() -> TargetEnvironment:
    """Read installed app metadata only; this does not query or change configuration records."""

    app_versions: dict[str, str] = {}
    for app in frappe.get_installed_apps():
        try:
            module = importlib.import_module(app)
            version = getattr(module, "__version__", None)
        except ImportError:
            continue
        app_versions[app] = version if isinstance(version, str) else ""
    if isinstance(frappe.__version__, str) and frappe.__version__:
        app_versions.setdefault("frappe", frappe.__version__)
    return TargetEnvironment(
        app_versions,
        capabilities={"server_script_enabled": bool(frappe.get_common_site_config().get("server_script_enabled"))},
    )
