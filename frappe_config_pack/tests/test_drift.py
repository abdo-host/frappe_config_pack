from __future__ import annotations

import unittest

from frappe_config_pack.core.checksums import resource_checksum
from frappe_config_pack.handlers.custom_field import CustomFieldHandler
from frappe_config_pack.services.drift import DriftService, DriftStatus
from frappe_config_pack.tests.helpers import custom_field


class DictTargetLoader:
    def __init__(self, resources: dict[tuple[str, str], dict]) -> None:
        self.resources = resources

    def load(self, resource_type: str, identity: str) -> dict | None:
        return self.resources.get((resource_type, identity))


class TestDriftService(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = CustomFieldHandler().serialize(custom_field())
        self.key = f"{self.payload['resource_type']}:{self.payload['identity']}"
        self.checksums = {self.key: resource_checksum(self.payload)}
        self.service = DriftService()

    def test_reports_clean_when_current_target_matches_installed_checksum(self) -> None:
        report = self.service.check(
            self.checksums,
            DictTargetLoader({(self.payload["resource_type"], self.payload["identity"]): self.payload}),
        )

        self.assertTrue(report.healthy)
        self.assertEqual(report.summary, {"Clean": 1, "Modified": 0, "Missing": 0})
        self.assertEqual(report.resources[0].status, DriftStatus.CLEAN)

    def test_reports_modified_without_correcting_current_target(self) -> None:
        modified = CustomFieldHandler().serialize({**custom_field(), "label": "Locally Changed Branch"})
        report = self.service.check(
            self.checksums,
            DictTargetLoader({(modified["resource_type"], modified["identity"]): modified}),
        )

        self.assertFalse(report.healthy)
        self.assertEqual(report.summary, {"Clean": 0, "Modified": 1, "Missing": 0})
        self.assertEqual(report.resources[0].status, DriftStatus.MODIFIED)
        self.assertEqual(report.resources[0].current_checksum, resource_checksum(modified))

    def test_reports_missing_when_an_installed_resource_no_longer_exists(self) -> None:
        report = self.service.check(self.checksums, DictTargetLoader({}))

        self.assertFalse(report.healthy)
        self.assertEqual(report.summary, {"Clean": 0, "Modified": 0, "Missing": 1})
        self.assertEqual(report.resources[0].status, DriftStatus.MISSING)
        self.assertIsNone(report.resources[0].current_checksum)
