"""Phase 5 dry-run and safe-apply endpoints for reviewed package changes."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import frappe

from frappe_config_pack.api._uploaded_package import read_private_fpack
from frappe_config_pack.api.import_pack import _target_environment
from frappe_config_pack.core.exceptions import ConfigPackError
from frappe_config_pack.services.dependency_engine import DependencyEngine, FrappeDependencyTarget
from frappe_config_pack.services.deployment import DeploymentService, FrappeResourceExecutor
from frappe_config_pack.services.installations import FrappeInstallationRepository
from frappe_config_pack.services.preflight import PackagePreflightService, PreflightStatus
from frappe_config_pack.services.reader import PackageReader
from frappe_config_pack.services.snapshot import SnapshotService
from frappe_config_pack.services.target_reader import FrappeTargetReader


@frappe.whitelist()
def dry_run_uploaded_package(file_name: str, selections: str | Mapping[str, str] | None = None) -> dict[str, Any]:
    """Build an action plan only; no target records are changed."""

    frappe.only_for("System Manager")
    package, response = _validated_package(file_name)
    if package is None:
        return response
    dependencies = DependencyEngine()
    dependency_target = FrappeDependencyTarget()

    def dependency_checker(payload: Mapping[str, Any]) -> tuple[str, ...]:
        return dependencies.missing_for_payload(payload, package.resources, dependency_target)

    plan = DeploymentService().dry_run(
        package.resources,
        FrappeTargetReader(),
        _parse_string_mapping(selections),
        dependency_checker=dependency_checker,
    )
    response["plan"] = plan.as_dict()
    return response


@frappe.whitelist()
def apply_uploaded_package(
    file_name: str,
    selections: str | Mapping[str, str],
    expected_target_checksums: str | Mapping[str, str | None],
) -> dict[str, Any]:
    """Apply a reviewed Create/Safe Update/Skip plan with a guarded savepoint."""

    frappe.only_for("System Manager")
    package, response = _validated_package(file_name)
    if package is None:
        return response
    selections_mapping = _parse_string_mapping(selections)
    expected_checksums = _parse_checksum_mapping(expected_target_checksums)
    deployment = DeploymentService()
    target_reader = FrappeTargetReader()
    dependencies = DependencyEngine()
    dependency_target = FrappeDependencyTarget()

    def dependency_checker(payload: Mapping[str, Any]) -> tuple[str, ...]:
        return dependencies.missing_for_payload(payload, package.resources, dependency_target)

    plan = deployment.dry_run(
        package.resources, target_reader, selections_mapping, dependency_checker=dependency_checker
    )
    if not plan.ready:
        frappe.throw("Deployment is blocked until every issue is resolved.")
    snapshot = SnapshotService().capture(package.resources, plan, target_reader)
    repository = FrappeInstallationRepository()
    installation = repository.create_installation(package, plan, snapshot, _target_environment())
    savepoint = _SavepointGuard(frappe.db, f"config_pack_apply_{frappe.generate_hash(length=12)}")
    savepoint.begin()
    try:
        result = deployment.apply(
            package.resources,
            FrappeTargetReader(),
            FrappeResourceExecutor(),
            selections_mapping,
            expected_checksums,
            dependency_checker=dependency_checker,
        )
    except ConfigPackError as error:
        savepoint.rollback()
        repository.mark_failed(installation, error)
        frappe.throw(str(error))
    except Exception as error:
        savepoint.rollback()
        repository.mark_failed(installation, error)
        raise
    savepoint.release()
    repository.mark_installed(installation, result)
    response["result"] = result.as_dict()
    response["installation"] = {"name": installation.name, "snapshot": installation.snapshot, "status": installation.status}
    return response


class _SavepointGuard:
    """Keep request transactions usable when Frappe metadata performs DDL.

    Saving metadata such as a Custom Field can issue MariaDB DDL. MariaDB
    implicitly commits DDL and discards every savepoint, so releasing that
    savepoint afterward must not turn an already-completed Safe Update into a
    user-facing failure. Other database errors still propagate normally.
    """

    def __init__(self, database: Any, name: str) -> None:
        self.database = database
        self.name = name
        self.active = False

    def begin(self) -> None:
        self.database.savepoint(self.name)
        self.active = True

    def rollback(self) -> None:
        if not self.active:
            return
        try:
            self.database.rollback(save_point=self.name)
        except Exception as error:
            if not _is_missing_savepoint(error):
                raise
        finally:
            self.active = False

    def release(self) -> None:
        if not self.active:
            return
        try:
            self.database.release_savepoint(self.name)
        except Exception as error:
            if not _is_missing_savepoint(error):
                raise
        finally:
            self.active = False


def _is_missing_savepoint(error: Exception) -> bool:
    """Return whether MariaDB discarded a savepoint after an implicit DDL commit."""

    error_code = error.args[0] if error.args else None
    return error_code == 1305 and "SAVEPOINT" in str(error).upper()


def _validated_package(file_name: str) -> tuple[Any | None, dict[str, Any]]:
    file_doc, content = read_private_fpack(file_name)
    preflight = PackagePreflightService().inspect(content, _target_environment(), FrappeDependencyTarget())
    response: dict[str, Any] = {
        "file_name": file_doc.name,
        "file_url": file_doc.file_url,
        "preflight": preflight.as_dict(),
        "plan": None,
        "result": None,
    }
    if preflight.status is PreflightStatus.INCOMPATIBLE:
        return None, response
    return PackageReader().read(content), response


def _parse_string_mapping(value: str | Mapping[str, str] | None) -> dict[str, str]:
    mapping = _parse_mapping(value)
    if any(not isinstance(key, str) or not isinstance(item, str) for key, item in mapping.items()):
        frappe.throw("Deployment selections must be a JSON object of string values.")
    return dict(mapping)


def _parse_checksum_mapping(value: str | Mapping[str, str | None]) -> dict[str, str | None]:
    mapping = _parse_mapping(value)
    if any(not isinstance(key, str) or (item is not None and not isinstance(item, str)) for key, item in mapping.items()):
        frappe.throw("Expected target checksums must be a JSON object of string or null values.")
    return dict(mapping)


def _parse_mapping(value: str | Mapping[str, Any] | None) -> Mapping[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            frappe.throw("Deployment request data must be valid JSON.")
            raise error
    if not isinstance(value, Mapping):
        frappe.throw("Deployment request data must be a JSON object.")
    return value
