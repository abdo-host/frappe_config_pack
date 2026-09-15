"""Extensible registry for resource-specific package behavior."""

from __future__ import annotations

from typing import TYPE_CHECKING

from frappe_config_pack.core.exceptions import UnknownResourceTypeError

if TYPE_CHECKING:
    from frappe_config_pack.handlers.base import BaseResourceHandler


class ResourceRegistry:
    """Map a resource type to exactly one handler class."""

    def __init__(self) -> None:
        self._handler_classes: dict[str, type[BaseResourceHandler]] = {}

    def register(self, resource_type: str, handler_class: type[BaseResourceHandler]) -> None:
        """Register a handler class once; duplicate registrations are mistakes."""

        if not isinstance(resource_type, str) or not resource_type.strip():
            raise ValueError("Resource type must be a non-empty string.")
        if resource_type in self._handler_classes:
            raise ValueError(f"A handler is already registered for {resource_type!r}.")
        if handler_class.resource_type != resource_type:
            raise ValueError("Handler resource_type must match the registration key.")
        self._handler_classes[resource_type] = handler_class

    def get_handler(self, resource_type: str) -> BaseResourceHandler:
        """Return a fresh handler instance for a supported resource type."""

        try:
            return self._handler_classes[resource_type]()
        except KeyError as error:
            raise UnknownResourceTypeError(f"Unsupported resource type: {resource_type!r}.") from error

    def resource_types(self) -> tuple[str, ...]:
        """Return supported resource types in a deterministic order."""

        return tuple(sorted(self._handler_classes))


def create_default_registry() -> ResourceRegistry:
    """Create the supported registry without making ERPNext a dependency."""

    from frappe_config_pack.handlers.client_script import ClientScriptHandler
    from frappe_config_pack.handlers.custom_docperm import CustomDocPermHandler
    from frappe_config_pack.handlers.custom_field import CustomFieldHandler
    from frappe_config_pack.handlers.notification import NotificationHandler
    from frappe_config_pack.handlers.print_format import PrintFormatHandler
    from frappe_config_pack.handlers.property_setter import PropertySetterHandler
    from frappe_config_pack.handlers.report import ReportHandler
    from frappe_config_pack.handlers.role import RoleHandler
    from frappe_config_pack.handlers.server_script import ServerScriptHandler
    from frappe_config_pack.handlers.workflow import WorkflowHandler
    from frappe_config_pack.handlers.workflow_state import WorkflowStateHandler

    registry = ResourceRegistry()
    registry.register(ClientScriptHandler.resource_type, ClientScriptHandler)
    registry.register(CustomDocPermHandler.resource_type, CustomDocPermHandler)
    registry.register(CustomFieldHandler.resource_type, CustomFieldHandler)
    registry.register(NotificationHandler.resource_type, NotificationHandler)
    registry.register(PropertySetterHandler.resource_type, PropertySetterHandler)
    registry.register(PrintFormatHandler.resource_type, PrintFormatHandler)
    registry.register(ReportHandler.resource_type, ReportHandler)
    registry.register(RoleHandler.resource_type, RoleHandler)
    registry.register(ServerScriptHandler.resource_type, ServerScriptHandler)
    registry.register(WorkflowHandler.resource_type, WorkflowHandler)
    registry.register(WorkflowStateHandler.resource_type, WorkflowStateHandler)
    return registry
