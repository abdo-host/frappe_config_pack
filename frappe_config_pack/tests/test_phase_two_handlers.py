from __future__ import annotations

import unittest

from frappe_config_pack.core.exceptions import ResourceValidationError
from frappe_config_pack.handlers.client_script import ClientScriptHandler
from frappe_config_pack.handlers.role import RoleHandler
from frappe_config_pack.handlers.workflow import WorkflowHandler
from frappe_config_pack.handlers.workflow_state import WorkflowStateHandler


class TestPhaseTwoHandlers(unittest.TestCase):
    def test_client_script_ignores_modified_metadata_and_normalizes_enabled(self) -> None:
        handler = ClientScriptHandler()
        source = {
            "name": "Sales Invoice Validation",
            "dt": "Sales Invoice",
            "view": "Form",
            "enabled": "1",
            "script": "frappe.ui.form.on('Sales Invoice', {});",
            "modified": "2026-09-13 00:00:00",
        }
        changed_metadata = {**source, "modified": "2030-01-01 00:00:00"}
        self.assertEqual(handler.serialize(source), handler.serialize(changed_metadata))
        self.assertEqual(handler.serialize(source)["data"]["enabled"], 1)

    def test_workflow_state_identity_is_stable(self) -> None:
        payload = WorkflowStateHandler().serialize(
            {"workflow_state_name": "Manager Review", "icon": "check", "style": "Warning", "modified": "ignored"}
        )
        self.assertEqual(payload["identity"], "Manager Review")
        self.assertNotIn("modified", payload["data"])

    def test_standard_role_is_not_packageable_by_default(self) -> None:
        with self.assertRaises(ResourceValidationError):
            RoleHandler().serialize({"role_name": "System Manager", "is_custom": 0})

    def test_custom_role_has_deterministic_output(self) -> None:
        handler = RoleHandler()
        source = {"role_name": "Release Manager", "is_custom": "1", "disabled": "0", "desk_access": 1}
        self.assertEqual(handler.serialize(source)["data"]["is_custom"], 1)
        self.assertEqual(handler.serialize(source), handler.serialize({**source, "modified": "ignored"}))

    def test_workflow_keeps_semantic_child_order_and_discards_child_metadata(self) -> None:
        handler = WorkflowHandler()
        source = {
            "workflow_name": "Sales Approval",
            "document_type": "Sales Invoice",
            "is_active": "1",
            "states": [
                {"state": "Draft", "doc_status": "0", "idx": 1, "modified": "ignored"},
                {"state": "Approved", "doc_status": "1", "idx": 2},
            ],
            "transitions": [{"state": "Draft", "action": "Approve", "next_state": "Approved", "allowed": "Release Manager", "idx": 1}],
            "modified": "ignored",
        }
        payload = handler.serialize(source)
        self.assertEqual([row["state"] for row in payload["data"]["states"]], ["Draft", "Approved"])
        self.assertNotIn("idx", payload["data"]["states"][0])
        self.assertEqual(payload["data"]["is_active"], 1)
