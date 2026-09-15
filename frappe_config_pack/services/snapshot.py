"""Restore-point capture and safe rollback planning for installed Config Packs."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from frappe_config_pack.core.checksums import checksum, resource_checksum
from frappe_config_pack.core.exceptions import RollbackError, SnapshotError
from frappe_config_pack.core.registry import ResourceRegistry, create_default_registry
from frappe_config_pack.services.deployment import DeploymentAction, DeploymentPlan
from frappe_config_pack.services.diff_engine import TargetLoader


def resource_key(resource_type: str, identity: str) -> str:
    """Return the stable key shared by deployments, snapshots, and installations."""

    return f"{resource_type}:{identity}"


@dataclass(frozen=True)
class SnapshotItem:
    """The pre-install state for one resource that a release will mutate."""

    resource_type: str
    identity: str
    existed_before: bool
    serialized_state: Mapping[str, Any] | None
    checksum: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type,
            "resource_identity": self.identity,
            "existed_before": self.existed_before,
            "serialized_state": dict(self.serialized_state) if self.serialized_state else None,
            "checksum": self.checksum,
        }


@dataclass(frozen=True)
class Snapshot:
    """A deterministic collection of all states needed to undo one installation."""

    items: tuple[SnapshotItem, ...]
    checksum: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "resource_count": len(self.items),
            "checksum": self.checksum,
            "items": [item.as_dict() for item in self.items],
        }


class SnapshotService:
    """Capture only resources whose reviewed deployment action can mutate a target."""

    def capture(
        self,
        package_resources: Iterable[Mapping[str, Any]],
        plan: DeploymentPlan,
        target_loader: TargetLoader,
    ) -> Snapshot:
        payloads = {
            resource_key(payload["resource_type"], payload["identity"]): dict(payload)
            for payload in package_resources
        }
        items: list[SnapshotItem] = []
        for planned in plan.resources:
            if planned.action not in {DeploymentAction.CREATE, DeploymentAction.SAFE_UPDATE}:
                continue
            key = resource_key(planned.resource_type, planned.identity)
            if key not in payloads:
                raise SnapshotError(f"Reviewed resource {key!r} is absent from the package.")
            current = target_loader.load(planned.resource_type, planned.identity)
            items.append(
                SnapshotItem(
                    planned.resource_type,
                    planned.identity,
                    current is not None,
                    dict(current) if current is not None else None,
                    resource_checksum(current) if current is not None else None,
                )
            )
        ordered_items = tuple(sorted(items, key=lambda item: (item.resource_type, item.identity)))
        return Snapshot(ordered_items, checksum([item.as_dict() for item in ordered_items]))


class RollbackAction(str, Enum):
    RESTORE = "Restore"
    DELETE = "Delete"
    SKIP = "Skip"


@dataclass(frozen=True)
class RollbackWarning:
    """A target no longer matches the exact state written by the installation."""

    resource_type: str
    identity: str
    expected_checksum: str
    current_checksum: str | None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "resource_type": self.resource_type,
            "resource_identity": self.identity,
            "expected_checksum": self.expected_checksum,
            "current_checksum": self.current_checksum,
        }


@dataclass(frozen=True)
class PlannedRollbackResource:
    snapshot_item: SnapshotItem
    action: RollbackAction
    warning: RollbackWarning | None = None


@dataclass(frozen=True)
class RollbackPlan:
    resources: tuple[PlannedRollbackResource, ...]

    @property
    def warnings(self) -> tuple[RollbackWarning, ...]:
        return tuple(resource.warning for resource in self.resources if resource.warning is not None)

    def as_dict(self) -> dict[str, Any]:
        return {
            "resources": [
                {
                    "resource_type": resource.snapshot_item.resource_type,
                    "resource_identity": resource.snapshot_item.identity,
                    "action": resource.action.value,
                    "has_local_change": resource.warning is not None,
                }
                for resource in self.resources
            ],
            "warnings": [warning.as_dict() for warning in self.warnings],
        }


@dataclass(frozen=True)
class RollbackResult:
    resources: tuple[PlannedRollbackResource, ...]
    forced: bool

    @property
    def summary(self) -> dict[str, int]:
        counts = Counter(resource.action.value for resource in self.resources)
        skipped = sum(1 for resource in self.resources if resource.warning is not None and not self.forced)
        return {
            "Restored": counts.get(RollbackAction.RESTORE.value, 0) - sum(
                1
                for resource in self.resources
                if resource.action is RollbackAction.RESTORE and resource.warning is not None and not self.forced
            ),
            "Deleted": counts.get(RollbackAction.DELETE.value, 0) - sum(
                1
                for resource in self.resources
                if resource.action is RollbackAction.DELETE and resource.warning is not None and not self.forced
            ),
            "Skipped": skipped,
        }

    def as_dict(self) -> dict[str, Any]:
        return {"summary": self.summary, "forced": self.forced}


class RollbackExecutor(Protocol):
    def restore(self, payload: Mapping[str, Any]) -> None: ...

    def delete(self, resource_type: str, identity: str) -> None: ...

    def refresh_caches(self, items: Iterable[SnapshotItem]) -> None: ...


class RollbackService:
    """Refuse to overwrite post-install local changes unless the caller explicitly forces it."""

    def plan(
        self,
        snapshot: Snapshot,
        installed_checksums: Mapping[str, str],
        target_loader: TargetLoader,
    ) -> RollbackPlan:
        resources: list[PlannedRollbackResource] = []
        for item in snapshot.items:
            key = resource_key(item.resource_type, item.identity)
            expected_checksum = installed_checksums.get(key)
            if not expected_checksum:
                raise RollbackError(f"Installation checksum for {key!r} is unavailable.")
            current = target_loader.load(item.resource_type, item.identity)
            current_checksum = resource_checksum(current) if current is not None else None
            warning = None
            if current_checksum != expected_checksum:
                warning = RollbackWarning(item.resource_type, item.identity, expected_checksum, current_checksum)
            action = RollbackAction.RESTORE if item.existed_before else RollbackAction.DELETE
            resources.append(PlannedRollbackResource(item, action, warning))
        return RollbackPlan(tuple(resources))

    def execute(self, plan: RollbackPlan, executor: RollbackExecutor, *, force: bool = False) -> RollbackResult:
        changed: list[SnapshotItem] = []
        for planned in plan.resources:
            if planned.warning is not None and not force:
                continue
            if planned.action is RollbackAction.RESTORE:
                if planned.snapshot_item.serialized_state is None:
                    raise RollbackError(
                        f"Restore point for {resource_key(planned.snapshot_item.resource_type, planned.snapshot_item.identity)!r} is missing its state."
                    )
                executor.restore(planned.snapshot_item.serialized_state)
            elif planned.action is RollbackAction.DELETE:
                executor.delete(planned.snapshot_item.resource_type, planned.snapshot_item.identity)
            else:
                raise RollbackError(f"Unsupported rollback action {planned.action.value!r}.")
            changed.append(planned.snapshot_item)
        if changed:
            executor.refresh_caches(changed)
        return RollbackResult(plan.resources, force)


class FrappeRollbackExecutor:
    """Frappe adapter that delegates resource restore/delete behavior to registered handlers."""

    def __init__(self, registry: ResourceRegistry | None = None) -> None:
        self.registry = registry or create_default_registry()

    def restore(self, payload: Mapping[str, Any]) -> None:
        self.registry.get_handler(payload["resource_type"]).rollback(payload)

    def delete(self, resource_type: str, identity: str) -> None:
        self.registry.get_handler(resource_type).delete_target(identity)

    def refresh_caches(self, items: Iterable[SnapshotItem]) -> None:
        import frappe

        doctypes: set[str] = set()
        for item in items:
            state = item.serialized_state or {}
            data = state.get("data", {}) if isinstance(state, Mapping) else {}
            doctype = data.get("dt") or data.get("doc_type") or data.get("document_type")
            doctypes.add(doctype or item.resource_type)
        for doctype in sorted(doctypes):
            frappe.clear_cache(doctype=doctype)
