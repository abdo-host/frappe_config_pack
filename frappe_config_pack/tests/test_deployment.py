from __future__ import annotations

import unittest

from frappe_config_pack.core.checksums import resource_checksum
from frappe_config_pack.core.exceptions import (
    DeploymentBlockedError,
    DuplicateResourceError,
    StalePreviewError,
)
from frappe_config_pack.handlers.custom_field import CustomFieldHandler
from frappe_config_pack.handlers.role import RoleHandler
from frappe_config_pack.handlers.workflow import WorkflowHandler
from frappe_config_pack.handlers.workflow_state import WorkflowStateHandler
from frappe_config_pack.services.deployment import DeploymentAction, DeploymentService
from frappe_config_pack.tests.helpers import custom_field


class DictTargetLoader:
    def __init__(self, resources: dict[tuple[str, str], dict]) -> None:
        self.resources = resources

    def load(self, resource_type: str, identity: str) -> dict | None:
        return self.resources.get((resource_type, identity))


class ChangingTargetLoader(DictTargetLoader):
    def __init__(self, initial: dict, changed: dict) -> None:
        super().__init__({(initial["resource_type"], initial["identity"]): initial})
        self.initial = initial
        self.changed = changed
        self.calls = 0

    def load(self, resource_type: str, identity: str) -> dict | None:
        self.calls += 1
        return self.initial if self.calls == 1 else self.changed


class FakeExecutor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, str, DeploymentAction]] = []
        self.refreshed: list[dict] = []

    def execute(self, payload: dict, action: DeploymentAction) -> None:
        self.executed.append((payload["resource_type"], payload["identity"], action))

    def refresh_caches(self, payloads: list[dict]) -> None:
        self.refreshed = list(payloads)


class TestDeploymentService(unittest.TestCase):
    def setUp(self) -> None:
        self.handler = CustomFieldHandler()
        self.package = self.handler.serialize(custom_field())
        self.key = f"{self.package['resource_type']}:{self.package['identity']}"
        self.service = DeploymentService()

    def test_dry_run_plans_create_without_mutating(self) -> None:
        plan = self.service.dry_run([self.package], DictTargetLoader({}))

        self.assertTrue(plan.ready)
        self.assertEqual(plan.resources[0].action, DeploymentAction.CREATE)
        self.assertEqual(plan.expected_target_checksums, {self.key: None})

    def test_modified_resource_requires_explicit_safe_update_or_skip(self) -> None:
        target = self.handler.serialize({**custom_field(), "label": "Legacy Branch"})
        plan = self.service.dry_run(
            [self.package],
            DictTargetLoader({(self.package["resource_type"], self.package["identity"]): target}),
        )

        self.assertFalse(plan.ready)
        self.assertEqual(plan.blockers[0].code, "explicit_action_required")

    def test_dry_run_accepts_explicit_safe_update(self) -> None:
        target = self.handler.serialize({**custom_field(), "label": "Legacy Branch"})
        plan = self.service.dry_run(
            [self.package],
            DictTargetLoader({(self.package["resource_type"], self.package["identity"]): target}),
            {self.key: "Safe Update"},
        )

        self.assertTrue(plan.ready)
        self.assertEqual(plan.resources[0].action, DeploymentAction.SAFE_UPDATE)

    def test_unresolved_conflict_blocks_apply(self) -> None:
        baseline = self.handler.serialize({**custom_field(), "label": "Original Branch"})
        target = self.handler.serialize({**custom_field(), "label": "Locally Changed"})
        loader = DictTargetLoader({(self.package["resource_type"], self.package["identity"]): target})
        executor = FakeExecutor()

        with self.assertRaises(DeploymentBlockedError):
            self.service.apply(
                [self.package],
                loader,
                executor,
                {},
                {self.key: resource_checksum(target)},
                baseline_checksums={self.key: resource_checksum(baseline)},
            )

        self.assertEqual(executor.executed, [])

    def test_apply_rechecks_target_checksum_immediately_before_mutation(self) -> None:
        target = self.handler.serialize({**custom_field(), "label": "Legacy Branch"})
        changed = self.handler.serialize({**custom_field(), "label": "Changed After Preview"})
        loader = ChangingTargetLoader(target, changed)
        executor = FakeExecutor()

        with self.assertRaises(StalePreviewError):
            self.service.apply(
                [self.package],
                loader,
                executor,
                {self.key: "Safe Update"},
                {self.key: resource_checksum(target)},
            )

        self.assertEqual(executor.executed, [])
        self.assertEqual(executor.refreshed, [])

    def test_apply_executes_only_reviewed_actions_and_refreshes_cache_after_changes(self) -> None:
        executor = FakeExecutor()
        result = self.service.apply(
            [self.package],
            DictTargetLoader({}),
            executor,
            {},
            {self.key: None},
        )

        self.assertEqual(result.summary, {"Applied": 1, "Skipped": 0})
        self.assertEqual(executor.executed[0][2], DeploymentAction.CREATE)
        self.assertEqual(executor.refreshed, [self.package])

    def test_skip_does_not_execute_or_refresh_cache(self) -> None:
        executor = FakeExecutor()
        result = self.service.apply(
            [self.package],
            DictTargetLoader({}),
            executor,
            {self.key: "Skip"},
            {self.key: None},
        )

        self.assertEqual(result.summary, {"Applied": 0, "Skipped": 1})
        self.assertEqual(executor.executed, [])
        self.assertEqual(executor.refreshed, [])

    def test_dry_run_rejects_duplicate_resource_identities(self) -> None:
        with self.assertRaises(DuplicateResourceError):
            self.service.dry_run([self.package, self.package], DictTargetLoader({}))

    def test_apply_orders_packaged_workflow_dependencies_before_workflow(self) -> None:
        workflow = WorkflowHandler().serialize(
            {
                "workflow_name": "Sales Approval",
                "document_type": "Sales Order",
                "states": [{"state": "Draft"}],
                "transitions": [
                    {"state": "Draft", "action": "Approve", "next_state": "Draft", "allowed": "Sales Approver"}
                ],
            }
        )
        state = WorkflowStateHandler().serialize({"workflow_state_name": "Draft"})
        role = RoleHandler().serialize({"role_name": "Sales Approver", "is_custom": 1})
        payloads = [workflow, state, role]
        executor = FakeExecutor()

        self.service.apply(
            payloads,
            DictTargetLoader({}),
            executor,
            {},
            {f"{payload['resource_type']}:{payload['identity']}": None for payload in payloads},
        )

        self.assertEqual(executor.executed[-1][0], "Workflow")
