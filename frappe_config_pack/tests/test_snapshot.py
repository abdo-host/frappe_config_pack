from __future__ import annotations

import unittest

from frappe_config_pack.core.checksums import resource_checksum
from frappe_config_pack.handlers.custom_field import CustomFieldHandler
from frappe_config_pack.services.deployment import DeploymentService
from frappe_config_pack.services.snapshot import (
    RollbackAction,
    RollbackService,
    SnapshotService,
    resource_key,
)
from frappe_config_pack.tests.helpers import custom_field


class DictTargetLoader:
    def __init__(self, resources: dict[tuple[str, str], dict]) -> None:
        self.resources = resources

    def load(self, resource_type: str, identity: str) -> dict | None:
        return self.resources.get((resource_type, identity))


class RecordingRollbackExecutor:
    def __init__(self) -> None:
        self.restored: list[dict] = []
        self.deleted: list[tuple[str, str]] = []
        self.refreshed: list[object] = []

    def restore(self, payload: dict) -> None:
        self.restored.append(payload)

    def delete(self, resource_type: str, identity: str) -> None:
        self.deleted.append((resource_type, identity))

    def refresh_caches(self, items: object) -> None:
        self.refreshed = list(items)


class TestSnapshotAndRollback(unittest.TestCase):
    def setUp(self) -> None:
        self.handler = CustomFieldHandler()
        self.package = self.handler.serialize(custom_field())
        self.key = resource_key(self.package["resource_type"], self.package["identity"])

    def test_snapshot_records_missing_target_for_a_created_resource(self) -> None:
        plan = DeploymentService().dry_run([self.package], DictTargetLoader({}))

        snapshot = SnapshotService().capture([self.package], plan, DictTargetLoader({}))

        self.assertEqual(snapshot.items[0].resource_type, "Custom Field")
        self.assertFalse(snapshot.items[0].existed_before)
        self.assertIsNone(snapshot.items[0].serialized_state)
        self.assertIsNone(snapshot.items[0].checksum)

    def test_snapshot_captures_normalized_pre_install_state_for_safe_update(self) -> None:
        target = self.handler.serialize({**custom_field(), "label": "Legacy Branch"})
        loader = DictTargetLoader({(self.package["resource_type"], self.package["identity"]): target})
        plan = DeploymentService().dry_run([self.package], loader, {self.key: "Safe Update"})

        snapshot = SnapshotService().capture([self.package], plan, loader)

        self.assertTrue(snapshot.items[0].existed_before)
        self.assertEqual(snapshot.items[0].serialized_state, target)
        self.assertEqual(snapshot.items[0].checksum, resource_checksum(target))

    def test_rollback_restores_previous_state_when_target_still_matches_installation(self) -> None:
        target = self.handler.serialize({**custom_field(), "label": "Legacy Branch"})
        loader = DictTargetLoader({(self.package["resource_type"], self.package["identity"]): target})
        plan = DeploymentService().dry_run([self.package], loader, {self.key: "Safe Update"})
        snapshot = SnapshotService().capture([self.package], plan, loader)
        installed_target = DictTargetLoader({(self.package["resource_type"], self.package["identity"]): self.package})
        rollback_plan = RollbackService().plan(snapshot, {self.key: resource_checksum(self.package)}, installed_target)
        executor = RecordingRollbackExecutor()

        result = RollbackService().execute(rollback_plan, executor)

        self.assertEqual(rollback_plan.resources[0].action, RollbackAction.RESTORE)
        self.assertEqual(rollback_plan.warnings, ())
        self.assertEqual(executor.restored, [target])
        self.assertEqual(result.summary, {"Restored": 1, "Deleted": 0, "Skipped": 0})

    def test_rollback_skips_post_install_local_change_without_force(self) -> None:
        plan = DeploymentService().dry_run([self.package], DictTargetLoader({}))
        snapshot = SnapshotService().capture([self.package], plan, DictTargetLoader({}))
        changed_target = self.handler.serialize({**custom_field(), "label": "Changed After Install"})
        loader = DictTargetLoader({(self.package["resource_type"], self.package["identity"]): changed_target})
        rollback_plan = RollbackService().plan(snapshot, {self.key: resource_checksum(self.package)}, loader)
        executor = RecordingRollbackExecutor()

        result = RollbackService().execute(rollback_plan, executor)

        self.assertEqual(len(rollback_plan.warnings), 1)
        self.assertEqual(executor.deleted, [])
        self.assertEqual(executor.refreshed, [])
        self.assertEqual(result.summary, {"Restored": 0, "Deleted": 0, "Skipped": 1})

    def test_forced_rollback_deletes_resource_created_by_installation(self) -> None:
        plan = DeploymentService().dry_run([self.package], DictTargetLoader({}))
        snapshot = SnapshotService().capture([self.package], plan, DictTargetLoader({}))
        changed_target = self.handler.serialize({**custom_field(), "label": "Changed After Install"})
        loader = DictTargetLoader({(self.package["resource_type"], self.package["identity"]): changed_target})
        rollback_plan = RollbackService().plan(snapshot, {self.key: resource_checksum(self.package)}, loader)
        executor = RecordingRollbackExecutor()

        result = RollbackService().execute(rollback_plan, executor, force=True)

        self.assertEqual(executor.deleted, [("Custom Field", self.package["identity"])])
        self.assertEqual(len(executor.refreshed), 1)
        self.assertEqual(result.summary, {"Restored": 0, "Deleted": 1, "Skipped": 0})
