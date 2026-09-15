"""Checksum helpers for normalized resources and logical packages."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Any

from frappe_config_pack.core.serializer import stable_json_bytes


def checksum(value: Any) -> str:
    """Calculate a SHA-256 checksum from canonical JSON, never display formatting."""

    return sha256(stable_json_bytes(value)).hexdigest()


def resource_checksum(resource: Mapping[str, Any]) -> str:
    """Calculate the checksum of one normalized resource envelope."""

    return checksum(resource)


def package_checksum(manifest: Mapping[str, Any], resource_checksums: Mapping[str, str]) -> str:
    """Calculate a logical package checksum independent of ZIP metadata.

    ``created_at`` reflects build time, not configuration state, so it is
    deliberately excluded. ``package_checksum`` is also excluded to avoid a
    checksum cycle if a future manifest records the value.
    """

    logical_manifest = {
        key: value
        for key, value in manifest.items()
        if key not in {"created_at", "package_checksum"}
    }
    return checksum({"manifest": logical_manifest, "resource_checksums": dict(resource_checksums)})
