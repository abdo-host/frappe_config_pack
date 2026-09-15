from __future__ import annotations

import unittest

from frappe_config_pack.handlers.custom_field import CustomFieldHandler
from frappe_config_pack.services.builder import PackageBuilder, ResourceInput
from frappe_config_pack.services.deployment import DeploymentService
from frappe_config_pack.services.reader import PackageReader
from frappe_config_pack.tests.helpers import custom_field, manifest


class TargetLoader:
    def __init__(self, target: dict) -> None:
        self.target = target

    def load(self, _resource_type: str, _identity: str) -> dict:
        return self.target


class NoMutationExecutor:
    def __init__(self) -> None:
        self.called = False
        self.cache_refreshed = False

    def execute(self, _payload: dict, _action: object) -> None:
        self.called = True

    def refresh_caches(self, _payloads: object) -> None:
        self.cache_refreshed = True


class TestDeploymentIntegration(unittest.TestCase):
    def test_built_package_can_be_read_diffed_and_dry_run_without_mutation(self) -> None:
        source = custom_field()
        built = PackageBuilder().build(manifest({"Custom Field": 1}), [ResourceInput("Custom Field", source)])
        package = PackageReader().read(built.archive)
        target = CustomFieldHandler().serialize(source)
        executor = NoMutationExecutor()

        plan = DeploymentService().dry_run(package.resources, TargetLoader(target))
        result = DeploymentService().apply(
            package.resources,
            TargetLoader(target),
            executor,
            {},
            plan.expected_target_checksums,
        )

        self.assertTrue(plan.ready)
        self.assertEqual(plan.summary, {"Create": 0, "Safe Update": 0, "Skip": 1, "Blocked": 0})
        self.assertEqual(result.summary, {"Applied": 0, "Skipped": 1})
        self.assertFalse(executor.called)
        self.assertFalse(executor.cache_refreshed)
