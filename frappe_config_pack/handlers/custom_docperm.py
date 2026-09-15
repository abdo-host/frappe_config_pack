"""Deterministic, security-conscious handling for Custom DocPerm records."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from frappe_config_pack.core.dependencies import Dependency
from frappe_config_pack.core.exceptions import ResourceValidationError
from frappe_config_pack.handlers._frappe import get_document_by_filters, get_frappe, validated_page
from frappe_config_pack.handlers._normalization import as_frappe_boolean, selected_fields
from frappe_config_pack.handlers._paths import archive_component, identity_suffix
from frappe_config_pack.handlers.base import BaseResourceHandler


class CustomDocPermHandler(BaseResourceHandler):
	"""Package explicit custom permission rules, never inferred standard permissions."""

	resource_type = "Custom DocPerm"
	archive_directory = "custom_docperms"
	managed_fields = frozenset(
		{
			"parent",
			"role",
			"permlevel",
			"if_owner",
			"select",
			"read",
			"write",
			"create",
			"delete",
			"submit",
			"cancel",
			"amend",
			"report",
			"export",
			"import",
			"share",
			"print",
			"email",
		}
	)
	boolean_fields = managed_fields - {"parent", "role", "permlevel"}

	def get_identity(self, document: Mapping[str, Any]) -> str:
		parent, role, permlevel = document.get("parent"), document.get("role"), document.get("permlevel")
		if not isinstance(parent, str) or not parent.strip():
			raise ResourceValidationError("Custom DocPerm requires a parent DocType.")
		if not isinstance(role, str) or not role.strip():
			raise ResourceValidationError("Custom DocPerm requires a Role.")
		if not isinstance(permlevel, int) or permlevel < 0:
			raise ResourceValidationError("Custom DocPerm permlevel must be a non-negative integer.")
		return f"{parent}::{role}::{permlevel}"

	def normalize(self, data: Mapping[str, Any]) -> dict[str, Any]:
		if not isinstance(data, Mapping):
			raise ResourceValidationError("Custom DocPerm data must be an object.")
		result = selected_fields(data, self.managed_fields)
		for field in self.boolean_fields.intersection(result):
			result[field] = as_frappe_boolean(result[field], field)
		if isinstance(result.get("permlevel"), str) and result["permlevel"].isdigit():
			result["permlevel"] = int(result["permlevel"])
		self.get_identity(result)
		return dict(sorted(result.items()))

	def archive_path(self, payload: Mapping[str, Any]) -> str:
		data, identity = payload["data"], payload["identity"]
		return (
			f"resources/{self.archive_directory}/{archive_component(data['parent'])}/"
			f"{archive_component(data['role'])}-{data['permlevel']}--{identity_suffix(identity)}.json"
		)

	def get_dependencies(self, payload: Mapping[str, Any], context: Any = None) -> list[Dependency]:
		data = payload["data"]
		return [
			Dependency.doctype(data["parent"], "Custom DocPerm parent DocType"),
			Dependency.resource("Role", data["role"], "Custom DocPerm Role"),
		]

	def get_target(self, identity: str, context: Any = None) -> dict[str, Any] | None:
		parent, separator, remaining = identity.partition("::")
		role, separator_two, permlevel = remaining.rpartition("::")
		if not separator or not separator_two or not permlevel.isdigit():
			raise ResourceValidationError("Custom DocPerm target identity is invalid.")
		data = {"parent": parent, "role": role, "permlevel": int(permlevel)}
		if self.get_identity(data) != identity:
			raise ResourceValidationError("Custom DocPerm target identity is invalid.")
		return get_document_by_filters(self.resource_type, data)

	def list_resources(
		self, filters: Mapping[str, Any] | None = None, *, start: int = 0, page_length: int = 20
	) -> list[dict[str, Any]]:
		start, page_length = validated_page(start, page_length)
		filters = dict(filters or {})
		query = filters.pop("query", "")
		reference_doctype = filters.pop("reference_doctype", None)
		if reference_doctype:
			filters["parent"] = reference_doctype
		frappe = get_frappe()
		rows = frappe.get_all(
			self.resource_type,
			filters=filters,
			or_filters={"parent": ["like", f"%{query}%"]} if query else None,
			fields=["name", "parent", "role", "permlevel", "read", "write", "create", "delete"],
			order_by="parent asc, role asc, permlevel asc",
			start=start,
			page_length=page_length,
		)
		for row in rows:
			row["label"] = f"{row['parent']} · {row['role']} · Level {row['permlevel']}"
		return rows
