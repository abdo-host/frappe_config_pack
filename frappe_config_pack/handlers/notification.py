"""Deterministic Notification handler without bundling related credentials."""

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


class NotificationHandler(BaseResourceHandler):
	"""Package custom notifications while leaving credentials on the target site."""

	resource_type = "Notification"
	archive_directory = "notifications"
	managed_fields = frozenset(
		{
			"name",
			"enabled",
			"channel",
			"subject",
			"document_type",
			"event",
			"method",
			"date_changed",
			"days_in_advance",
			"value_changed",
			"sender",
			"condition",
			"set_property_after_alert",
			"property_value",
			"send_to_all_assignees",
			"recipients",
			"message_type",
			"message",
			"attach_print",
			"print_format",
			"send_system_notification",
			"is_standard",
		}
	)
	boolean_fields = frozenset(
		{"enabled", "send_to_all_assignees", "attach_print", "send_system_notification", "is_standard"}
	)
	recipient_fields = frozenset({"receiver_by_document_field", "receiver_by_role", "cc", "bcc", "condition"})

	def get_identity(self, document: Mapping[str, Any]) -> str:
		name = document.get("name")
		if not isinstance(name, str) or not name.strip():
			raise ResourceValidationError("Notification requires its stable document name.")
		return name

	def normalize(self, data: Mapping[str, Any]) -> dict[str, Any]:
		if not isinstance(data, Mapping):
			raise ResourceValidationError("Notification data must be an object.")
		result = selected_fields(data, self.managed_fields)
		for field in self.boolean_fields.intersection(result):
			result[field] = as_frappe_boolean(result[field], field)
		self.get_identity(result)
		if result.get("is_standard", 0) != 0:
			raise ResourceValidationError("Standard Notifications are not packageable by default.")
		if not isinstance(result.get("document_type"), str) or not result["document_type"].strip():
			raise ResourceValidationError("Notification requires document_type.")
		if not isinstance(result.get("channel"), str) or not result["channel"].strip():
			raise ResourceValidationError("Notification requires channel.")
		if not isinstance(result.get("event"), str) or not result["event"].strip():
			raise ResourceValidationError("Notification requires event.")
		result["recipients"] = normalize_child_rows(
			result.get("recipients"), self.recipient_fields, label="Notification recipients"
		)
		return dict(sorted(result.items()))

	def archive_path(self, payload: Mapping[str, Any]) -> str:
		identity = payload["identity"]
		return f"resources/{self.archive_directory}/{archive_component(identity)}--{identity_suffix(identity)}.json"

	def get_dependencies(self, payload: Mapping[str, Any], context: Any = None) -> list[Dependency]:
		data = payload["data"]
		dependencies: set[Dependency] = {
			Dependency.doctype(data["document_type"], "Notification document type")
		}
		for recipient in data["recipients"]:
			role = recipient.get("receiver_by_role")
			if isinstance(role, str) and role.strip():
				dependencies.add(Dependency.resource("Role", role, "Notification recipient role"))
		print_format = data.get("print_format")
		if isinstance(print_format, str) and print_format.strip():
			dependencies.add(Dependency.resource("Print Format", print_format, "Notification print format"))
		return sorted(dependencies)

	def get_target(self, identity: str, context: Any = None) -> dict[str, Any] | None:
		if self.get_identity({"name": identity}) != identity:
			raise ResourceValidationError("Notification target identity is invalid.")
		return get_document_by_filters(self.resource_type, {"name": identity})

	def list_resources(
		self, filters: Mapping[str, Any] | None = None, *, start: int = 0, page_length: int = 20
	) -> list[dict[str, Any]]:
		start, page_length = validated_page(start, page_length)
		filters = {**dict(filters or {}), "is_standard": 0}
		query = filters.pop("query", "")
		reference_doctype = filters.pop("reference_doctype", None)
		if reference_doctype:
			filters["document_type"] = reference_doctype
		return get_frappe().get_all(
			self.resource_type,
			filters=filters,
			or_filters={"name": ["like", f"%{query}%"]} if query else None,
			fields=["name", "document_type", "event", "channel", "enabled"],
			order_by="modified desc, name asc",
			start=start,
			page_length=page_length,
		)
