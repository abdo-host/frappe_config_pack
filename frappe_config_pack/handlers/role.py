"""Deterministic serializer and source browser for custom Frappe Roles."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from frappe_config_pack.core.exceptions import ResourceValidationError
from frappe_config_pack.handlers._frappe import get_document_by_filters, get_frappe, validated_page
from frappe_config_pack.handlers._paths import archive_component, identity_suffix
from frappe_config_pack.handlers.base import BaseResourceHandler


class RoleHandler(BaseResourceHandler):
    resource_type = "Role"
    archive_directory = "roles"
    managed_fields = frozenset(
        {"role_name", "disabled", "desk_access", "two_factor_auth", "restrict_to_domain", "home_page", "is_custom"}
    )
    boolean_fields = frozenset({"disabled", "desk_access", "two_factor_auth", "is_custom"})

    def get_identity(self, document: Mapping[str, Any]) -> str:
        value = document.get("role_name")
        if not isinstance(value, str) or not value.strip():
            raise ResourceValidationError("Role requires role_name.")
        return value

    def normalize(self, data: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(data, Mapping):
            raise ResourceValidationError("Role data must be an object.")
        result = {field: data.get(field) for field in self.managed_fields if field in data}
        self.get_identity(result)
        for field in self.boolean_fields.intersection(result):
            result[field] = _as_frappe_boolean(result[field])
        if result.get("is_custom", 0) != 1:
            raise ResourceValidationError("Standard Frappe/ERPNext Roles are not packageable by default.")
        return dict(sorted(result.items()))

    def archive_path(self, payload: Mapping[str, Any]) -> str:
        identity = payload["identity"]
        return f"resources/{self.archive_directory}/{archive_component(identity)}--{identity_suffix(identity)}.json"

    def get_target(self, identity: str, context: Any = None) -> dict[str, Any] | None:
        if self.get_identity({"role_name": identity}) != identity:
            raise ResourceValidationError("Role target identity is invalid.")
        return get_document_by_filters(self.resource_type, {"role_name": identity})

    def list_resources(
        self, filters: Mapping[str, Any] | None = None, *, start: int = 0, page_length: int = 20
    ) -> list[dict[str, Any]]:
        start, page_length = validated_page(start, page_length)
        filters = {**dict(filters or {}), "is_custom": 1}
        query = filters.pop("query", "")
        filters.pop("reference_doctype", None)
        frappe = get_frappe()
        return frappe.get_all(
            self.resource_type,
            filters=filters,
            or_filters={"role_name": ["like", f"%{query}%"]} if query else None,
            fields=["name", "role_name", "disabled", "desk_access", "is_custom"],
            order_by="role_name asc",
            start=start,
            page_length=page_length,
        )


def _as_frappe_boolean(value: Any) -> int:
    if value in (True, 1, "1"):
        return 1
    if value in (False, 0, "0", None, ""):
        return 0
    raise ResourceValidationError(f"Invalid Frappe boolean value: {value!r}.")
