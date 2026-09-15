from __future__ import annotations

import unittest
from collections.abc import Mapping
from typing import Any

from frappe_config_pack.core.registry import ResourceRegistry
from frappe_config_pack.handlers.base import BaseResourceHandler
from frappe_config_pack.services.resource_browser import (
    ResourceBrowser,
    selected_resource_counts,
    selected_resource_names,
)


class BrowserTestHandler(BaseResourceHandler):
    resource_type = "Browser Test"
    archive_directory = "browser_tests"

    def get_identity(self, document: Mapping[str, Any]) -> str:
        return f"{document['dt']}.{document['fieldname']}"

    def normalize(self, data: Mapping[str, Any]) -> dict[str, Any]:
        return dict(data)

    def archive_path(self, payload: Mapping[str, Any]) -> str:
        return "resources/browser_tests/example.json"

    def list_resources(
        self,
        filters: Mapping[str, Any] | None = None,
        *,
        start: int = 0,
        page_length: int = 20,
    ) -> list[dict[str, Any]]:
        self.filters = dict(filters or {})
        self.start = start
        self.page_length = page_length
        return [{"name": "Test-custom_field", "dt": "Test", "fieldname": "custom_field", "label": "Custom Field"}]


class SecondBrowserTestHandler(BrowserTestHandler):
    resource_type = "Another Browser Test"

    def list_resources(
        self,
        filters: Mapping[str, Any] | None = None,
        *,
        start: int = 0,
        page_length: int = 20,
    ) -> list[dict[str, Any]]:
        self.filters = dict(filters or {})
        self.start = start
        self.page_length = page_length
        return [{"name": "Test-another_field", "dt": "Test", "fieldname": "another_field", "label": "Another Field"}]


class TestResourceBrowser(unittest.TestCase):
    def test_selected_resource_counts_include_only_selected_rows(self) -> None:
        resources = [
            {"resource_type": "Custom Field", "resource_name": "custom_a", "selected": 1},
            {"resource_type": "Custom Field", "resource_name": "custom_b", "selected": True},
            {"resource_type": "Workflow", "resource_name": "approval", "selected": "1"},
            {"resource_type": "Role", "resource_name": "Accounts User", "selected": 0},
        ]

        self.assertEqual(selected_resource_counts(resources), {"Custom Field": 2, "Workflow": 1})
        self.assertEqual(
            selected_resource_names(resources),
            {"Custom Field": ["custom_a", "custom_b"], "Workflow": ["approval"]},
        )

    def test_supports_registered_types_and_returns_handler_derived_identity(self) -> None:
        registry = ResourceRegistry()
        registry.register("Browser Test", BrowserTestHandler)
        page = ResourceBrowser(registry).search(
            "Browser Test", query="custom", reference_doctype="Test", start=20, page_length=20
        )
        self.assertEqual(page["start"], 20)
        self.assertEqual(page["items"][0]["resource_identity"], "Test.custom_field")
        self.assertEqual(page["items"][0]["reference_doctype"], "Test")

    def test_all_groups_each_supported_type_for_the_builder(self) -> None:
        registry = ResourceRegistry()
        registry.register("Browser Test", BrowserTestHandler)
        registry.register("Another Browser Test", SecondBrowserTestHandler)

        page = ResourceBrowser(registry).search("All", query="field", start=0, page_length=10)

        self.assertTrue(page["is_all"])
        self.assertEqual(
            [section["resource_type"] for section in page["sections"]],
            ["Another Browser Test", "Browser Test"],
        )
        self.assertEqual(page["sections"][0]["items"][0]["resource_identity"], "Test.another_field")
