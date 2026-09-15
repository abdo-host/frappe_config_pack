from __future__ import annotations

import unittest

from frappe_config_pack.core.checksums import resource_checksum
from frappe_config_pack.handlers.custom_field import CustomFieldHandler
from frappe_config_pack.services.diff_engine import (
    ConflictResolution,
    ConflictResolutionChoice,
    DiffEngine,
    ResourceState,
    field_differences,
)
from frappe_config_pack.tests.helpers import custom_field


class DictTargetLoader:
    def __init__(self, resources: dict[tuple[str, str], dict]) -> None:
        self.resources = resources

    def load(self, resource_type: str, identity: str) -> dict | None:
        return self.resources.get((resource_type, identity))


class TestDiffEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.handler = CustomFieldHandler()
        self.package = self.handler.serialize(custom_field())
        self.key = (self.package["resource_type"], self.package["identity"])
        self.engine = DiffEngine()

    def test_reports_new_when_target_is_missing(self) -> None:
        result = self.engine.compare([self.package], DictTargetLoader({}))

        self.assertEqual(result.resources[0].state, ResourceState.NEW)
        self.assertIsNone(result.resources[0].target_checksum)
        self.assertEqual(result.summary["NEW"], 1)

    def test_reports_unchanged_when_normalized_checksums_match(self) -> None:
        result = self.engine.compare([self.package], DictTargetLoader({self.key: self.package}))

        self.assertEqual(result.resources[0].state, ResourceState.UNCHANGED)
        self.assertEqual(result.resources[0].field_differences, ())

    def test_reports_modified_with_field_level_differences(self) -> None:
        target = self.handler.serialize({**custom_field(), "label": "Legacy Branch", "reqd": "1"})
        result = self.engine.compare([self.package], DictTargetLoader({self.key: target}))

        self.assertEqual(result.resources[0].state, ResourceState.MODIFIED)
        self.assertEqual(
            [(difference.field, difference.target_value, difference.package_value) for difference in result.resources[0].field_differences],
            [("label", "Legacy Branch", "Branch"), ("reqd", 1, 0)],
        )

    def test_reports_conflict_when_target_changed_since_the_known_baseline(self) -> None:
        baseline = self.handler.serialize({**custom_field(), "label": "Original Branch"})
        target = self.handler.serialize({**custom_field(), "label": "Locally Changed"})
        result = self.engine.compare(
            [self.package],
            DictTargetLoader({self.key: target}),
            baseline_checksums={f"{self.key[0]}:{self.key[1]}": resource_checksum(baseline)},
        )

        self.assertEqual(result.resources[0].state, ResourceState.CONFLICT)
        self.assertEqual(result.unresolved_conflicts[0].identity, self.package["identity"])
        self.assertEqual(
            result.resources[0].as_dict()["resolution_options"],
            ["Keep Target", "Use Package", "Skip"],
        )

    def test_marks_unavailable_dependencies_before_target_comparison(self) -> None:
        result = self.engine.compare(
            [self.package],
            DictTargetLoader({}),
            dependency_checker=lambda _payload: ["DocType: Branch"],
        )

        self.assertEqual(result.resources[0].state, ResourceState.MISSING_DEPENDENCY)
        self.assertEqual(result.resources[0].missing_dependencies, ("DocType: Branch",))

    def test_conflict_resolution_model_requires_an_explicit_choice(self) -> None:
        unresolved = ConflictResolution("Custom Field", "Sales Invoice.custom_branch")
        resolved = ConflictResolution(
            "Custom Field", "Sales Invoice.custom_branch", ConflictResolutionChoice.USE_PACKAGE
        )

        self.assertFalse(unresolved.is_resolved)
        self.assertTrue(resolved.is_resolved)

    def test_field_differences_are_stable_for_nested_data(self) -> None:
        differences = field_differences(
            {"label": "Package", "options": {"one": 1, "two": 2}},
            {"label": "Target", "options": {"one": 1, "three": 3}},
        )

        self.assertEqual(
            [(difference.field, difference.target_value, difference.package_value) for difference in differences],
            [("label", "Target", "Package"), ("options.three", 3, None), ("options.two", None, 2)],
        )
