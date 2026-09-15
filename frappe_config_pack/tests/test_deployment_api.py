from __future__ import annotations

import unittest

from frappe_config_pack.api.deployment import _SavepointGuard


class MissingSavepointError(Exception):
    def __init__(self) -> None:
        super().__init__(1305, "SAVEPOINT config_pack_apply_test does not exist")


class RecordingDatabase:
    def __init__(self, *, missing_on: str | None = None) -> None:
        self.missing_on = missing_on
        self.calls: list[tuple[str, str | None]] = []

    def savepoint(self, name: str) -> None:
        self.calls.append(("savepoint", name))

    def release_savepoint(self, name: str) -> None:
        self.calls.append(("release", name))
        if self.missing_on == "release":
            raise MissingSavepointError()

    def rollback(self, *, save_point: str) -> None:
        self.calls.append(("rollback", save_point))
        if self.missing_on == "rollback":
            raise MissingSavepointError()


class TestSavepointGuard(unittest.TestCase):
    def test_release_ignores_only_ddl_discarded_savepoint(self) -> None:
        database = RecordingDatabase(missing_on="release")
        guard = _SavepointGuard(database, "config_pack_apply_test")

        guard.begin()
        guard.release()

        self.assertEqual(
            database.calls,
            [("savepoint", "config_pack_apply_test"), ("release", "config_pack_apply_test")],
        )
        self.assertFalse(guard.active)

    def test_rollback_ignores_only_ddl_discarded_savepoint(self) -> None:
        database = RecordingDatabase(missing_on="rollback")
        guard = _SavepointGuard(database, "config_pack_apply_test")

        guard.begin()
        guard.rollback()

        self.assertEqual(
            database.calls,
            [("savepoint", "config_pack_apply_test"), ("rollback", "config_pack_apply_test")],
        )
        self.assertFalse(guard.active)
