"""Canonical JSON representation used for deterministic package content."""

from __future__ import annotations

import json
from typing import Any


def stable_json_dumps(value: Any) -> str:
    """Return canonical UTF-8-safe JSON independent of insertion order or formatting."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def stable_json_bytes(value: Any) -> bytes:
    """Encode canonical JSON as UTF-8 bytes."""

    return stable_json_dumps(value).encode("utf-8")
