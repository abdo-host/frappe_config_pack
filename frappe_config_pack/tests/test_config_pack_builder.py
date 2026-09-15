from __future__ import annotations

import unittest

from frappe_config_pack.core.exceptions import ConfigPackError
from frappe_config_pack.services.config_pack_builder import ConfigPackBuildService, ConfigPackSelection
from frappe_config_pack.services.reader import PackageReader
from frappe_config_pack.tests.helpers import custom_field, property_setter


class TestConfigPackBuildService(unittest.TestCase):
    def setUp(self) -> None:
        self.package = {
            "package_name": "Core Customizations",
            "slug": "core-customizations",
            "version": "1.0.0",
            "description": "Selected source configuration",
            "author": "Test Author",
            "frappe_version_constraint": ">=15,<17",
        }
        self.documents = {
            ("Custom Field", "Sales Invoice-custom_branch"): custom_field(),
            ("Property Setter", "Sales Invoice-customer-reqd"): property_setter(),
        }

    def test_builds_selected_source_resources_through_phase_one_engine(self) -> None:
        result = ConfigPackBuildService().build_from_selections(
            self.package,
            [
                ConfigPackSelection("Custom Field", "Sales Invoice-custom_branch", "Sales Invoice.custom_branch"),
                ConfigPackSelection("Property Setter", "Sales Invoice-customer-reqd", "Sales Invoice.customer.reqd"),
            ],
            lambda resource_type, name: self.documents[(resource_type, name)],
        )
        parsed = PackageReader().read(result.archive)
        self.assertEqual(parsed.manifest["resources"], {"Custom Field": 1, "Property Setter": 1})
        self.assertEqual(len(parsed.resources), 2)

    def test_requires_at_least_one_selection(self) -> None:
        with self.assertRaises(ConfigPackError):
            ConfigPackBuildService().build_from_selections(self.package, [], lambda *_: {})
