"""Deterministic serializer for Frappe Property Setter configuration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from frappe_config_pack.core.constants import IRRELEVANT_Frappe_METADATA
from frappe_config_pack.core.exceptions import ResourceValidationError
from frappe_config_pack.handlers._frappe import get_document_by_filters, get_frappe, validated_page
from frappe_config_pack.handlers._paths import archive_component, identity_suffix
from frappe_config_pack.handlers.base import BaseResourceHandler


class PropertySetterHandler(BaseResourceHandler):
    resource_type = "Property Setter"
    archive_directory = "property_setters"
    managed_fields = frozenset({"doc_type", "field_name", "property", "value", "property_type", "doctype_or_field"})

    def get_identity(self, document: Mapping[str, Any]) -> str:
        doc_type, field_name, property_name = (
            document.get("doc_type"),
            document.get("field_name"),
            document.get("property"),
        )
        if not isinstance(doc_type, str) or not doc_type.strip() or not isinstance(property_name, str) or not property_name.strip():
            raise ResourceValidationError("Property Setter requires non-empty doc_type and property.")
        if field_name is not None and not isinstance(field_name, str):
            raise ResourceValidationError("Property Setter field_name must be a string or null.")
        return f"{doc_type}.{field_name or '__doctype__'}.{property_name}"

    def normalize(self, data: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(data, Mapping):
            raise ResourceValidationError("Property Setter data must be an object.")
        result = {field: data.get(field) for field in self.managed_fields if field in data and field not in IRRELEVANT_Frappe_METADATA}
        if "field_name" not in result or result["field_name"] == "":
            result["field_name"] = None
        if "property_type" in result:
            result["value"] = _normalize_value(result.get("value"), result["property_type"])
        self.get_identity(result)
        return dict(sorted(result.items()))

    def archive_path(self, payload: Mapping[str, Any]) -> str:
        data, identity = payload["data"], payload["identity"]
        field = data["field_name"] or "doctype"
        return (
            f"resources/{self.archive_directory}/{archive_component(data['doc_type'])}/"
            f"{archive_component(field)}-{archive_component(data['property'])}--{identity_suffix(identity)}.json"
        )

    def get_target(self, identity: str, context: Any = None) -> dict[str, Any] | None:
        parts = identity.rsplit(".", 2)
        if len(parts) != 3:
            raise ResourceValidationError("Property Setter target identity is invalid.")
        doc_type, field_name, property_name = parts
        field_name = None if field_name == "__doctype__" else field_name
        if self.get_identity(
            {"doc_type": doc_type, "field_name": field_name, "property": property_name}
        ) != identity:
            raise ResourceValidationError("Property Setter target identity is invalid.")
        return get_document_by_filters(
            self.resource_type,
            {"doc_type": doc_type, "field_name": field_name, "property": property_name},
        )

    def list_resources(
        self, filters: Mapping[str, Any] | None = None, *, start: int = 0, page_length: int = 20
    ) -> list[dict[str, Any]]:
        start, page_length = validated_page(start, page_length)
        filters = dict(filters or {})
        query = filters.pop("query", "")
        reference_doctype = filters.pop("reference_doctype", None)
        if reference_doctype:
            filters["doc_type"] = reference_doctype
        frappe = get_frappe()
        return frappe.get_all(
            self.resource_type,
            filters=filters,
            or_filters={"field_name": ["like", f"%{query}%"]} if query else None,
            fields=["name", "doc_type", "field_name", "property", "value", "property_type"],
            order_by="modified desc, name asc",
            start=start,
            page_length=page_length,
        )


def _normalize_value(value: Any, property_type: Any) -> Any:
    if not isinstance(property_type, str):
        raise ResourceValidationError("Property Setter property_type must be a string.")
    kind = property_type.lower()
    if kind in {"check", "int", "integer"} and isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    if kind in {"float", "currency", "percent"} and isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return value
    return value
