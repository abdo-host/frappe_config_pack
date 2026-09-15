"""Read-only configuration drift detection for installed Config Pack releases."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from frappe_config_pack.core.checksums import resource_checksum
from frappe_config_pack.core.exceptions import ConfigPackError
from frappe_config_pack.services.diff_engine import TargetLoader


class DriftStatus(str, Enum):
    CLEAN = "Clean"
    MODIFIED = "Modified"
    MISSING = "Missing"


@dataclass(frozen=True)
class DriftResource:
    """One installed resource compared with its current target state."""

    resource_type: str
    identity: str
    status: DriftStatus
    installed_checksum: str
    current_checksum: str | None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "resource_type": self.resource_type,
            "identity": self.identity,
            "status": self.status.value,
            "installed_checksum": self.installed_checksum,
            "current_checksum": self.current_checksum,
        }


@dataclass(frozen=True)
class DriftReport:
    """Deterministic health report for a single installed release."""

    resources: tuple[DriftResource, ...]

    @property
    def summary(self) -> dict[str, int]:
        counts = Counter(resource.status.value for resource in self.resources)
        return {status.value: counts.get(status.value, 0) for status in DriftStatus}

    @property
    def healthy(self) -> bool:
        return not self.summary[DriftStatus.MODIFIED.value] and not self.summary[DriftStatus.MISSING.value]

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "healthy": self.healthy,
            "resources": [resource.as_dict() for resource in self.resources],
        }


class DriftService:
    """Compare stored installation checksums with the current target without correcting anything."""

    def check(self, installed_checksums: Mapping[str, str], target_loader: TargetLoader) -> DriftReport:
        resources = [
            self._check_resource(key, installed_checksum, target_loader)
            for key, installed_checksum in installed_checksums.items()
        ]
        return DriftReport(tuple(sorted(resources, key=lambda item: (item.resource_type, item.identity))))

    @staticmethod
    def _check_resource(
        key: str,
        installed_checksum: str,
        target_loader: TargetLoader,
    ) -> DriftResource:
        resource_type, separator, identity = key.partition(":")
        if not separator or not resource_type or not identity:
            raise ConfigPackError(f"Installed resource checksum key {key!r} is invalid.")
        current = target_loader.load(resource_type, identity)
        if current is None:
            return DriftResource(resource_type, identity, DriftStatus.MISSING, installed_checksum, None)
        current_checksum = resource_checksum(current)
        status = DriftStatus.CLEAN if current_checksum == installed_checksum else DriftStatus.MODIFIED
        return DriftResource(resource_type, identity, status, installed_checksum, current_checksum)
