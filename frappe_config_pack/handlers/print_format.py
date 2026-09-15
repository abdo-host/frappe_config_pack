"""Deterministic Print Format handler for custom site configuration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from frappe_config_pack.core.dependencies import Dependency
from frappe_config_pack.core.exceptions import ResourceValidationError
from frappe_config_pack.handlers._frappe import get_document_by_filters, get_frappe, validated_page
from frappe_config_pack.handlers._normalization import as_frappe_boolean, selected_fields
from frappe_config_pack.handlers._paths import archive_component, identity_suffix
from frappe_config_pack.handlers.base import BaseResourceHandler


class PrintFormatHandler(BaseResourceHandler):
	"""Package custom Print Format source and settings as data, never rendered output."""

	resource_type = "Print Format"
	archive_directory = "print_formats"
	managed_fields = frozenset(
		{
			"name",
			"doc_type",
			"disabled",
			"standard",
			"custom_format",
			"print_format_type",
			"raw_printing",
			"html",
			"raw_commands",
			"align_labels_right",
			"show_section_headings",
			"line_breaks",
			"absolute_value",
			"default_print_language",
			"font",
			"css",
			"format_data",
			"print_format_builder",
			"print_format_builder_beta",
			"margin_top",
			"margin_bottom",
			"margin_left",
			"margin_right",
			"font_size",
			"page_number",
		}
	)
	boolean_fields = frozenset(
		{
			"disabled",
			"custom_format",
			"raw_printing",
			"align_labels_right",
			"show_section_headings",
			"line_breaks",
			"absolute_value",
			"print_format_builder",
			"print_format_builder_beta",
		}
	)

	def get_identity(self, document: Mapping[str, Any]) -> str:
		name = document.get("name")
		if not isinstance(name, str) or not name.strip():
			raise ResourceValidationError("Print Format requires its stable document name.")
		return name

	def normalize(self, data: Mapping[str, Any]) -> dict[str, Any]:
		if not isinstance(data, Mapping):
			raise ResourceValidationError("Print Format data must be an object.")
		result = selected_fields(data, self.managed_fields)
		for field in self.boolean_fields.intersection(result):
			result[field] = as_frappe_boolean(result[field], field)
		self.get_identity(result)
		if result.get("standard") != "No":
			raise ResourceValidationError("Only custom Print Formats with standard set to 'No' are packageable.")
		if not isinstance(result.get("doc_type"), str) or not result["doc_type"].strip():
			raise ResourceValidationError("Print Format requires doc_type.")
		return dict(sorted(result.items()))

	def archive_path(self, payload: Mapping[str, Any]) -> str:
		data, identity = payload["data"], payload["identity"]
		return (
			f"resources/{self.archive_directory}/{archive_component(data['doc_type'])}/"
			f"{archive_component(identity)}--{identity_suffix(identity)}.json"
		)

	def get_dependencies(self, payload: Mapping[str, Any], context: Any = None) -> list[Dependency]:
		return [Dependency.doctype(payload["data"]["doc_type"], "Print Format DocType")]

	def get_target(self, identity: str, context: Any = None) -> dict[str, Any] | None:
		if self.get_identity({"name": identity}) != identity:
			raise ResourceValidationError("Print Format target identity is invalid.")
		return get_document_by_filters(self.resource_type, {"name": identity})

	def list_resources(
		self, filters: Mapping[str, Any] | None = None, *, start: int = 0, page_length: int = 20
	) -> list[dict[str, Any]]:
		start, page_length = validated_page(start, page_length)
		filters = {**dict(filters or {}), "standard": "No"}
		query = filters.pop("query", "")
		reference_doctype = filters.pop("reference_doctype", None)
		if reference_doctype:
			filters["doc_type"] = reference_doctype
		return get_frappe().get_all(
			self.resource_type,
			filters=filters,
			or_filters={"name": ["like", f"%{query}%"]} if query else None,
			fields=["name", "doc_type", "custom_format", "disabled"],
			order_by="modified desc, name asc",
			start=start,
			page_length=page_length,
		)
