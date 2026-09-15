"""Deterministic, read-only comparison of package and target resources."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from frappe_config_pack.core.checksums import resource_checksum
from frappe_config_pack.core.registry import ResourceRegistry, create_default_registry


class ResourceState(str, Enum):
    NEW = "NEW"
    UNCHANGED = "UNCHANGED"
    MODIFIED = "MODIFIED"
    CONFLICT = "CONFLICT"
    MISSING_DEPENDENCY = "MISSING_DEPENDENCY"


class ConflictResolutionChoice(str, Enum):
    KEEP_TARGET = "Keep Target"
    USE_PACKAGE = "Use Package"
    SKIP = "Skip"


@dataclass(frozen=True)
class ConflictResolution:
    """An explicit, non-persistent choice for a conflicting resource."""

    resource_type: str
    identity: str
    choice: ConflictResolutionChoice | None = None

    @property
    def is_resolved(self) -> bool:
        return self.choice is not None


@dataclass(frozen=True)
class FieldDifference:
    field: str
    target_value: Any
    package_value: Any

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "target_value": self.target_value,
            "package_value": self.package_value,
        }


@dataclass(frozen=True)
class ResourceDiff:
    resource_type: str
    identity: str
    state: ResourceState
    package_checksum: str
    target_checksum: str | None
    field_differences: tuple[FieldDifference, ...]
    missing_dependencies: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type,
            "identity": self.identity,
            "state": self.state.value,
            "package_checksum": self.package_checksum,
            "target_checksum": self.target_checksum,
            "field_differences": [difference.as_dict() for difference in self.field_differences],
            "missing_dependencies": list(self.missing_dependencies),
            "resolution_options": [choice.value for choice in ConflictResolutionChoice]
            if self.state is ResourceState.CONFLICT
            else [],
        }


@dataclass(frozen=True)
class DiffResult:
    resources: tuple[ResourceDiff, ...]

    @property
    def summary(self) -> dict[str, int]:
        counts = Counter(resource.state.value for resource in self.resources)
        return {state.value: counts.get(state.value, 0) for state in ResourceState}

    @property
    def unresolved_conflicts(self) -> tuple[ConflictResolution, ...]:
        return tuple(
            ConflictResolution(resource.resource_type, resource.identity)
            for resource in self.resources
            if resource.state is ResourceState.CONFLICT
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "resources": [resource.as_dict() for resource in self.resources],
            "unresolved_conflicts": [
                {
                    "resource_type": conflict.resource_type,
                    "identity": conflict.identity,
                    "is_resolved": conflict.is_resolved,
                }
                for conflict in self.unresolved_conflicts
            ],
        }


class TargetLoader(Protocol):
    def load(self, resource_type: str, identity: str) -> dict[str, Any] | None: ...


DependencyChecker = Callable[[Mapping[str, Any]], Iterable[str]]


class DiffEngine:
    """Compare normalized payloads without applying or persisting any change."""

    def __init__(self, registry: ResourceRegistry | None = None) -> None:
        self.registry = registry or create_default_registry()

    def compare(
        self,
        package_resources: Iterable[Mapping[str, Any]],
        target_loader: TargetLoader,
        *,
        baseline_checksums: Mapping[str, str] | None = None,
        dependency_checker: DependencyChecker | None = None,
    ) -> DiffResult:
        """Return deterministic differences; callers cannot mutate through this method."""

        baselines = baseline_checksums or {}
        resources = [dict(resource) for resource in package_resources]
        for payload in resources:
            self.registry.get_handler(payload["resource_type"]).validate(payload)
        compared = [
            self._compare_resource(payload, target_loader, baselines, dependency_checker) for payload in resources
        ]
        return DiffResult(tuple(sorted(compared, key=lambda resource: (resource.resource_type, resource.identity))))

    def _compare_resource(
        self,
        payload: Mapping[str, Any],
        target_loader: TargetLoader,
        baseline_checksums: Mapping[str, str],
        dependency_checker: DependencyChecker | None,
    ) -> ResourceDiff:
        missing_dependencies = tuple(sorted(set(dependency_checker(payload)))) if dependency_checker else ()
        package_checksum = resource_checksum(payload)
        resource_type, identity = payload["resource_type"], payload["identity"]
        if missing_dependencies:
            return ResourceDiff(
                resource_type,
                identity,
                ResourceState.MISSING_DEPENDENCY,
                package_checksum,
                None,
                (),
                missing_dependencies,
            )

        target = target_loader.load(resource_type, identity)
        if target is None:
            return ResourceDiff(resource_type, identity, ResourceState.NEW, package_checksum, None, ())
        self.registry.get_handler(resource_type).validate(target)
        target_checksum = resource_checksum(target)
        if target_checksum == package_checksum:
            state = ResourceState.UNCHANGED
        elif baseline_checksums.get(_resource_key(payload)) not in {None, target_checksum}:
            state = ResourceState.CONFLICT
        else:
            state = ResourceState.MODIFIED
        return ResourceDiff(
            resource_type,
            identity,
            state,
            package_checksum,
            target_checksum,
            field_differences(payload["data"], target["data"]),
        )


_MISSING = object()


def field_differences(package_data: Mapping[str, Any], target_data: Mapping[str, Any]) -> tuple[FieldDifference, ...]:
    """Return stable field paths and values, without treating metadata as configuration."""

    return tuple(_field_differences(package_data, target_data))


def _field_differences(package_value: Any, target_value: Any, prefix: str = "") -> list[FieldDifference]:
    if isinstance(package_value, Mapping) and isinstance(target_value, Mapping):
        differences: list[FieldDifference] = []
        for key in sorted(set(package_value) | set(target_value)):
            path = f"{prefix}.{key}" if prefix else key
            differences.extend(_field_differences(package_value.get(key, _MISSING), target_value.get(key, _MISSING), path))
        return differences
    if package_value == target_value:
        return []
    return [
        FieldDifference(
            prefix,
            None if target_value is _MISSING else target_value,
            None if package_value is _MISSING else package_value,
        )
    ]


def _resource_key(payload: Mapping[str, Any]) -> str:
    return f"{payload['resource_type']}:{payload['identity']}"
