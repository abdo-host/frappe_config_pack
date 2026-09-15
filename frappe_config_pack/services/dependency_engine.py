"""Deterministic dependency analysis shared by builder, preflight, diff, and deployment."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from frappe_config_pack.core.dependencies import Dependency, DependencyKind
from frappe_config_pack.core.registry import ResourceRegistry, create_default_registry


def resource_key(resource_type: str, identity: str) -> str:
    return f"{resource_type}:{identity}"


class DependencyTarget(Protocol):
    def resource_exists(self, resource_type: str, identity: str) -> bool: ...

    def doctype_exists(self, doctype: str) -> bool: ...


@dataclass(frozen=True)
class DependencyReport:
    dependencies: tuple[Dependency, ...]
    missing: tuple[Dependency, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "dependencies": [_dependency_dict(item) for item in self.dependencies],
            "missing": [_dependency_dict(item) for item in self.missing],
        }


class DependencyEngine:
    """Resolve only declared handler dependencies; it never parses scripts or arbitrary code."""

    def __init__(self, registry: ResourceRegistry | None = None) -> None:
        self.registry = registry or create_default_registry()

    def dependencies_for(self, payload: Mapping[str, Any]) -> tuple[Dependency, ...]:
        handler = self.registry.get_handler(payload["resource_type"])
        return tuple(sorted(set(handler.get_dependencies(payload))))

    def report_for_target(
        self,
        payloads: Iterable[Mapping[str, Any]],
        target: DependencyTarget,
    ) -> DependencyReport:
        resources = [dict(payload) for payload in payloads]
        package_keys = {resource_key(payload["resource_type"], payload["identity"]) for payload in resources}
        dependencies = tuple(sorted({item for payload in resources for item in self.dependencies_for(payload)}))
        missing = tuple(
            dependency
            for dependency in dependencies
            if not self._is_satisfied(dependency, package_keys, target)
        )
        return DependencyReport(dependencies, missing)

    def report_for_builder(
        self,
        payloads: Iterable[Mapping[str, Any]],
        target: DependencyTarget,
    ) -> DependencyReport:
        """Report packageable dependencies omitted from the release scope and invalid DocType references."""

        resources = [dict(payload) for payload in payloads]
        package_keys = {resource_key(payload["resource_type"], payload["identity"]) for payload in resources}
        dependencies = tuple(sorted({item for payload in resources for item in self.dependencies_for(payload)}))
        missing = tuple(
            dependency
            for dependency in dependencies
            if (
                dependency.kind is DependencyKind.RESOURCE
                and dependency.key not in package_keys
            )
            or (
                dependency.kind is DependencyKind.DOCTYPE
                and not target.doctype_exists(dependency.identity)
            )
        )
        return DependencyReport(dependencies, missing)

    def missing_for_payload(
        self,
        payload: Mapping[str, Any],
        package_resources: Iterable[Mapping[str, Any]],
        target: DependencyTarget,
    ) -> tuple[str, ...]:
        package_keys = {
            resource_key(resource["resource_type"], resource["identity"])
            for resource in package_resources
        }
        return tuple(
            dependency.label
            for dependency in self.dependencies_for(payload)
            if not self._is_satisfied(dependency, package_keys, target)
        )

    def ordered_payloads(self, payloads: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        """Topologically order packageable dependencies before their consumers."""

        by_key = {resource_key(payload["resource_type"], payload["identity"]): payload for payload in payloads}
        dependencies = {
            key: {
                dependency.key
                for dependency in self.dependencies_for(payload)
                if dependency.kind is DependencyKind.RESOURCE and dependency.key in by_key
            }
            for key, payload in by_key.items()
        }
        ordered: list[Mapping[str, Any]] = []
        remaining = set(by_key)
        while remaining:
            ready = sorted(key for key in remaining if not dependencies[key].intersection(remaining))
            if not ready:
                # Cycles are not expected in the initial rule set; keep deterministic behavior if one is introduced.
                ready = [min(remaining)]
            for key in ready:
                ordered.append(by_key[key])
                remaining.remove(key)
        return ordered

    @staticmethod
    def _is_satisfied(dependency: Dependency, package_keys: set[str], target: DependencyTarget) -> bool:
        if dependency.kind is DependencyKind.RESOURCE:
            return dependency.key in package_keys or target.resource_exists(dependency.resource_type, dependency.identity)
        return target.doctype_exists(dependency.identity)


class FrappeDependencyTarget:
    """Read-only Frappe adapter used by import preflight, diff, and source scans."""

    def __init__(self, registry: ResourceRegistry | None = None) -> None:
        self.registry = registry or create_default_registry()

    def resource_exists(self, resource_type: str, identity: str) -> bool:
        return self.registry.get_handler(resource_type).get_target(identity) is not None

    def doctype_exists(self, doctype: str) -> bool:
        import frappe

        return bool(frappe.db.exists("DocType", doctype))


def _dependency_dict(dependency: Dependency) -> dict[str, str]:
    return {
        "kind": dependency.kind.value,
        "resource_type": dependency.resource_type,
        "identity": dependency.identity,
        "reason": dependency.reason,
        "label": dependency.label,
    }
