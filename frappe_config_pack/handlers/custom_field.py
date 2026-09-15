"""Deterministic serializer for Frappe Custom Field configuration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from frappe_config_pack.core.constants import IRRELEVANT_Frappe_METADATA
from frappe_config_pack.core.dependencies import Dependency
from frappe_config_pack.core.exceptions import ResourceValidationError
from frappe_config_pack.handlers._frappe import get_document_by_filters, get_frappe, validated_page
from frappe_config_pack.handlers._paths import archive_component, identity_suffix
from frappe_config_pack.handlers.base import BaseResourceHandler


class CustomFieldHandler(BaseResourceHandler):
    resource_type = "Custom Field"
    archive_directory = "custom_fields"
    managed_fields = frozenset(
        {
            "dt", "fieldname", "label", "fieldtype", "options", "insert_after", "reqd", "read_only",
            "hidden", "default", "description", "depends_on", "mandatory_depends_on", "read_only_depends_on",
            "collapsible", "collapsible_depends_on", "unique", "no_copy", "in_list_view",
            "in_standard_filter", "in_global_search", "allow_in_quick_entry", "precision", "length",
        }
    )
    boolean_fields = frozenset(
        {
            "reqd", "read_only", "hidden", "collapsible", "unique", "no_copy", "in_list_view",
            "in_standard_filter", "in_global_search", "allow_in_quick_entry",
        }
    )

    def get_identity(self, document: Mapping[str, Any]) -> str:
        dt, fieldname = document.get("dt"), document.get("fieldname")
        if not isinstance(dt, str) or not dt.strip() or not isinstance(fieldname, str) or not fieldname.strip():
            raise ResourceValidationError("Custom Field requires non-empty dt and fieldname.")
        return f"{dt}.{fieldname}"

    def normalize(self, data: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(data, Mapping):
            raise ResourceValidationError("Custom Field data must be an object.")
        result = {field: data.get(field) for field in self.managed_fields if field in data and field not in IRRELEVANT_Frappe_METADATA}
        for field in self.boolean_fields.intersection(result):
            result[field] = _as_frappe_boolean(result[field])
        self.get_identity(result)
        return dict(sorted(result.items()))

    def archive_path(self, payload: Mapping[str, Any]) -> str:
        data, identity = payload["data"], payload["identity"]
        return (
            f"resources/{self.archive_directory}/{archive_component(data['dt'])}/"
            f"{archive_component(data['fieldname'])}--{identity_suffix(identity)}.json"
        )

    def get_dependencies(self, payload: Mapping[str, Any], context: Any = None) -> list[Dependency]:
        """Expose only explicit DocType references carried by supported field types."""

        data = payload["data"]
        fieldtype, options = data.get("fieldtype"), data.get("options")
        if fieldtype not in {"Link", "Table", "Table MultiSelect"} or not isinstance(options, str) or not options.strip():
            return []
        reason = {
            "Link": "Link field options",
            "Table": "Table field child DocType",
            "Table MultiSelect": "Table MultiSelect child DocType",
        }[fieldtype]
        return [Dependency.doctype(options.strip(), reason)]

    def get_target(self, identity: str, context: Any = None) -> dict[str, Any] | None:
        dt, separator, fieldname = identity.rpartition(".")
        if not separator or self.get_identity({"dt": dt, "fieldname": fieldname}) != identity:
            raise ResourceValidationError("Custom Field target identity is invalid.")
        return get_document_by_filters(self.resource_type, {"dt": dt, "fieldname": fieldname})

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
            or_filters={"fieldname": ["like", f"%{query}%"]} if query else None,
            fields=["name", "dt", "fieldname", "label", "fieldtype", "options"],
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
