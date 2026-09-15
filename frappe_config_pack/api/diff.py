"""Read-only target comparison endpoints for imported Config Packs."""

from __future__ import annotations

from typing import Any

import frappe

from frappe_config_pack.api._uploaded_package import read_private_fpack
from frappe_config_pack.api.import_pack import _target_environment
from frappe_config_pack.services.dependency_engine import DependencyEngine, FrappeDependencyTarget
from frappe_config_pack.services.diff_engine import DiffEngine
from frappe_config_pack.services.preflight import PackagePreflightService, PreflightStatus
from frappe_config_pack.services.reader import PackageReader
from frappe_config_pack.services.target_reader import FrappeTargetReader


@frappe.whitelist()
def compare_uploaded_package(file_name: str) -> dict[str, Any]:
    """Compare a valid package to target records without changing any target record."""

    file_doc, content = read_private_fpack(file_name)
    dependency_target = FrappeDependencyTarget()
    preflight = PackagePreflightService().inspect(content, _target_environment(), dependency_target)
    response: dict[str, Any] = {
        "file_name": file_doc.name,
        "file_url": file_doc.file_url,
        "preflight": preflight.as_dict(),
        "diff": None,
    }
    if preflight.status is PreflightStatus.INCOMPATIBLE:
        return response
    package = PackageReader().read(content)
    dependencies = DependencyEngine()
    response["diff"] = DiffEngine().compare(
        package.resources,
        FrappeTargetReader(),
        dependency_checker=lambda payload: dependencies.missing_for_payload(payload, package.resources, dependency_target),
    ).as_dict()
    return response
