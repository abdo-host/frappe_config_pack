from __future__ import annotations

import pytest

from frappe_config_pack.commands import _parse_assignments, commands, config_pack


def test_config_pack_group_exposes_the_documented_lifecycle_commands() -> None:
	assert commands == [config_pack]
	assert set(config_pack.commands) == {
		"list",
		"build",
		"export",
		"inspect",
		"diff",
		"apply",
		"drift",
		"rollback",
	}


def test_parse_assignments_preserves_explicit_empty_checksum() -> None:
	assert _parse_assignments(("Custom Field:Item.example=",), "expected checksum", allow_empty_value=True) == {
		"Custom Field:Item.example": None
	}


@pytest.mark.parametrize("value", ["no-separator", "=missing-key", "key="])
def test_parse_assignments_rejects_ambiguous_values(value: str) -> None:
	with pytest.raises(Exception):
		_parse_assignments((value,), "selection")


def test_parse_assignments_rejects_duplicate_resource_keys() -> None:
	with pytest.raises(Exception):
		_parse_assignments(("Custom Field:Item.example=Skip", "Custom Field:Item.example=Safe Update"), "selection")
