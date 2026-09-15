"""Shared deterministic normalization primitives for complex resource handlers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from frappe_config_pack.core.exceptions import ResourceValidationError
from frappe_config_pack.core.serializer import stable_json_dumps


def selected_fields(data: Mapping[str, Any], fields: Iterable[str]) -> dict[str, Any]:
	"""Copy only handler-owned fields, preserving meaningful falsey values."""

	return {field: data[field] for field in fields if field in data}


def as_frappe_boolean(value: Any, field: str) -> int:
	"""Normalize Frappe Check values and reject ambiguous input."""

	if value in (True, 1, "1"):
		return 1
	if value in (False, 0, "0", None, ""):
		return 0
	raise ResourceValidationError(f"{field} must be a Frappe boolean value.")


def normalize_child_rows(
	value: Any,
	fields: Iterable[str],
	*,
	boolean_fields: Iterable[str] = (),
	label: str,
) -> list[dict[str, Any]]:
	"""Normalize unordered child tables without package-specific row metadata."""

	if value in (None, ""):
		return []
	if not isinstance(value, list):
		raise ResourceValidationError(f"{label} must be a list.")
	booleans = set(boolean_fields)
	rows: list[dict[str, Any]] = []
	for row in value:
		if not isinstance(row, Mapping):
			raise ResourceValidationError(f"{label} rows must be objects.")
		normalized = selected_fields(row, fields)
		for field in booleans.intersection(normalized):
			normalized[field] = as_frappe_boolean(normalized[field], field)
		rows.append(dict(sorted(normalized.items())))
	return sorted(rows, key=stable_json_dumps)
