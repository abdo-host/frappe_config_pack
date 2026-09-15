from frappe.model.document import Document

from frappe_config_pack.core.registry import create_default_registry


class ConfigPackResource(Document):
    """Reject table rows whose type has no registered export handler."""

    def validate(self) -> None:
        create_default_registry().get_handler(self.resource_type)
