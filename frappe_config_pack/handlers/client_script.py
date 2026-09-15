"""Deterministic serializer and source browser for Client Script."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from frappe_config_pack.core.exceptions import ResourceValidationError
from frappe_config_pack.handlers._frappe import get_document_by_filters, get_frappe, validated_page
from frappe_config_pack.handlers._paths import archive_component, identity_suffix
from frappe_config_pack.handlers.base import BaseResourceHandler


class ClientScriptHandler(BaseResourceHandler):
    resource_type = "Client Script"
    archive_directory = "client_scripts"
    managed_fields = frozenset({"name", "dt", "view", "enabled", "script", "module"})

    def get_identity(self, document: Mapping[str, Any]) -> str:
        name = document.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ResourceValidationError("Client Script requires its stable document name.")
        return name

    def normalize(self, data: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(data, Mapping):
            raise ResourceValidationError("Client Script data must be an object.")
        result = {field: data.get(field) for field in self.managed_fields if field in data}
        self.get_identity(result)
        if not isinstance(result.get("dt"), str) or not result["dt"].strip():
            raise ResourceValidationError("Client Script requires a DocType (dt).")
        if "enabled" in result:
            result["enabled"] = _as_frappe_boolean(result["enabled"])
        return dict(sorted(result.items()))

    def archive_path(self, payload: Mapping[str, Any]) -> str:
        data, identity = payload["data"], payload["identity"]
        return (
            f"resources/{self.archive_directory}/{archive_component(data['dt'])}/"
            f"{archive_component(identity)}--{identity_suffix(identity)}.json"
        )

    def get_target(self, identity: str, context: Any = None) -> dict[str, Any] | None:
        if self.get_identity({"name": identity}) != identity:
            raise ResourceValidationError("Client Script target identity is invalid.")
        return get_document_by_filters(self.resource_type, {"name": identity})

    def list_resources(
        self, filters: Mapping[str, Any] | None = None, *, start: int = 0, page_length: int = 20
    ) -> list[dict[str, Any]]:
        start, page_length = validated_page(start, page_length)
        filters = dict(filters or {})
        query = filters.pop("query", "")
        reference_doctype = filters.pop("reference_doctype", None)
        if reference_doctype:
            filters["dt"] = reference_doctype
        frappe = get_frappe()
        return frappe.get_all(
            self.resource_type,
            filters=filters,
            or_filters={"name": ["like", f"%{query}%"]} if query else None,
            fields=["name", "dt", "view", "enabled", "module"],
            order_by="modified desc, name asc",
            start=start,
            page_length=page_length,
        )


def _as_frappe_boolean(value: Any) -> int:
    if value in (True, 1, "1"):
        return 1
    if value in (False, 0, "0", None, ""):
        return 0
    raise ResourceValidationError(f"Invalid Frappe boolean value: {value!r}.")
