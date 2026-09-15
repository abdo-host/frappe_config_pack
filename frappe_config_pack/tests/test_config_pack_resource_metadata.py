from __future__ import annotations

import json
from pathlib import Path

from frappe_config_pack.services.resource_browser import ResourceBrowser


def test_resource_type_select_options_match_the_registered_export_handlers() -> None:
    metadata_path = (
        Path(__file__).parents[1]
        / "frappe_config_pack"
        / "doctype"
        / "config_pack_resource"
        / "config_pack_resource.json"
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    resource_type = next(field for field in metadata["fields"] if field["fieldname"] == "resource_type")

    assert resource_type["fieldtype"] == "Select"
    assert tuple(resource_type["options"].splitlines()) == ResourceBrowser().supported_resource_types()
