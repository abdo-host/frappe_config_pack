"""Safe, human-readable and collision-resistant internal archive paths."""

from __future__ import annotations

import re
from hashlib import sha256

_UNSAFE = re.compile(r"[^a-z0-9]+")


def archive_component(value: str) -> str:
    """Convert an identity fragment into a predictable safe path component."""

    component = _UNSAFE.sub("-", value.lower()).strip("-") or "resource"
    return component[:70]


def identity_suffix(identity: str) -> str:
    """Prevent collisions from normalization/case folding while keeping names legible."""

    return sha256(identity.encode("utf-8")).hexdigest()[:12]
