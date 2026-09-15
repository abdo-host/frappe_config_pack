"""Source-side package definition; no target-site operation belongs here."""

from __future__ import annotations

import re

from frappe.model.document import Document


class ConfigPack(Document):
    """Keep basic package metadata valid before it reaches the builder service."""

    def validate(self) -> None:
        self.resource_count = sum(1 for row in self.resources if row.selected)
        if self.slug and not re.fullmatch(r"[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?", self.slug):
            self.throw("Slug may contain only lowercase letters, numbers, and hyphens.")
        if self.version and not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?", self.version):
            self.throw("Version must use semantic versioning, for example 1.0.0.")
