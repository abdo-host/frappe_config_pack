"""Stable boundary between the generic package engine and Frappe resources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from frappe_config_pack.core.exceptions import ConfigPackError, ResourceValidationError


class BaseResourceHandler(ABC):
    """Contract implemented by every configuration resource type.

    Phase 1 implements the non-mutating export/validation boundary. Later
    phases will use the remaining methods without central type branching.
    """

    resource_type: str | None = None
    archive_directory: str | None = None

    def list_resources(
        self,
        filters: Mapping[str, Any] | None = None,
        *,
        start: int = 0,
        page_length: int = 20,
    ) -> list[dict[str, Any]]:
        """Return source-site resource summaries for the Phase 2 browser."""

        raise NotImplementedError

    @abstractmethod
    def get_identity(self, document: Mapping[str, Any]) -> str:
        """Return the stable identity of a logical resource."""

    @abstractmethod
    def normalize(self, data: Mapping[str, Any]) -> dict[str, Any]:
        """Return handler-owned, deterministic configuration state only."""

    @abstractmethod
    def archive_path(self, payload: Mapping[str, Any]) -> str:
        """Return the deterministic internal ZIP path for a normalized payload."""

    def serialize(self, document: Mapping[str, Any]) -> dict[str, Any]:
        """Create and validate the canonical resource envelope."""

        data = self.normalize(document)
        payload = {"resource_type": self.resource_type, "identity": self.get_identity(data), "data": data}
        self.validate(payload, context=None)
        return payload

    def deserialize(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Validate a package payload and return its normalized data."""

        self.validate(payload, context=None)
        return dict(payload["data"])

    def validate(self, payload: Mapping[str, Any], context: Any = None) -> None:
        """Enforce the standard envelope and handler-specific invariants."""

        if not isinstance(payload, Mapping):
            raise ResourceValidationError("Resource payload must be an object.")
        if payload.get("resource_type") != self.resource_type:
            raise ResourceValidationError(f"Expected resource type {self.resource_type!r}.")
        if not isinstance(payload.get("identity"), str) or not payload["identity"]:
            raise ResourceValidationError("Resource identity must be a non-empty string.")
        if not isinstance(payload.get("data"), Mapping):
            raise ResourceValidationError("Resource data must be an object.")
        normalized = self.normalize(payload["data"])
        if dict(payload["data"]) != normalized:
            raise ResourceValidationError("Resource data is not in the handler's normalized form.")
        if payload["identity"] != self.get_identity(normalized):
            raise ResourceValidationError("Resource identity does not match its data.")

    def get_dependencies(self, payload: Mapping[str, Any], context: Any = None) -> list[Any]:
        return []

    def required_capabilities(self, payload: Mapping[str, Any], context: Any = None) -> tuple[str, ...]:
        """Return target capabilities that must be enabled before this payload is installed."""

        return ()

    def get_target(self, identity: str, context: Any = None) -> Any:
        raise NotImplementedError

    def diff(self, source: Mapping[str, Any], target: Mapping[str, Any], context: Any = None) -> Any:
        raise NotImplementedError

    def apply(self, payload: Mapping[str, Any], strategy: str, context: Any = None) -> Any:
        """Create or safely update only the normalized, handler-owned document fields."""

        self.validate(payload, context)
        if strategy == "Skip":
            return None
        if strategy not in {"Create", "Safe Update"}:
            raise ConfigPackError(f"Unsupported deployment strategy {strategy!r}.")

        target = self.get_target(payload["identity"], context)
        from frappe_config_pack.handlers._frappe import get_frappe

        frappe = get_frappe()
        if strategy == "Create":
            if target is not None:
                raise ConfigPackError(f"Target resource {payload['identity']!r} already exists.")
            return frappe.get_doc({"doctype": self.resource_type, **payload["data"]}).insert().as_dict()

        if target is None:
            raise ConfigPackError(f"Target resource {payload['identity']!r} no longer exists.")
        document = frappe.get_doc(self.resource_type, target["name"])
        document.update(dict(payload["data"]))
        return document.save().as_dict()

    def snapshot(self, identity: str, context: Any = None) -> Any:
        """Return the current normalized state, or ``None`` when it does not exist."""

        target = self.get_target(identity, context)
        return self.serialize(target) if target is not None else None

    def rollback(self, snapshot: Mapping[str, Any], context: Any = None) -> Any:
        """Restore normalized state without assuming whether the target still exists."""

        self.validate(snapshot, context)
        current = self.get_target(snapshot["identity"], context)
        action = "Safe Update" if current is not None else "Create"
        return self.apply(snapshot, action, context)

    def delete_target(self, identity: str, context: Any = None) -> bool:
        """Delete a target that was created by a release after rollback safeguards pass."""

        target = self.get_target(identity, context)
        if target is None:
            return False
        from frappe_config_pack.handlers._frappe import get_frappe

        get_frappe().delete_doc(self.resource_type, target["name"])
        return True
