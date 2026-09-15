"""Pagination and normalized summaries for the source-site resource browser."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from frappe_config_pack.core.registry import ResourceRegistry, create_default_registry


def selected_resource_counts(resources: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Count selected package rows by resource type for source-browser feedback."""

    return dict(
        sorted(
            Counter(
                resource["resource_type"]
                for resource in resources
                if resource.get("selected") in {True, "1"} and isinstance(resource.get("resource_type"), str)
            ).items()
        )
    )


def selected_resource_names(resources: Iterable[Mapping[str, Any]]) -> dict[str, list[str]]:
    """Group selected source record names so the browser can render their disabled state."""

    grouped: dict[str, list[str]] = {}
    for resource in resources:
        resource_type = resource.get("resource_type")
        resource_name = resource.get("resource_name")
        if (
            resource.get("selected") not in {True, "1"}
            or not isinstance(resource_type, str)
            or not isinstance(resource_name, str)
        ):
            continue
        grouped.setdefault(resource_type, []).append(resource_name)
    return {resource_type: sorted(names) for resource_type, names in sorted(grouped.items())}


class ResourceBrowser:
    """Expose only registered resource types and bounded source-site pages."""

    def __init__(self, registry: ResourceRegistry | None = None) -> None:
        self.registry = registry or create_default_registry()

    def supported_resource_types(self) -> tuple[str, ...]:
        return self.registry.resource_types()

    def search(
        self,
        resource_type: str,
        *,
        query: str = "",
        reference_doctype: str | None = None,
        start: int = 0,
        page_length: int = 20,
    ) -> dict[str, Any]:
        """Return a source-site page whose identities are handler-derived."""

        if resource_type == "All":
            return self._search_all(
                query=query,
                reference_doctype=reference_doctype,
                start=start,
                page_length=page_length,
            )

        handler = self.registry.get_handler(resource_type)
        rows = handler.list_resources(
            {"query": query, "reference_doctype": reference_doctype},
            start=start,
            page_length=self._lookahead_page_length(page_length),
        )
        items = [self._summary(resource_type, handler, dict(row)) for row in rows[:page_length]]
        return {
            "items": items,
            "start": start,
            "page_length": page_length,
            "has_more": len(rows) > page_length,
        }

    def _search_all(
        self,
        *,
        query: str,
        reference_doctype: str | None,
        start: int,
        page_length: int,
    ) -> dict[str, Any]:
        """Return a bounded page for every supported type, grouped for the builder UI."""

        sections = []
        for supported_type in self.supported_resource_types():
            handler = self.registry.get_handler(supported_type)
            rows = handler.list_resources(
                {"query": query, "reference_doctype": reference_doctype},
                start=start,
                page_length=self._lookahead_page_length(page_length),
            )
            items = [self._summary(supported_type, handler, dict(row)) for row in rows[:page_length]]
            if items:
                sections.append(
                    {
                        "resource_type": supported_type,
                        "items": items,
                        "has_more": len(rows) > page_length,
                    }
                )

        return {
            "items": [],
            "sections": sections,
            "is_all": True,
            "start": start,
            "page_length": page_length,
            "has_more": any(section["has_more"] for section in sections),
        }

    @staticmethod
    def _lookahead_page_length(page_length: int) -> int:
        """Ask handlers for one extra row so next-page availability is accurate."""

        if not 1 <= page_length <= 100:
            raise ValueError("page_length must be between 1 and 100.")
        return min(page_length + 1, 100)

    @staticmethod
    def _summary(resource_type: str, handler: Any, row: dict[str, Any]) -> dict[str, Any]:
        identity = handler.get_identity(row)
        reference_doctype = row.get("dt") or row.get("doc_type") or row.get("document_type")
        display_name = (
            row.get("label")
            or row.get("fieldname")
            or row.get("workflow_name")
            or row.get("workflow_state_name")
            or row.get("role_name")
            or row.get("name")
        )
        return {
            "resource_type": resource_type,
            "resource_name": row["name"],
            "resource_identity": identity,
            "reference_doctype": reference_doctype,
            "display_name": display_name,
        }
