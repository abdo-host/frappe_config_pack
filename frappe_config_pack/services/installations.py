"""Frappe persistence adapter for immutable installation history and restore points."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from frappe_config_pack.core.checksums import checksum, resource_checksum
from frappe_config_pack.core.exceptions import SnapshotError
from frappe_config_pack.core.serializer import stable_json_dumps
from frappe_config_pack.services.deployment import ApplyResult, DeploymentAction, DeploymentPlan
from frappe_config_pack.services.preflight import TargetEnvironment
from frappe_config_pack.services.snapshot import RollbackResult, Snapshot, SnapshotItem, resource_key


class FrappeInstallationRepository:
    """Store release history separately from deployment and rollback business rules."""

    def create_installation(
        self,
        package: Any,
        plan: DeploymentPlan,
        snapshot: Snapshot,
        environment: TargetEnvironment,
    ) -> Any:
        """Persist an Installing record and its Ready restore point before mutation begins."""

        import frappe

        payloads = {
            resource_key(payload["resource_type"], payload["identity"]): payload
            for payload in package.resources
        }
        installation = frappe.get_doc(
            {
                "doctype": "Config Pack Installation",
                "package_name": package.manifest["name"],
                "package_slug": package.manifest["slug"],
                "package_version": package.manifest["version"],
                "package_checksum": package.package_checksum,
                "package_format_version": package.manifest["format_version"],
                "source_author": package.manifest["author"],
                "status": "Installing",
                "installed_by": frappe.session.user,
                "frappe_version": environment.version_for("frappe") or "",
                "erpnext_version": environment.version_for("erpnext") or "",
                "preflight_completed": 1,
                "dry_run_completed": 1,
                "items": [self._installation_item(planned, payloads) for planned in plan.resources],
            }
        ).insert()
        snapshot_doc = frappe.get_doc(
            {
                "doctype": "Config Pack Snapshot",
                "snapshot_id": f"FCP-SNAP-{frappe.generate_hash(length=12)}",
                "installation": installation.name,
                "created_on": frappe.utils.now_datetime(),
                "created_by": frappe.session.user,
                "resource_count": len(snapshot.items),
                "status": "Ready",
                "checksum": snapshot.checksum,
                "items": [self._snapshot_item(item) for item in snapshot.items],
            }
        ).insert()
        installation.snapshot = snapshot_doc.name
        installation.save()
        return installation

    def mark_installed(self, installation: Any, result: ApplyResult) -> Any:
        """Record each reviewed action and only report Installed after all actions completed."""

        import frappe

        items = {
            resource_key(item.resource_type, item.resource_identity): item
            for item in installation.items
        }
        created = updated = skipped = 0
        for outcome in result.resources:
            item = items[resource_key(outcome.resource_type, outcome.identity)]
            item.status = outcome.status
            if outcome.status == "Skipped":
                skipped += 1
            elif outcome.action is DeploymentAction.CREATE:
                created += 1
            elif outcome.action is DeploymentAction.SAFE_UPDATE:
                updated += 1
        installation.status = "Installed"
        installation.installed_on = frappe.utils.now_datetime()
        installation.created_count = created
        installation.updated_count = updated
        installation.skipped_count = skipped
        installation.conflict_count = 0
        installation.failed_count = 0
        installation.save()
        return installation

    def mark_failed(self, installation: Any, error: Exception) -> Any:
        """Keep failed attempts visible without claiming an installation succeeded."""

        installation.status = "Failed"
        installation.failed_count = 1
        installation.notes = str(error)
        installation.save()
        return installation

    def get_installation(self, name: str) -> Any:
        import frappe

        installation = frappe.get_doc("Config Pack Installation", name)
        installation.check_permission("read")
        return installation

    def list_installations(self, *, start: int = 0, page_length: int = 20) -> dict[str, Any]:
        import frappe

        if start < 0 or not 1 <= page_length <= 100:
            frappe.throw("Pagination values are invalid.")
        rows = frappe.get_all(
            "Config Pack Installation",
            fields=["name", "package_name", "package_version", "status", "installed_by", "installed_on", "snapshot"],
            order_by="creation desc",
            limit_start=start,
            limit_page_length=page_length + 1,
        )
        return {
            "items": rows[:page_length],
            "start": start,
            "page_length": page_length,
            "has_more": len(rows) > page_length,
        }

    def read_snapshot(self, installation: Any) -> Snapshot:
        import frappe

        if not installation.snapshot:
            raise SnapshotError("This installation has no restore point.")
        snapshot_doc = frappe.get_doc("Config Pack Snapshot", installation.snapshot)
        snapshot_doc.check_permission("read")
        items = tuple(
            sorted(
                (self._read_snapshot_item(item) for item in snapshot_doc.items),
                key=lambda item: (item.resource_type, item.identity),
            )
        )
        calculated_checksum = checksum([item.as_dict() for item in items])
        if calculated_checksum != snapshot_doc.checksum:
            raise SnapshotError("The stored restore point failed its checksum validation.")
        return Snapshot(items, snapshot_doc.checksum)

    def installed_checksums(self, installation: Any) -> dict[str, str]:
        checksums: dict[str, str] = {}
        for item in installation.items:
            if item.status != "Applied" or not item.source_checksum:
                continue
            checksums[resource_key(item.resource_type, item.resource_identity)] = item.source_checksum
        return checksums

    def mark_rollback_started(self, installation: Any) -> Any:
        import frappe

        snapshot_doc = frappe.get_doc("Config Pack Snapshot", installation.snapshot)
        snapshot_doc.status = "Restoring"
        snapshot_doc.save()
        return snapshot_doc

    def mark_rollback_complete(self, installation: Any, result: RollbackResult) -> Any:
        import frappe

        snapshot_doc = frappe.get_doc("Config Pack Snapshot", installation.snapshot)
        partial = result.summary["Skipped"] > 0
        snapshot_doc.status = "Partially Restored" if partial else "Restored"
        snapshot_doc.save()
        installation.status = "Partially Rolled Back" if partial else "Rolled Back"
        if partial:
            installation.notes = f"Rollback skipped {result.summary['Skipped']} resource(s) modified after installation."
        installation.save()
        return installation

    def mark_rollback_failed(self, installation: Any, error: Exception) -> None:
        import frappe

        snapshot_doc = frappe.get_doc("Config Pack Snapshot", installation.snapshot)
        snapshot_doc.status = "Failed"
        snapshot_doc.save()
        installation.notes = str(error)
        installation.save()

    @staticmethod
    def _installation_item(planned: Any, payloads: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        key = resource_key(planned.resource_type, planned.identity)
        payload = payloads[key]
        action = planned.action
        action_label = {
            DeploymentAction.CREATE: "Create",
            DeploymentAction.SAFE_UPDATE: "Update",
            DeploymentAction.SKIP: "Skip",
        }.get(action, "")
        return {
            "resource_type": planned.resource_type,
            "resource_identity": planned.identity,
            "change_type": planned.state.value,
            "selected_action": action_label,
            "source_checksum": resource_checksum(payload),
            "target_checksum": planned.target_checksum or "",
            "status": "Pending",
        }

    @staticmethod
    def _snapshot_item(item: SnapshotItem) -> dict[str, Any]:
        return {
            "resource_type": item.resource_type,
            "resource_identity": item.identity,
            "existed_before": int(item.existed_before),
            "serialized_state": stable_json_dumps(item.serialized_state) if item.serialized_state else "",
            "checksum": item.checksum or "",
        }

    @staticmethod
    def _read_snapshot_item(item: Any) -> SnapshotItem:
        serialized_state = None
        if item.serialized_state:
            try:
                serialized_state = json.loads(item.serialized_state)
            except json.JSONDecodeError as error:
                raise SnapshotError(f"Restore point for {item.resource_identity!r} contains invalid JSON.") from error
            if not isinstance(serialized_state, Mapping):
                raise SnapshotError(f"Restore point for {item.resource_identity!r} is not a resource object.")
        return SnapshotItem(
            item.resource_type,
            item.resource_identity,
            bool(item.existed_before),
            serialized_state,
            item.checksum or None,
        )
