"""Deterministic handler for custom Frappe Reports and their child definitions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from frappe_config_pack.core.dependencies import Dependency
from frappe_config_pack.core.exceptions import ResourceValidationError
from frappe_config_pack.handlers._frappe import get_document_by_filters, get_frappe, validated_page
from frappe_config_pack.handlers._normalization import (
	as_frappe_boolean,
	normalize_child_rows,
	selected_fields,
)
from frappe_config_pack.handlers._paths import archive_component, identity_suffix
from frappe_config_pack.handlers.base import BaseResourceHandler


class ReportHandler(BaseResourceHandler):
	"""Package non-standard report definitions, not generated report output or data."""

	resource_type = "Report"
	archive_directory = "reports"
	managed_fields = frozenset(
		{
			"report_name",
			"ref_doctype",
			"reference_report",
			"is_standard",
			"report_type",
			"letter_head",
			"add_total_row",
			"disabled",
			"prepared_report",
			"add_translate_data",
			"timeout",
			"query",
			"report_script",
			"javascript",
			"json",
			"roles",
			"filters",
			"columns",
		}
	)
	boolean_fields = frozenset({"add_total_row", "disabled", "prepared_report", "add_translate_data"})
	role_fields = frozenset({"role"})
	filter_fields = frozenset(
		{"label", "fieldtype", "fieldname", "mandatory", "wildcard_filter", "options", "default"}
	)
	filter_boolean_fields = frozenset({"mandatory", "wildcard_filter"})
	column_fields = frozenset({"fieldname", "label", "fieldtype", "options", "width"})

	def get_identity(self, document: Mapping[str, Any]) -> str:
		report_name = document.get("report_name")
		if not isinstance(report_name, str) or not report_name.strip():
			raise ResourceValidationError("Report requires report_name.")
		return report_name

	def normalize(self, data: Mapping[str, Any]) -> dict[str, Any]:
		if not isinstance(data, Mapping):
			raise ResourceValidationError("Report data must be an object.")
		result = selected_fields(data, self.managed_fields)
		for field in self.boolean_fields.intersection(result):
			result[field] = as_frappe_boolean(result[field], field)
		self.get_identity(result)
		if result.get("is_standard") != "No":
			raise ResourceValidationError("Only custom Reports with is_standard set to 'No' are packageable.")
		if not isinstance(result.get("ref_doctype"), str) or not result["ref_doctype"].strip():
			raise ResourceValidationError("Report requires ref_doctype.")
		if not isinstance(result.get("report_type"), str) or not result["report_type"].strip():
			raise ResourceValidationError("Report requires report_type.")
		result["roles"] = normalize_child_rows(result.get("roles"), self.role_fields, label="Report roles")
		result["filters"] = normalize_child_rows(
			result.get("filters"),
			self.filter_fields,
			boolean_fields=self.filter_boolean_fields,
			label="Report filters",
		)
		result["columns"] = normalize_child_rows(result.get("columns"), self.column_fields, label="Report columns")
		return dict(sorted(result.items()))

	def archive_path(self, payload: Mapping[str, Any]) -> str:
		data, identity = payload["data"], payload["identity"]
		return (
			f"resources/{self.archive_directory}/{archive_component(data['ref_doctype'])}/"
			f"{archive_component(identity)}--{identity_suffix(identity)}.json"
		)

	def get_dependencies(self, payload: Mapping[str, Any], context: Any = None) -> list[Dependency]:
		data = payload["data"]
		dependencies: set[Dependency] = {Dependency.doctype(data["ref_doctype"], "Report reference DocType")}
		for row in data["roles"]:
			role = row.get("role")
			if isinstance(role, str) and role.strip():
				dependencies.add(Dependency.resource("Role", role, "Report role"))
		reference_report = data.get("reference_report")
		if isinstance(reference_report, str) and reference_report.strip():
			dependencies.add(Dependency.resource("Report", reference_report, "Reference report"))
		return sorted(dependencies)

	def get_target(self, identity: str, context: Any = None) -> dict[str, Any] | None:
		if self.get_identity({"report_name": identity}) != identity:
			raise ResourceValidationError("Report target identity is invalid.")
		return get_document_by_filters(self.resource_type, {"report_name": identity})

	def list_resources(
		self, filters: Mapping[str, Any] | None = None, *, start: int = 0, page_length: int = 20
	) -> list[dict[str, Any]]:
		start, page_length = validated_page(start, page_length)
		filters = {**dict(filters or {}), "is_standard": "No"}
		query = filters.pop("query", "")
		reference_doctype = filters.pop("reference_doctype", None)
		if reference_doctype:
			filters["ref_doctype"] = reference_doctype
		return get_frappe().get_all(
			self.resource_type,
			filters=filters,
			or_filters={"report_name": ["like", f"%{query}%"]} if query else None,
			fields=["name", "report_name", "ref_doctype", "report_type", "disabled"],
			order_by="modified desc, report_name asc",
			start=start,
			page_length=page_length,
		)
