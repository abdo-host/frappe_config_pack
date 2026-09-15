from __future__ import annotations

import unittest

from frappe_config_pack.core.exceptions import UnknownResourceTypeError
from frappe_config_pack.core.registry import ResourceRegistry, create_default_registry
from frappe_config_pack.handlers.custom_field import CustomFieldHandler


class TestRegistry(unittest.TestCase):
    def test_default_registry_contains_all_current_handlers(self) -> None:
        registry = create_default_registry()
        self.assertEqual(
            registry.resource_types(),
            (
                "Client Script",
                "Custom DocPerm",
                "Custom Field",
                "Notification",
                "Print Format",
                "Property Setter",
                "Report",
                "Role",
                "Server Script",
                "Workflow",
                "Workflow State",
            ),
        )
        self.assertIsInstance(registry.get_handler("Custom Field"), CustomFieldHandler)

    def test_unknown_resource_type_is_rejected(self) -> None:
        with self.assertRaises(UnknownResourceTypeError):
            create_default_registry().get_handler("Unregistered Resource")

    def test_duplicate_registration_is_rejected(self) -> None:
        registry = ResourceRegistry()
        registry.register("Custom Field", CustomFieldHandler)
        with self.assertRaises(ValueError):
            registry.register("Custom Field", CustomFieldHandler)
