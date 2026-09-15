"""Lazy Frappe access so deterministic handler tests remain framework-free."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def get_frappe() -> Any:
    """Import Frappe only when a handler is used against a real site."""

    import frappe

    return frappe


def get_document_by_filters(doctype: str, filters: Mapping[str, Any]) -> dict[str, Any] | None:
    """Read one Frappe document by its stable handler-defined identity fields."""

    frappe = get_frappe()
    name = frappe.db.get_value(doctype, dict(filters), "name")
    if not name:
        return None
    return frappe.get_doc(doctype, name).as_dict()


def validated_page(start: int, page_length: int) -> tuple[int, int]:
    """Keep resource browsing bounded and deterministic."""

    if start < 0:
        raise ValueError("start cannot be negative.")
    if not 1 <= page_length <= 100:
        raise ValueError("page_length must be between 1 and 100.")
    return start, page_length
