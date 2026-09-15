"""Phase 5 dry-run planning and safe application of reviewed package changes."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from frappe_config_pack.core.checksums import resource_checksum
from frappe_config_pack.core.exceptions import (
    DeploymentBlockedError,
    DuplicateResourceError,
    StalePreviewError,
)
from frappe_config_pack.core.registry import ResourceRegistry, create_default_registry
from frappe_config_pack.services.dependency_engine import DependencyEngine
from frappe_config_pack.services.diff_engine import (
    DependencyChecker,
    DiffEngine,
    ResourceDiff,
    ResourceState,
    TargetLoader,
)


class DeploymentAction(str, Enum):
    CREATE = "Create"
    SAFE_UPDATE = "Safe Update"
    SKIP = "Skip"


@dataclass(frozen=True)
class PlanBlocker:
    resource_type: str
    identity: str
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "resource_type": self.resource_type,
            "identity": self.identity,
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class PlannedResource:
    resource_type: str
    identity: str
    state: ResourceState
    action: DeploymentAction | None
    target_checksum: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type,
            "identity": self.identity,
            "state": self.state.value,
            "action": self.action.value if self.action else None,
            "target_checksum": self.target_checksum,
        }


@dataclass(frozen=True)
class DeploymentPlan:
    resources: tuple[PlannedResource, ...]
    blockers: tuple[PlanBlocker, ...]

    @property
    def ready(self) -> bool:
        return not self.blockers

    @property
    def summary(self) -> dict[str, int]:
        counts = Counter(resource.action.value if resource.action else "Blocked" for resource in self.resources)
        return {action.value: counts.get(action.value, 0) for action in DeploymentAction} | {
            "Blocked": counts.get("Blocked", 0)
        }

    @property
    def expected_target_checksums(self) -> dict[str, str | None]:
        return {_resource_key(item.resource_type, item.identity): item.target_checksum for item in self.resources}

    def as_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "summary": self.summary,
            "resources": [resource.as_dict() for resource in self.resources],
            "blockers": [blocker.as_dict() for blocker in self.blockers],
            "expected_target_checksums": self.expected_target_checksums,
        }


@dataclass(frozen=True)
class ResourceApplyResult:
    resource_type: str
    identity: str
    action: DeploymentAction
    status: str

    def as_dict(self) -> dict[str, str]:
        return {
            "resource_type": self.resource_type,
            "identity": self.identity,
            "action": self.action.value,
            "status": self.status,
        }


@dataclass(frozen=True)
class ApplyResult:
    resources: tuple[ResourceApplyResult, ...]

    @property
    def summary(self) -> dict[str, int]:
        counts = Counter(result.status for result in self.resources)
        return {"Applied": counts.get("Applied", 0), "Skipped": counts.get("Skipped", 0)}

    def as_dict(self) -> dict[str, Any]:
        return {"summary": self.summary, "resources": [resource.as_dict() for resource in self.resources]}


class ResourceExecutor(Protocol):
    def execute(self, payload: Mapping[str, Any], action: DeploymentAction) -> None: ...

    def refresh_caches(self, payloads: Iterable[Mapping[str, Any]]) -> None: ...


class FrappeResourceExecutor:
    """Frappe mutation adapter; all selection and validation stays in DeploymentService."""

    def __init__(self, registry: ResourceRegistry | None = None) -> None:
        self.registry = registry or create_default_registry()

    def execute(self, payload: Mapping[str, Any], action: DeploymentAction) -> None:
        self.registry.get_handler(payload["resource_type"]).apply(payload, action.value)

    def refresh_caches(self, payloads: Iterable[Mapping[str, Any]]) -> None:
        import frappe

        doctypes: set[str] = set()
        for payload in payloads:
            data = payload["data"]
            doctype = data.get("dt") or data.get("doc_type") or data.get("document_type")
            doctypes.add(doctype or payload["resource_type"])
        for doctype in sorted(doctypes):
            frappe.clear_cache(doctype=doctype)


class DeploymentService:
    """Build a safe plan first, then apply only explicitly approved actions."""

    def __init__(self, registry: ResourceRegistry | None = None) -> None:
        self.registry = registry or create_default_registry()
        self.diff_engine = DiffEngine(self.registry)

    def dry_run(
        self,
        package_resources: Iterable[Mapping[str, Any]],
        target_loader: TargetLoader,
        selections: Mapping[str, str] | None = None,
        *,
        baseline_checksums: Mapping[str, str] | None = None,
        dependency_checker: DependencyChecker | None = None,
    ) -> DeploymentPlan:
        """Validate and plan deployment without sending any mutation to an executor."""

        payloads = [dict(payload) for payload in package_resources]
        _validate_unique_resources(payloads)
        diff = self.diff_engine.compare(
            payloads,
            target_loader,
            baseline_checksums=baseline_checksums,
            dependency_checker=dependency_checker,
        )
        return self._plan(diff.resources, selections or {})

    def apply(
        self,
        package_resources: Iterable[Mapping[str, Any]],
        target_loader: TargetLoader,
        executor: ResourceExecutor,
        selections: Mapping[str, str],
        expected_target_checksums: Mapping[str, str | None],
        *,
        baseline_checksums: Mapping[str, str] | None = None,
        dependency_checker: DependencyChecker | None = None,
    ) -> ApplyResult:
        """Re-plan, recheck each target, then execute only the reviewed safe actions."""

        payloads = [dict(payload) for payload in package_resources]
        plan = self.dry_run(
            payloads,
            target_loader,
            selections,
            baseline_checksums=baseline_checksums,
            dependency_checker=dependency_checker,
        )
        if not plan.ready:
            raise DeploymentBlockedError("Deployment is blocked until every issue is resolved.")
        results: list[ResourceApplyResult] = []
        changed: list[Mapping[str, Any]] = []
        planned_by_key = {_resource_key(item.resource_type, item.identity): item for item in plan.resources}
        ordered_payloads = DependencyEngine(self.registry).ordered_payloads(payloads)
        for payload in ordered_payloads:
            planned = planned_by_key[_resource_key(payload["resource_type"], payload["identity"])]
            if planned.action is DeploymentAction.SKIP:
                results.append(
                    ResourceApplyResult(planned.resource_type, planned.identity, planned.action, "Skipped")
                )
                continue
            key = _resource_key(planned.resource_type, planned.identity)
            if key not in expected_target_checksums:
                raise StalePreviewError(f"Target checksum for {key!r} was not supplied by the reviewed dry run.")
            current = target_loader.load(planned.resource_type, planned.identity)
            actual_checksum = resource_checksum(current) if current is not None else None
            if actual_checksum != expected_target_checksums[key]:
                raise StalePreviewError(f"Target resource {key!r} changed since preview. Refresh the comparison.")
            executor.execute(payload, planned.action)
            changed.append(payload)
            results.append(ResourceApplyResult(planned.resource_type, planned.identity, planned.action, "Applied"))
        if changed:
            executor.refresh_caches(changed)
        return ApplyResult(tuple(results))

    @staticmethod
    def _plan(resources: Iterable[ResourceDiff], selections: Mapping[str, str]) -> DeploymentPlan:
        planned: list[PlannedResource] = []
        blockers: list[PlanBlocker] = []
        for resource in resources:
            key = _resource_key(resource.resource_type, resource.identity)
            action, blocker = _action_for(resource, selections.get(key))
            planned.append(
                PlannedResource(
                    resource.resource_type,
                    resource.identity,
                    resource.state,
                    action,
                    resource.target_checksum,
                )
            )
            if blocker:
                blockers.append(blocker)
        return DeploymentPlan(tuple(planned), tuple(blockers))


def _action_for(resource: ResourceDiff, selection: str | None) -> tuple[DeploymentAction | None, PlanBlocker | None]:
    key_args = (resource.resource_type, resource.identity)
    if resource.state is ResourceState.NEW:
        if selection in {None, DeploymentAction.CREATE.value}:
            return DeploymentAction.CREATE, None
        if selection == DeploymentAction.SKIP.value:
            return DeploymentAction.SKIP, None
    elif resource.state is ResourceState.UNCHANGED:
        if selection in {None, DeploymentAction.SKIP.value}:
            return DeploymentAction.SKIP, None
    elif resource.state is ResourceState.MODIFIED:
        if selection in {DeploymentAction.SAFE_UPDATE.value, DeploymentAction.SKIP.value}:
            return DeploymentAction(selection), None
        return None, PlanBlocker(*key_args, "explicit_action_required", "Choose Safe Update or Skip for this modified resource.")
    elif resource.state is ResourceState.CONFLICT:
        choices = {
            "Keep Target": DeploymentAction.SKIP,
            "Use Package": DeploymentAction.SAFE_UPDATE,
            "Skip": DeploymentAction.SKIP,
        }
        if selection in choices:
            return choices[selection], None
        return None, PlanBlocker(*key_args, "conflict_unresolved", "Choose a resolution for this conflict.")
    elif resource.state is ResourceState.MISSING_DEPENDENCY:
        return None, PlanBlocker(*key_args, "missing_dependency", "Required dependencies are unavailable.")
    return None, PlanBlocker(*key_args, "invalid_state", "Resource has an unsupported deployment state.")


def _validate_unique_resources(payloads: Iterable[Mapping[str, Any]]) -> None:
    keys = [_resource_key(payload["resource_type"], payload["identity"]) for payload in payloads]
    if len(keys) != len(set(keys)):
        raise DuplicateResourceError("Package contains duplicate resource identities.")


def _resource_key(resource_type: str, identity: str) -> str:
    return f"{resource_type}:{identity}"
