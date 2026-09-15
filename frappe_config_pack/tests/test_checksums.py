from __future__ import annotations

import unittest

from frappe_config_pack.core.checksums import package_checksum, resource_checksum
from frappe_config_pack.handlers.custom_field import CustomFieldHandler
from frappe_config_pack.tests.helpers import changed_metadata, custom_field, manifest


class TestChecksums(unittest.TestCase):
    def test_irrelevant_metadata_does_not_change_resource_checksum(self) -> None:
        handler = CustomFieldHandler()
        original = handler.serialize(custom_field())
        metadata_changed = handler.serialize(changed_metadata(custom_field()))
        self.assertEqual(resource_checksum(original), resource_checksum(metadata_changed))

    def test_meaningful_change_changes_resource_checksum(self) -> None:
        handler = CustomFieldHandler()
        original = handler.serialize(custom_field())
        changed = custom_field()
        changed["label"] = "Sales Branch"
        self.assertNotEqual(resource_checksum(original), resource_checksum(handler.serialize(changed)))

    def test_package_checksum_ignores_build_timestamp_but_not_resource_checksums(self) -> None:
        resource_checksums = {"Custom Field:Sales Invoice.custom_branch": "a" * 64}
        first = manifest()
        second = manifest()
        second["created_at"] = "2030-01-01T00:00:00+00:00"
        self.assertEqual(package_checksum(first, resource_checksums), package_checksum(second, resource_checksums))
        self.assertNotEqual(
            package_checksum(first, resource_checksums),
            package_checksum(first, {"Custom Field:Sales Invoice.custom_branch": "b" * 64}),
        )
