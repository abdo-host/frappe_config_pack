"""Thin Phase 6 APIs for deployment history and explicitly approved rollback."""

from __future__ import annotations

from typing import Any

import frappe

from frappe_config_pack.core.exceptions import ConfigPackError
from frappe_config_pack.services.drift import DriftService
from frappe_config_pack.services.installations import FrappeInstallationRepository
from frappe_config_pack.services.snapshot import FrappeRollbackExecutor, RollbackService
from frappe_config_pack.services.target_reader import FrappeTargetReader


@frappe.whitelist()
def list_installations(start: int | str = 0, page_length: int | str = 20) -> dict[str, Any]:
    """List installation history without reading or mutating target configuration."""

    frappe.only_for("System Manager")
    return FrappeInstallationRepository().list_installations(start=int(start), page_length=int(page_length))


@frappe.whitelist()
def get_installation(installation: str) -> dict[str, Any]:
    """Return one authorized installation and its linked restore point metadata."""

    frappe.only_for("System Manager")
    record = FrappeInstallationRepository().get_installation(installation)
    return record.as_dict()


@frappe.whitelist()
def get_rollback_preview(installation: str) -> dict[str, Any]:
    """Show local-change warnings before any restore or delete action is attempted."""

    frappe.only_for("System Manager")
    repository = FrappeInstallationRepository()
    record = repository.get_installation(installation)
    snapshot = repository.read_snapshot(record)
    plan = RollbackService().plan(snapshot, repository.installed_checksums(record), FrappeTargetReader())
    return plan.as_dict()


@frappe.whitelist()
def check_drift(installation: str) -> dict[str, Any]:
    """Compare an installed release with its current target state without changing either."""

    frappe.only_for("System Manager")
    repository = FrappeInstallationRepository()
    record = repository.get_installation(installation)
    report = DriftService().check(repository.installed_checksums(record), FrappeTargetReader())
    return {
        "installation": record.name,
        "package_name": record.package_name,
        "package_version": record.package_version,
        "report": report.as_dict(),
    }


@frappe.whitelist()
def rollback_installation(installation: str, force: int | str | bool = False) -> dict[str, Any]:
    """Restore a release point, skipping later local changes unless force is explicit."""

    frappe.only_for("System Manager")
    repository = FrappeInstallationRepository()
    record = repository.get_installation(installation)
    if record.status not in {"Installed", "Partially Rolled Back"}:
        frappe.throw("Only installed Config Packs can be rolled back.")
    try:
        snapshot = repository.read_snapshot(record)
        plan = RollbackService().plan(snapshot, repository.installed_checksums(record), FrappeTargetReader())
        repository.mark_rollback_started(record)
        result = RollbackService().execute(plan, FrappeRollbackExecutor(), force=bool(frappe.utils.cint(force)))
    except ConfigPackError as error:
        repository.mark_rollback_failed(record, error)
        frappe.throw(str(error))
    except Exception as error:
        repository.mark_rollback_failed(record, error)
        raise
    repository.mark_rollback_complete(record, result)
    return {"installation": record.name, "snapshot": record.snapshot, "result": result.as_dict()}
