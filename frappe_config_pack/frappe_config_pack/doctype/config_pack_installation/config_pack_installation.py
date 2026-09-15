from frappe.model.document import Document


class ConfigPackInstallation(Document):
    """Immutable deployment-history record, updated only by the installation service."""

