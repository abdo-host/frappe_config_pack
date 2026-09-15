"""Phase 2 orchestration: selected source resources to a private .fpack file."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from frappe_config_pack import __version__
from frappe_config_pack.core.exceptions import ConfigPackError
from frappe_config_pack.core.registry import ResourceRegistry, create_default_registry
from frappe_config_pack.services.builder import PackageBuilder, ResourceInput
from frappe_config_pack.services.dependency_engine import (
    DependencyEngine,
    FrappeDependencyTarget,
    resource_key,
)


@dataclass(frozen=True)
class ConfigPackSelection:
    resource_type: str
    resource_name: str
    resource_identity: str


class ConfigPackBuildService:
    """Build selected source documents through the existing Phase 1 engine."""

    def __init__(self, registry: ResourceRegistry | None = None) -> None:
        self.registry = registry or create_default_registry()

    def build_from_selections(
        self,
        package: Mapping[str, Any],
        selections: Iterable[ConfigPackSelection],
        document_loader: Callable[[str, str], Mapping[str, Any]],
    ):
        selected = list(selections)
        if not selected:
            raise ConfigPackError("Select at least one resource before building a package.")
        inputs = [
            ResourceInput(item.resource_type, document_loader(item.resource_type, item.resource_name))
            for item in selected
        ]
        counts = dict(sorted(Counter(item.resource_type for item in selected).items()))
        manifest = _manifest_from_package(package, counts)
        return PackageBuilder(self.registry).build(manifest, inputs)

    def build_and_store(self, config_pack: Any) -> dict[str, Any]:
        """Build a private Frappe File and update only the source Config Pack record."""

        import frappe

        selections = [
            ConfigPackSelection(row.resource_type, row.resource_name, row.resource_identity)
            for row in config_pack.resources
            if row.selected
        ]
        result = self.build_from_selections(
            config_pack.as_dict(),
            selections,
            lambda resource_type, name: frappe.get_doc(resource_type, name).as_dict(),
        )
        file_doc = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": _package_filename(config_pack.slug, config_pack.version),
                "content": result.archive,
                "is_private": 1,
                "attached_to_doctype": "Config Pack",
                "attached_to_name": config_pack.name,
            }
        ).insert(ignore_permissions=True)
        checksums = result.resource_checksums
        for row in config_pack.resources:
            key = f"{row.resource_type}:{row.resource_identity}"
            if row.selected and key in checksums:
                row.checksum = checksums[key]
        config_pack.package_file = file_doc.name
        config_pack.package_checksum = result.package_checksum
        config_pack.resource_count = len(selections)
        config_pack.last_built_on = frappe.utils.now_datetime()
        config_pack.status = "Built"
        config_pack.save()
        return {
            "file_name": file_doc.file_name,
            "file_url": file_doc.file_url,
            "package_checksum": result.package_checksum,
            "resource_count": len(selections),
        }

    def scan_dependencies(self, config_pack: Any, *, add_missing: bool = False) -> dict[str, Any]:
        """Inspect selected resources and optionally add only serializable declared dependencies."""

        import frappe

        selected = [row for row in config_pack.resources if row.selected]
        payloads = [
            self.registry.get_handler(row.resource_type).serialize(frappe.get_doc(row.resource_type, row.resource_name).as_dict())
            for row in selected
        ]
        report = DependencyEngine(self.registry).report_for_builder(payloads, FrappeDependencyTarget(self.registry))
        added: list[str] = []
        unresolved: list[str] = []
        if add_missing:
            existing = {resource_key(row.resource_type, row.resource_identity) for row in config_pack.resources}
            for dependency in report.missing:
                if dependency.kind.value != "Resource" or dependency.key in existing:
                    continue
                try:
                    document = frappe.get_doc(dependency.resource_type, dependency.identity).as_dict()
                    payload = self.registry.get_handler(dependency.resource_type).serialize(document)
                except Exception:
                    unresolved.append(dependency.label)
                    continue
                config_pack.append(
                    "resources",
                    {
                        "resource_type": dependency.resource_type,
                        "resource_identity": payload["identity"],
                        "resource_name": document["name"],
                        "reference_doctype": document.get("dt") or document.get("doc_type") or document.get("document_type"),
                        "selected": 1,
                        "is_dependency": 1,
                        "dependency_reason": dependency.reason,
                        "status": "Selected",
                    },
                )
                existing.add(dependency.key)
                added.append(dependency.label)
            if added:
                config_pack.status = "Draft"
                config_pack.save()
        return {**report.as_dict(), "added": added, "unresolved": unresolved}


def _manifest_from_package(package: Mapping[str, Any], counts: Mapping[str, int]) -> dict[str, Any]:
    return {
        "format_version": "1.0",
        "name": package["package_name"],
        "slug": package["slug"],
        "version": package["version"],
        "description": package.get("description") or "",
        "author": package.get("author") or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "generator": {"app": "frappe_config_pack", "version": __version__},
        "compatibility": {
            "frappe": package.get("frappe_version_constraint") or ">=15,<17",
            "erpnext": package.get("erpnext_version_constraint") or None,
        },
        "required_apps": _required_apps(package.get("required_apps")),
        "resources": dict(counts),
        "total_resources": sum(counts.values()),
    }


def _required_apps(value: Any) -> list[dict[str, str]]:
    if not value:
        return [{"app": "frappe", "version": ">=15,<17"}]
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise ConfigPackError("Required Apps must be valid JSON.") from error
    if not isinstance(value, list):
        raise ConfigPackError("Required Apps must be a JSON list.")
    return value


def _package_filename(slug: str, version: str) -> str:
    return f"{slug}-{version}.fpack"
