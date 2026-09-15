"""Programmatic inspection of untrusted .fpack archives."""

from __future__ import annotations

from typing import BinaryIO

from frappe_config_pack.core.registry import ResourceRegistry, create_default_registry
from frappe_config_pack.utils.archive import ReadPackage, SafeArchiveReader


class PackageReader:
    """Read and validate an archive without extraction or code execution."""

    def __init__(self, registry: ResourceRegistry | None = None) -> None:
        self.registry = registry or create_default_registry()

    def read(self, source: bytes | BinaryIO) -> ReadPackage:
        return SafeArchiveReader(self.registry).read(source)
