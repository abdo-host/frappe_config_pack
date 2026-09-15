"""Read normalized target resources through registered handlers only."""

from __future__ import annotations

from typing import Any

from frappe_config_pack.core.registry import ResourceRegistry, create_default_registry


class FrappeTargetReader:
    """Adapter that performs read-only target lookups for the diff engine."""

    def __init__(self, registry: ResourceRegistry | None = None) -> None:
        self.registry = registry or create_default_registry()

    def load(self, resource_type: str, identity: str) -> dict[str, Any] | None:
        handler = self.registry.get_handler(resource_type)
        document = handler.get_target(identity)
        return handler.serialize(document) if document is not None else None
