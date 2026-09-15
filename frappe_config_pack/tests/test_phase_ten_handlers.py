from __future__ import annotations

import unittest

from frappe_config_pack.core.exceptions import ResourceValidationError
from frappe_config_pack.handlers.custom_docperm import CustomDocPermHandler
from frappe_config_pack.handlers.notification import NotificationHandler
from frappe_config_pack.handlers.print_format import PrintFormatHandler
from frappe_config_pack.handlers.report import ReportHandler
from frappe_config_pack.handlers.server_script import ServerScriptHandler
from frappe_config_pack.services.builder import PackageBuilder, ResourceInput
from frappe_config_pack.services.preflight import PackagePreflightService, PreflightStatus, TargetEnvironment
from frappe_config_pack.services.reader import PackageReader
from frappe_config_pack.tests.helpers import manifest


class TestPhaseTenHandlers(unittest.TestCase):
	def test_custom_docperm_has_a_stable_security_rule_identity_and_dependencies(self) -> None:
		handler = CustomDocPermHandler()
		payload = handler.serialize(
			{
				"parent": "Sales Invoice",
				"role": "Release Manager",
				"permlevel": "0",
				"read": "1",
				"write": 0,
				"create": False,
				"modified": "ignored",
			}
		)

		self.assertEqual(payload["identity"], "Sales Invoice::Release Manager::0")
		self.assertEqual(payload["data"]["read"], 1)
		self.assertNotIn("modified", payload["data"])
		self.assertEqual(
			[dependency.label for dependency in handler.get_dependencies(payload)],
			["DocType:Sales Invoice", "Role:Release Manager"],
		)

	def test_server_script_is_serialized_as_text_and_requires_enabled_target_capability(self) -> None:
		handler = ServerScriptHandler()
		source = {"name": "release_api", "script_type": "API", "api_method": "release_api", "script": "frappe.response['ok'] = 1"}
		payload = handler.serialize(source)
		archive = PackageBuilder().build(manifest({"Server Script": 1}), [ResourceInput("Server Script", source)]).archive

		self.assertEqual(payload["data"]["script"], source["script"])
		self.assertEqual(handler.required_capabilities(payload), ("server_script_enabled",))
		self.assertEqual(
			PackagePreflightService().inspect(archive, TargetEnvironment({"frappe": "15.65.1"})).status,
			PreflightStatus.INCOMPATIBLE,
		)
		self.assertEqual(
			PackagePreflightService()
			.inspect(archive, TargetEnvironment({"frappe": "15.65.1"}, {"server_script_enabled": True}))
			.status,
			PreflightStatus.COMPATIBLE,
		)

	def test_server_script_requires_type_specific_configuration(self) -> None:
		with self.assertRaises(ResourceValidationError):
			ServerScriptHandler().serialize(
				{"name": "invalid_event", "script_type": "DocType Event", "script": "pass"}
			)

	def test_notification_discards_child_metadata_and_rejects_standard_notifications(self) -> None:
		handler = NotificationHandler()
		source = {
			"name": "Order submitted",
			"document_type": "Sales Order",
			"channel": "Email",
			"event": "Submit",
			"is_standard": "0",
			"slack_webhook_url": "https://hooks.slack.com/services/secret",
			"recipients": [
				{"receiver_by_role": "Release Manager", "idx": 2},
				{"receiver_by_document_field": "owner", "idx": 1},
			],
		}
		payload = handler.serialize(source)

		self.assertEqual(payload, handler.serialize({**source, "modified": "ignored"}))
		self.assertNotIn("idx", payload["data"]["recipients"][0])
		self.assertNotIn("slack_webhook_url", payload["data"])
		self.assertEqual(
			[dependency.label for dependency in handler.get_dependencies(payload)],
			["DocType:Sales Order", "Role:Release Manager"],
		)
		with self.assertRaises(ResourceValidationError):
			handler.serialize({**source, "is_standard": 1})

	def test_print_format_is_custom_only_and_references_its_doctype(self) -> None:
		handler = PrintFormatHandler()
		payload = handler.serialize(
			{"name": "Sales Invoice Compact", "doc_type": "Sales Invoice", "standard": "No", "html": "<h1>{{ doc.name }}</h1>"}
		)

		self.assertEqual(payload["identity"], "Sales Invoice Compact")
		self.assertEqual([dependency.label for dependency in handler.get_dependencies(payload)], ["DocType:Sales Invoice"])
		with self.assertRaises(ResourceValidationError):
			handler.serialize({"name": "Standard", "doc_type": "Sales Invoice", "standard": "Yes"})

	def test_report_normalizes_child_rows_and_declares_references(self) -> None:
		handler = ReportHandler()
		payload = handler.serialize(
			{
				"report_name": "Open Sales Orders",
				"ref_doctype": "Sales Order",
				"is_standard": "No",
				"report_type": "Query Report",
				"roles": [{"role": "Release Manager", "idx": 3}],
				"filters": [{"label": "Company", "fieldname": "company", "fieldtype": "Link", "mandatory": "1", "idx": 1}],
				"columns": [{"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "idx": 1}],
			}
		)

		self.assertEqual(payload["data"]["filters"][0]["mandatory"], 1)
		self.assertNotIn("idx", payload["data"]["roles"][0])
		self.assertEqual(
			[dependency.label for dependency in handler.get_dependencies(payload)],
			["DocType:Sales Order", "Role:Release Manager"],
		)
		with self.assertRaises(ResourceValidationError):
			handler.serialize({**payload["data"], "is_standard": "Yes"})

	def test_all_phase_ten_handlers_round_trip_through_a_package(self) -> None:
		resources = [
			ResourceInput(
				"Custom DocPerm",
				{"parent": "Sales Invoice", "role": "Release Manager", "permlevel": 0, "read": 1},
			),
			ResourceInput(
				"Server Script",
				{
					"name": "release_api",
					"script_type": "API",
					"api_method": "release_api",
					"script": "frappe.response['ok'] = 1",
				},
			),
			ResourceInput(
				"Notification",
				{
					"name": "Sales Invoice submitted",
					"document_type": "Sales Invoice",
					"channel": "Email",
					"event": "Submit",
					"is_standard": 0,
					"recipients": [],
				},
			),
			ResourceInput(
				"Print Format",
				{"name": "Sales Invoice Compact", "doc_type": "Sales Invoice", "standard": "No"},
			),
			ResourceInput(
				"Report",
				{
					"report_name": "Open Sales Orders",
					"ref_doctype": "Sales Order",
					"is_standard": "No",
					"report_type": "Query Report",
				},
			),
		]
		built = PackageBuilder().build(
			manifest(
				{
					"Custom DocPerm": 1,
					"Server Script": 1,
					"Notification": 1,
					"Print Format": 1,
					"Report": 1,
				}
			),
			resources,
		)
		package = PackageReader().read(built.archive)

		self.assertEqual({payload["resource_type"] for payload in package.resources}, {item.resource_type for item in resources})
		self.assertEqual(len(package.resources), len(resources))
