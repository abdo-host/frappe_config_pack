"""Typed, deterministic dependency references emitted by resource handlers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DependencyKind(str, Enum):
    RESOURCE = "Resource"
    DOCTYPE = "DocType"


@dataclass(frozen=True, order=True)
class Dependency:
    """A packageable resource or a required target DocType."""

    kind: DependencyKind
    resource_type: str
    identity: str
    reason: str

    @classmethod
    def resource(cls, resource_type: str, identity: str, reason: str) -> Dependency:
        return cls(DependencyKind.RESOURCE, resource_type, identity, reason)

    @classmethod
    def doctype(cls, doctype: str, reason: str) -> Dependency:
        return cls(DependencyKind.DOCTYPE, "DocType", doctype, reason)

    @property
    def key(self) -> str:
        return f"{self.resource_type}:{self.identity}"

    @property
    def label(self) -> str:
        return self.key
