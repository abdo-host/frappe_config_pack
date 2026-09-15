"""Semantic-version compatibility checks for package preflight."""

from __future__ import annotations

from dataclasses import dataclass

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version


@dataclass(frozen=True)
class VersionCompatibility:
	"""The result of comparing one installed app version to one constraint."""

	actual_version: str | None
	constraint: str
	satisfied: bool
	reason: str | None = None


def check_version_compatibility(actual_version: str | None, constraint: str) -> VersionCompatibility:
	"""Compare versions semantically, never with a lexical string comparison."""

	if not isinstance(constraint, str) or not constraint.strip():
		return VersionCompatibility(actual_version, str(constraint), False, "The version constraint is empty.")
	try:
		specifiers = SpecifierSet(constraint)
	except InvalidSpecifier:
		return VersionCompatibility(actual_version, constraint, False, "The version constraint is invalid.")
	if not actual_version:
		return VersionCompatibility(None, constraint, False, "The installed app version is unavailable.")
	try:
		version = Version(actual_version)
	except InvalidVersion:
		return VersionCompatibility(actual_version, constraint, False, "The installed app version is invalid.")
	if version not in specifiers:
		return VersionCompatibility(actual_version, constraint, False, "The installed version does not satisfy the constraint.")
	return VersionCompatibility(actual_version, constraint, True)
