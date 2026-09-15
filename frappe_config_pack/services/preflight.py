"""Read-only package import inspection and environment preflight."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, BinaryIO

from frappe_config_pack.core.compatibility import check_version_compatibility
from frappe_config_pack.core.exceptions import ConfigPackError
from frappe_config_pack.services.dependency_engine import DependencyEngine, DependencyTarget
from frappe_config_pack.services.reader import PackageReader


class PreflightStatus(str, Enum):
	COMPATIBLE = "Compatible"
	COMPATIBLE_WITH_WARNINGS = "Compatible With Warnings"
	INCOMPATIBLE = "Incompatible"


@dataclass(frozen=True)
class PreflightIssue:
	"""A user-facing preflight finding with no target-site mutation."""

	severity: str
	code: str
	message: str

	def as_dict(self) -> dict[str, str]:
		return {"severity": self.severity, "code": self.code, "message": self.message}


@dataclass(frozen=True)
class TargetEnvironment:
	"""Installed target app versions and enabled deployment capabilities."""

	app_versions: Mapping[str, str]
	capabilities: Mapping[str, bool] = field(default_factory=dict)

	def version_for(self, app: str) -> str | None:
		return self.app_versions.get(app)

	def has_capability(self, capability: str) -> bool:
		return bool(self.capabilities.get(capability))


@dataclass(frozen=True)
class PreflightResult:
	status: PreflightStatus
	issues: tuple[PreflightIssue, ...]
	package: dict[str, Any] | None
	resources: dict[str, int]

	def as_dict(self) -> dict[str, Any]:
		return {
			"status": self.status.value,
			"issues": [issue.as_dict() for issue in self.issues],
			"package": self.package,
			"resources": self.resources,
		}


class PackagePreflightService:
	"""Inspect an untrusted .fpack archive without reading or writing target records."""

	def __init__(self, reader: PackageReader | None = None) -> None:
		self.reader = reader or PackageReader()

	def inspect(
		self,
		source: bytes | BinaryIO,
		environment: TargetEnvironment,
		dependency_target: DependencyTarget | None = None,
	) -> PreflightResult:
		"""Validate the package, then compare only its declarations to target app versions."""

		try:
			package = self.reader.read(source)
		except ConfigPackError as error:
			return PreflightResult(
				PreflightStatus.INCOMPATIBLE,
				(PreflightIssue("error", "package_invalid", str(error)),),
				None,
				{},
			)

		issues = self._compatibility_issues(package.manifest, environment)
		issues.extend(self._capability_issues(package.resources, environment))
		if dependency_target:
			issues.extend(self._dependency_issues(package.resources, dependency_target))
		status = _status_for(issues)
		resource_counts = dict(sorted(Counter(resource["resource_type"] for resource in package.resources).items()))
		return PreflightResult(
			status,
			tuple(issues),
			{
				"name": package.manifest["name"],
				"slug": package.manifest["slug"],
				"version": package.manifest["version"],
				"format_version": package.manifest["format_version"],
				"package_checksum": package.package_checksum,
			},
			resource_counts,
		)

	@staticmethod
	def _dependency_issues(resources: list[dict[str, Any]], target: DependencyTarget) -> list[PreflightIssue]:
		report = DependencyEngine().report_for_target(resources, target)
		return [
			PreflightIssue("error", "missing_dependency", f"Missing dependency {dependency.label}: {dependency.reason}.")
			for dependency in report.missing
		]

	def _compatibility_issues(
		self, manifest: Mapping[str, Any], environment: TargetEnvironment
	) -> list[PreflightIssue]:
		issues: list[PreflightIssue] = []
		compatibility = manifest["compatibility"]
		self._require_version(issues, environment, "frappe", compatibility["frappe"], "frappe_compatibility")
		if compatibility.get("erpnext"):
			self._require_version(
				issues, environment, "erpnext", compatibility["erpnext"], "erpnext_compatibility"
			)
		for requirement in manifest["required_apps"]:
			self._require_version(
				issues,
				environment,
				requirement["app"],
				requirement["version"],
				"required_app",
			)
		self._generator_warning(issues, manifest, environment)
		return issues

	def _capability_issues(
		self, resources: list[dict[str, Any]], environment: TargetEnvironment
	) -> list[PreflightIssue]:
		issues: list[PreflightIssue] = []
		for payload in resources:
			handler = self.reader.registry.get_handler(payload["resource_type"])
			for capability in handler.required_capabilities(payload):
				if environment.has_capability(capability):
					continue
				issues.append(
					PreflightIssue(
						"error",
						f"required_capability_{capability}",
						f"Resource {payload['resource_type']}:{payload['identity']} requires target capability {capability!r}.",
					)
				)
		return issues

	@staticmethod
	def _require_version(
		issues: list[PreflightIssue],
		environment: TargetEnvironment,
		app: str,
		constraint: str,
		code_prefix: str,
	) -> None:
		actual = environment.version_for(app)
		result = check_version_compatibility(actual, constraint)
		if result.satisfied:
			return
		if actual is None:
			message = f"Required app {app!r} is not installed on the target site."
		else:
			message = (
				f"App {app!r} version {actual!r} does not satisfy {constraint!r}: {result.reason}"
			)
		issues.append(PreflightIssue("error", code_prefix, message))

	@staticmethod
	def _generator_warning(
		issues: list[PreflightIssue], manifest: Mapping[str, Any], environment: TargetEnvironment
	) -> None:
		generator = manifest["generator"]
		target_version = environment.version_for(generator["app"])
		if target_version and target_version != generator["version"]:
			issues.append(
				PreflightIssue(
					"warning",
					"generator_version_differs",
					f"Package generator {generator['app']!r} is {generator['version']!r}; "
					f"the target has {target_version!r}.",
				)
			)


def _status_for(issues: list[PreflightIssue]) -> PreflightStatus:
	if any(issue.severity == "error" for issue in issues):
		return PreflightStatus.INCOMPATIBLE
	if issues:
		return PreflightStatus.COMPATIBLE_WITH_WARNINGS
	return PreflightStatus.COMPATIBLE
