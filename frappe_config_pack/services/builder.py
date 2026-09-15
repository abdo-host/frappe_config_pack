"""Programmatic construction of a deterministic .fpack archive."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from frappe_config_pack.core.registry import ResourceRegistry, create_default_registry
from frappe_config_pack.utils.archive import BuildResult, SafeArchiveBuilder


@dataclass(frozen=True)
class ResourceInput:
    """One source document and the handler responsible for serializing it."""

    resource_type: str
    document: Mapping[str, Any]


class PackageBuilder:
    """Serialize selected resources through registered handlers and archive them."""

    def __init__(self, registry: ResourceRegistry | None = None) -> None:
        self.registry = registry or create_default_registry()

    def build(self, manifest: Mapping[str, Any], resources: Iterable[ResourceInput]) -> BuildResult:
        payloads = [
            self.registry.get_handler(item.resource_type).serialize(item.document)
            for item in resources
        ]
        return SafeArchiveBuilder(self.registry).build(manifest, payloads)
