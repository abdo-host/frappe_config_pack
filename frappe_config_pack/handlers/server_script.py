"""Server Script support that treats code as data and requires an enabled target."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from frappe_config_pack.core.dependencies import Dependency
from frappe_config_pack.core.exceptions import ResourceValidationError
from frappe_config_pack.handlers._frappe import get_document_by_filters, get_frappe, validated_page
from frappe_config_pack.handlers._normalization import as_frappe_boolean, selected_fields
from frappe_config_pack.handlers._paths import archive_component, identity_suffix
from frappe_config_pack.handlers.base import BaseResourceHandler


class ServerScriptHandler(BaseResourceHandler):
	"""Serialize Server Script text without executing it during package handling."""

	resource_type = "Server Script"
	archive_directory = "server_scripts"
	managed_fields = frozenset(
		{
			"name",
			"script_type",
			"script",
			"reference_doctype",
			"doctype_event",
			"api_method",
			"allow_guest",
			"disabled",
			"event_frequency",
			"cron_format",
			"enable_rate_limit",
			"rate_limit_count",
			"rate_limit_seconds",
			"module",
		}
	)
	boolean_fields = frozenset({"allow_guest", "disabled", "enable_rate_limit"})
	script_types = frozenset({"DocType Event", "Scheduler Event", "Permission Query", "API"})

	def get_identity(self, document: Mapping[str, Any]) -> str:
		name = document.get("name")
		if not isinstance(name, str) or not name.strip():
			raise ResourceValidationError("Server Script requires its stable document name.")
		return name

	def normalize(self, data: Mapping[str, Any]) -> dict[str, Any]:
		if not isinstance(data, Mapping):
			raise ResourceValidationError("Server Script data must be an object.")
		result = selected_fields(data, self.managed_fields)
		for field in self.boolean_fields.intersection(result):
			result[field] = as_frappe_boolean(result[field], field)
		self.get_identity(result)
		if result.get("script_type") not in self.script_types:
			raise ResourceValidationError("Server Script has an unsupported script_type.")
		if not isinstance(result.get("script"), str):
			raise ResourceValidationError("Server Script requires script text.")
		if result["script_type"] in {"DocType Event", "Permission Query"}:
			if not isinstance(result.get("reference_doctype"), str) or not result["reference_doctype"].strip():
				raise ResourceValidationError("This Server Script type requires reference_doctype.")
		if result["script_type"] == "DocType Event" and not isinstance(result.get("doctype_event"), str):
			raise ResourceValidationError("DocType Event Server Script requires doctype_event.")
		if result["script_type"] == "Scheduler Event" and not isinstance(result.get("event_frequency"), str):
			raise ResourceValidationError("Scheduler Event Server Script requires event_frequency.")
		if result["script_type"] == "Scheduler Event" and result.get("event_frequency") == "Cron":
			if not isinstance(result.get("cron_format"), str) or not result["cron_format"].strip():
				raise ResourceValidationError("Cron Server Script requires cron_format.")
		if result["script_type"] == "API" and not isinstance(result.get("api_method"), str):
			raise ResourceValidationError("API Server Script requires api_method.")
		return dict(sorted(result.items()))

	def archive_path(self, payload: Mapping[str, Any]) -> str:
		identity = payload["identity"]
		return f"resources/{self.archive_directory}/{archive_component(identity)}--{identity_suffix(identity)}.json"

	def get_dependencies(self, payload: Mapping[str, Any], context: Any = None) -> list[Dependency]:
		reference_doctype = payload["data"].get("reference_doctype")
		if isinstance(reference_doctype, str) and reference_doctype.strip():
			return [Dependency.doctype(reference_doctype, "Server Script reference DocType")]
		return []

	def required_capabilities(self, payload: Mapping[str, Any], context: Any = None) -> tuple[str, ...]:
		self.validate(payload, context)
		return ("server_script_enabled",)

	def get_target(self, identity: str, context: Any = None) -> dict[str, Any] | None:
		if self.get_identity({"name": identity}) != identity:
			raise ResourceValidationError("Server Script target identity is invalid.")
		return get_document_by_filters(self.resource_type, {"name": identity})

	def list_resources(
		self, filters: Mapping[str, Any] | None = None, *, start: int = 0, page_length: int = 20
	) -> list[dict[str, Any]]:
		start, page_length = validated_page(start, page_length)
		filters = dict(filters or {})
		query = filters.pop("query", "")
		reference_doctype = filters.pop("reference_doctype", None)
		if reference_doctype:
			filters["reference_doctype"] = reference_doctype
		return get_frappe().get_all(
			self.resource_type,
			filters=filters,
			or_filters={"name": ["like", f"%{query}%"]} if query else None,
			fields=["name", "script_type", "reference_doctype", "disabled"],
			order_by="modified desc, name asc",
			start=start,
			page_length=page_length,
		)
