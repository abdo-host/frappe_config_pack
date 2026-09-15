from __future__ import annotations

import unittest

from frappe_config_pack.services.builder import PackageBuilder, ResourceInput
from frappe_config_pack.services.preflight import (
	PackagePreflightService,
	PreflightStatus,
	TargetEnvironment,
)
from frappe_config_pack.tests.helpers import custom_field, manifest, property_setter


class DependencyTarget:
	def resource_exists(self, resource_type: str, identity: str) -> bool:
		return False

	def doctype_exists(self, doctype: str) -> bool:
		return False


class TestPackagePreflightService(unittest.TestCase):
	def setUp(self) -> None:
		self.archive = PackageBuilder().build(
			manifest(),
			[
				ResourceInput("Custom Field", custom_field()),
				ResourceInput("Property Setter", property_setter()),
			],
		).archive
		self.service = PackagePreflightService()

	def test_accepts_a_valid_package_when_target_versions_match(self) -> None:
		result = self.service.inspect(self.archive, TargetEnvironment({"frappe": "15.65.1"}))

		self.assertEqual(result.status, PreflightStatus.COMPATIBLE)
		self.assertEqual(result.resources, {"Custom Field": 1, "Property Setter": 1})
		self.assertEqual(result.issues, ())

	def test_blocks_a_missing_required_app(self) -> None:
		result = self.service.inspect(self.archive, TargetEnvironment({}))

		self.assertEqual(result.status, PreflightStatus.INCOMPATIBLE)
		self.assertTrue(any(issue.code == "frappe_compatibility" for issue in result.issues))
		self.assertTrue(any(issue.code == "required_app" for issue in result.issues))

	def test_blocks_an_incompatible_frappe_version_semantically(self) -> None:
		result = self.service.inspect(self.archive, TargetEnvironment({"frappe": "17.0.0"}))

		self.assertEqual(result.status, PreflightStatus.INCOMPATIBLE)
		self.assertTrue(any(issue.code == "frappe_compatibility" for issue in result.issues))

	def test_validates_erpnext_only_when_declared(self) -> None:
		pack_manifest = manifest()
		pack_manifest["compatibility"]["erpnext"] = ">=15,<17"
		archive = PackageBuilder().build(
			pack_manifest,
			[
				ResourceInput("Custom Field", custom_field()),
				ResourceInput("Property Setter", property_setter()),
			],
		).archive

		result = self.service.inspect(archive, TargetEnvironment({"frappe": "15.65.1"}))

		self.assertEqual(result.status, PreflightStatus.INCOMPATIBLE)
		self.assertTrue(any(issue.code == "erpnext_compatibility" for issue in result.issues))

	def test_reports_a_generator_version_difference_as_a_warning(self) -> None:
		result = self.service.inspect(
			self.archive,
			TargetEnvironment({"frappe": "15.65.1", "frappe_config_pack": "0.2.0"}),
		)

		self.assertEqual(result.status, PreflightStatus.COMPATIBLE_WITH_WARNINGS)
		self.assertTrue(any(issue.code == "generator_version_differs" for issue in result.issues))

	def test_reports_invalid_archives_as_incompatible_without_target_access(self) -> None:
		result = self.service.inspect(b"not an archive", TargetEnvironment({"frappe": "15.65.1"}))

		self.assertEqual(result.status, PreflightStatus.INCOMPATIBLE)
		self.assertEqual(result.package, None)
		self.assertEqual(result.issues[0].code, "package_invalid")

	def test_blocks_missing_custom_field_link_doctype_dependency(self) -> None:
		archive = PackageBuilder().build(
			manifest({"Custom Field": 1}),
			[ResourceInput("Custom Field", {**custom_field(), "fieldtype": "Link", "options": "Branch"})],
		).archive

		result = self.service.inspect(
			archive,
			TargetEnvironment({"frappe": "15.65.1"}),
			DependencyTarget(),
		)

		self.assertEqual(result.status, PreflightStatus.INCOMPATIBLE)
		self.assertTrue(any(issue.code == "missing_dependency" and "DocType:Branch" in issue.message for issue in result.issues))
