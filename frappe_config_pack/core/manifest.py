"""Validation for the versioned, JSON-based .fpack manifest."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from frappe_config_pack.core.constants import FORMAT_VERSION
from frappe_config_pack.core.exceptions import ManifestValidationError, UnsupportedFormatError

SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?$")
REQUIRED_FIELDS = frozenset(
    {
        "format_version",
        "name",
        "slug",
        "version",
        "description",
        "author",
        "created_at",
        "generator",
        "compatibility",
        "required_apps",
        "resources",
        "total_resources",
    }
)


def validate_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and copy a manifest without changing the source object."""

    if not isinstance(manifest, Mapping):
        raise ManifestValidationError("Manifest must be a JSON object.")
    missing = REQUIRED_FIELDS.difference(manifest)
    if missing:
        raise ManifestValidationError(f"Manifest is missing required fields: {', '.join(sorted(missing))}.")

    result = dict(manifest)
    if result["format_version"] != FORMAT_VERSION:
        raise UnsupportedFormatError(
            f"Unsupported package format {result['format_version']!r}; expected {FORMAT_VERSION!r}."
        )
    for field in ("name", "description", "author", "created_at"):
        if not isinstance(result[field], str) or not result[field].strip():
            raise ManifestValidationError(f"Manifest field {field!r} must be a non-empty string.")
    if not isinstance(result["slug"], str) or not SLUG_RE.fullmatch(result["slug"]):
        raise ManifestValidationError("Manifest slug must use lowercase letters, numbers, and hyphens.")
    if not isinstance(result["version"], str) or not SEMVER_RE.fullmatch(result["version"]):
        raise ManifestValidationError("Manifest version must be valid semantic versioning (MAJOR.MINOR.PATCH).")
    _validate_datetime(result["created_at"])
    _validate_generator(result["generator"])
    _validate_compatibility(result["compatibility"])
    _validate_required_apps(result["required_apps"])
    _validate_resource_counts(result["resources"], result["total_resources"])
    return result


def _validate_datetime(value: str) -> None:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ManifestValidationError("Manifest created_at must be an ISO-8601 datetime.") from error


def _validate_generator(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise ManifestValidationError("Manifest generator must be an object.")
    if not all(isinstance(value.get(field), str) and value[field].strip() for field in ("app", "version")):
        raise ManifestValidationError("Manifest generator requires non-empty app and version strings.")


def _validate_compatibility(value: Any) -> None:
    if not isinstance(value, Mapping) or not isinstance(value.get("frappe"), str) or not value["frappe"].strip():
        raise ManifestValidationError("Manifest compatibility requires a non-empty frappe constraint.")
    if "erpnext" in value and value["erpnext"] is not None and not isinstance(value["erpnext"], str):
        raise ManifestValidationError("Manifest compatibility.erpnext must be a string or null.")


def _validate_required_apps(value: Any) -> None:
    if not isinstance(value, list):
        raise ManifestValidationError("Manifest required_apps must be a list.")
    seen: set[str] = set()
    for app in value:
        if not isinstance(app, Mapping) or not isinstance(app.get("app"), str) or not app["app"].strip():
            raise ManifestValidationError("Each required app requires a non-empty app name.")
        if not isinstance(app.get("version"), str) or not app["version"].strip():
            raise ManifestValidationError("Each required app requires a non-empty version constraint.")
        if app["app"] in seen:
            raise ManifestValidationError(f"Required app {app['app']!r} is duplicated.")
        seen.add(app["app"])


def _validate_resource_counts(resources: Any, total_resources: Any) -> None:
    if not isinstance(resources, Mapping) or not isinstance(total_resources, int) or isinstance(total_resources, bool):
        raise ManifestValidationError("Manifest resources and total_resources have invalid types.")
    if any(not isinstance(key, str) or not key or not isinstance(value, int) or isinstance(value, bool) or value < 0 for key, value in resources.items()):
        raise ManifestValidationError("Manifest resource counts must be non-negative integer values.")
    if sum(resources.values()) != total_resources:
        raise ManifestValidationError("Manifest total_resources does not match the resource counts.")
