from __future__ import annotations

import unittest

from frappe_config_pack.handlers.custom_field import CustomFieldHandler
from frappe_config_pack.tests.helpers import changed_metadata, custom_field


class TestCustomFieldHandler(unittest.TestCase):
    def test_normalizes_irrelevant_metadata_and_boolean_values(self) -> None:
        handler = CustomFieldHandler()
        payload = handler.serialize(custom_field())
        self.assertEqual(payload["identity"], "Sales Invoice.custom_branch")
        self.assertEqual(payload["data"]["reqd"], 0)
        self.assertNotIn("modified", payload["data"])
        self.assertEqual(payload, handler.serialize(changed_metadata(custom_field())))

    def test_archive_path_is_stable_and_safe(self) -> None:
        handler = CustomFieldHandler()
        path = handler.archive_path(handler.serialize(custom_field()))
        self.assertTrue(path.startswith("resources/custom_fields/sales-invoice/"))
        self.assertTrue(path.endswith(".json"))
