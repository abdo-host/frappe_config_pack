from __future__ import annotations

import unittest

from frappe_config_pack.core.exceptions import ManifestValidationError, UnsupportedFormatError
from frappe_config_pack.core.manifest import validate_manifest
from frappe_config_pack.tests.helpers import manifest


class TestManifest(unittest.TestCase):
    def test_valid_manifest_is_accepted(self) -> None:
        self.assertEqual(validate_manifest(manifest())["slug"], "core-customizations")

    def test_missing_required_field_is_rejected(self) -> None:
        value = manifest()
        del value["author"]
        with self.assertRaises(ManifestValidationError):
            validate_manifest(value)

    def test_invalid_semantic_version_is_rejected(self) -> None:
        value = manifest()
        value["version"] = "release-one"
        with self.assertRaises(ManifestValidationError):
            validate_manifest(value)

    def test_unsupported_format_is_rejected(self) -> None:
        value = manifest()
        value["format_version"] = "2.0"
        with self.assertRaises(UnsupportedFormatError):
            validate_manifest(value)

    def test_malformed_required_app_is_rejected(self) -> None:
        value = manifest()
        value["required_apps"] = [{"app": "frappe"}]
        with self.assertRaises(ManifestValidationError):
            validate_manifest(value)
