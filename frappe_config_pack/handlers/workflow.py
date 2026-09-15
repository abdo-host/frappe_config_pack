"""Deterministic serializer and source browser for Frappe Workflow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from frappe_config_pack.core.dependencies import Dependency
from frappe_config_pack.core.exceptions import ResourceValidationError
from frappe_config_pack.handlers._frappe import get_document_by_filters, get_frappe, validated_page
from frappe_config_pack.handlers._paths import archive_component, identity_suffix
from frappe_config_pack.handlers.base import BaseResourceHandler


class WorkflowHandler(BaseResourceHandler):
    resource_type = "Workflow"
    archive_directory = "workflows"
    managed_fields = frozenset(
        {"workflow_name", "document_type", "is_active", "override_status", "send_email_alert", "workflow_state_field", "states", "transitions"}
    )
    boolean_fields = frozenset({"is_active", "override_status", "send_email_alert"})
    state_fields = frozenset(
        {"state", "doc_status", "update_field", "update_value", "allow_edit", "message", "next_action_email_template", "is_optional_state", "avoid_status_override", "send_email"}
    )
    transition_fields = frozenset(
        {"state", "action", "next_state", "allowed", "allow_self_approval", "condition", "send_email_to_creator"}
    )

    def get_identity(self, document: Mapping[str, Any]) -> str:
        value = document.get("workflow_name")
        if not isinstance(value, str) or not value.strip():
            raise ResourceValidationError("Workflow requires workflow_name.")
        return value

    def normalize(self, data: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(data, Mapping):
            raise ResourceValidationError("Workflow data must be an object.")
        result = {field: data.get(field) for field in self.managed_fields if field in data}
        self.get_identity(result)
        if not isinstance(result.get("document_type"), str) or not result["document_type"].strip():
            raise ResourceValidationError("Workflow requires document_type.")
        for field in self.boolean_fields.intersection(result):
            result[field] = _as_frappe_boolean(result[field])
        result["states"] = _normalize_children(result.get("states", []), self.state_fields, {"is_optional_state", "avoid_status_override", "send_email"})
        result["transitions"] = _normalize_children(result.get("transitions", []), self.transition_fields, {"allow_self_approval", "send_email_to_creator"})
        return dict(sorted(result.items()))

    def archive_path(self, payload: Mapping[str, Any]) -> str:
        identity = payload["identity"]
        return f"resources/{self.archive_directory}/{archive_component(identity)}--{identity_suffix(identity)}.json"

    def get_dependencies(self, payload: Mapping[str, Any], context: Any = None) -> list[Dependency]:
        """Return explicit Workflow State, Role, and reference DocType requirements."""

        data = payload["data"]
        dependencies: set[Dependency] = {
            Dependency.doctype(data["document_type"], "Workflow reference DocType")
        }
        for state in data.get("states", []):
            name = state.get("state")
            if isinstance(name, str) and name.strip():
                dependencies.add(Dependency.resource("Workflow State", name.strip(), "Workflow state"))
        for transition in data.get("transitions", []):
            role = transition.get("allowed")
            if isinstance(role, str) and role.strip():
                dependencies.add(Dependency.resource("Role", role.strip(), "Workflow transition role"))
        return sorted(dependencies)

    def get_target(self, identity: str, context: Any = None) -> dict[str, Any] | None:
        if self.get_identity({"workflow_name": identity}) != identity:
            raise ResourceValidationError("Workflow target identity is invalid.")
        return get_document_by_filters(self.resource_type, {"workflow_name": identity})

    def list_resources(
        self, filters: Mapping[str, Any] | None = None, *, start: int = 0, page_length: int = 20
    ) -> list[dict[str, Any]]:
        start, page_length = validated_page(start, page_length)
        filters = dict(filters or {})
        query = filters.pop("query", "")
        reference_doctype = filters.pop("reference_doctype", None)
        if reference_doctype:
            filters["document_type"] = reference_doctype
        frappe = get_frappe()
        return frappe.get_all(
            self.resource_type,
            filters=filters,
            or_filters={"workflow_name": ["like", f"%{query}%"]} if query else None,
            fields=["name", "workflow_name", "document_type", "is_active"],
            order_by="modified desc, workflow_name asc",
            start=start,
            page_length=page_length,
        )


def _normalize_children(value: Any, allowed_fields: frozenset[str], boolean_fields: set[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ResourceValidationError("Workflow child rows must be a list.")
    normalized: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, Mapping):
            raise ResourceValidationError("Workflow child rows must be objects.")
        child = {field: row.get(field) for field in allowed_fields if field in row}
        for field in boolean_fields.intersection(child):
            child[field] = _as_frappe_boolean(child[field])
        normalized.append(dict(sorted(child.items())))
    return normalized


def _as_frappe_boolean(value: Any) -> int:
    if value in (True, 1, "1"):
        return 1
    if value in (False, 0, "0", None, ""):
        return 0
    raise ResourceValidationError(f"Invalid Frappe boolean value: {value!r}.")
