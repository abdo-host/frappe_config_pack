"""Deterministic serializer and source browser for Workflow State."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from frappe_config_pack.core.exceptions import ResourceValidationError
from frappe_config_pack.handlers._frappe import get_document_by_filters, get_frappe, validated_page
from frappe_config_pack.handlers._paths import archive_component, identity_suffix
from frappe_config_pack.handlers.base import BaseResourceHandler


class WorkflowStateHandler(BaseResourceHandler):
    resource_type = "Workflow State"
    archive_directory = "workflow_states"
    managed_fields = frozenset({"workflow_state_name", "icon", "style"})

    def get_identity(self, document: Mapping[str, Any]) -> str:
        value = document.get("workflow_state_name")
        if not isinstance(value, str) or not value.strip():
            raise ResourceValidationError("Workflow State requires workflow_state_name.")
        return value

    def normalize(self, data: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(data, Mapping):
            raise ResourceValidationError("Workflow State data must be an object.")
        result = {field: data.get(field) for field in self.managed_fields if field in data}
        self.get_identity(result)
        return dict(sorted(result.items()))

    def archive_path(self, payload: Mapping[str, Any]) -> str:
        identity = payload["identity"]
        return f"resources/{self.archive_directory}/{archive_component(identity)}--{identity_suffix(identity)}.json"

    def get_target(self, identity: str, context: Any = None) -> dict[str, Any] | None:
        if self.get_identity({"workflow_state_name": identity}) != identity:
            raise ResourceValidationError("Workflow State target identity is invalid.")
        return get_document_by_filters(self.resource_type, {"workflow_state_name": identity})

    def list_resources(
        self, filters: Mapping[str, Any] | None = None, *, start: int = 0, page_length: int = 20
    ) -> list[dict[str, Any]]:
        start, page_length = validated_page(start, page_length)
        filters = dict(filters or {})
        query = filters.pop("query", "")
        filters.pop("reference_doctype", None)
        frappe = get_frappe()
        return frappe.get_all(
            self.resource_type,
            filters=filters,
            or_filters={"workflow_state_name": ["like", f"%{query}%"]} if query else None,
            fields=["name", "workflow_state_name", "style"],
            order_by="workflow_state_name asc",
            start=start,
            page_length=page_length,
        )
