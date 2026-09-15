from __future__ import annotations

import unittest

from frappe_config_pack.handlers.custom_field import CustomFieldHandler
from frappe_config_pack.handlers.role import RoleHandler
from frappe_config_pack.handlers.workflow import WorkflowHandler
from frappe_config_pack.handlers.workflow_state import WorkflowStateHandler
from frappe_config_pack.services.dependency_engine import DependencyEngine, resource_key
from frappe_config_pack.tests.helpers import custom_field


class DependencyTarget:
    def __init__(self, resources: set[str] | None = None, doctypes: set[str] | None = None) -> None:
        self.resources = resources or set()
        self.doctypes = doctypes or set()

    def resource_exists(self, resource_type: str, identity: str) -> bool:
        return resource_key(resource_type, identity) in self.resources

    def doctype_exists(self, doctype: str) -> bool:
        return doctype in self.doctypes


class TestDependencyEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = DependencyEngine()
        self.workflow = WorkflowHandler().serialize(
            {
                "workflow_name": "Sales Approval",
                "document_type": "Sales Order",
                "states": [{"state": "Draft"}, {"state": "Approved"}],
                "transitions": [{"state": "Draft", "action": "Approve", "next_state": "Approved", "allowed": "Sales Approver"}],
            }
        )

    def test_workflow_dependencies_are_explicit_and_deterministic(self) -> None:
        dependencies = self.engine.dependencies_for(self.workflow)

        self.assertEqual(
            [dependency.label for dependency in dependencies],
            ["DocType:Sales Order", "Role:Sales Approver", "Workflow State:Approved", "Workflow State:Draft"],
        )

    def test_target_report_accepts_dependencies_in_same_package(self) -> None:
        state = WorkflowStateHandler().serialize({"workflow_state_name": "Draft"})
        approved = WorkflowStateHandler().serialize({"workflow_state_name": "Approved"})
        role = RoleHandler().serialize({"role_name": "Sales Approver", "is_custom": 1})

        report = self.engine.report_for_target(
            [self.workflow, state, approved, role], DependencyTarget(doctypes={"Sales Order"})
        )

        self.assertEqual(report.missing, ())

    def test_missing_target_dependency_is_reported(self) -> None:
        report = self.engine.report_for_target([self.workflow], DependencyTarget())

        self.assertEqual(
            [dependency.label for dependency in report.missing],
            ["DocType:Sales Order", "Role:Sales Approver", "Workflow State:Approved", "Workflow State:Draft"],
        )

    def test_custom_field_link_and_table_dependencies_reference_option_doctype(self) -> None:
        link = CustomFieldHandler().serialize({**custom_field(), "fieldtype": "Link", "options": "Branch"})
        table = CustomFieldHandler().serialize({**custom_field(), "fieldname": "custom_lines", "fieldtype": "Table", "options": "Sales Order Item"})

        self.assertEqual([dependency.label for dependency in self.engine.dependencies_for(link)], ["DocType:Branch"])
        self.assertEqual(
            [dependency.label for dependency in self.engine.dependencies_for(table)], ["DocType:Sales Order Item"]
        )

    def test_apply_order_places_packaged_dependencies_before_workflow(self) -> None:
        state = WorkflowStateHandler().serialize({"workflow_state_name": "Draft"})
        role = RoleHandler().serialize({"role_name": "Sales Approver", "is_custom": 1})
        ordered = self.engine.ordered_payloads([self.workflow, state, role])

        self.assertEqual(ordered[-1]["resource_type"], "Workflow")
