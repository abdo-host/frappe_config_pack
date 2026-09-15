"""Phase 2 source-site builder endpoints; deployment remains intentionally absent."""

from __future__ import annotations

from typing import Any

import frappe

from frappe_config_pack.core.registry import create_default_registry
from frappe_config_pack.services.config_pack_builder import ConfigPackBuildService
from frappe_config_pack.services.resource_browser import (
    ResourceBrowser,
    selected_resource_counts,
    selected_resource_names,
)


@frappe.whitelist()
def get_supported_resource_types() -> list[str]:
    """Return only types with registered handlers."""

    return list(ResourceBrowser().supported_resource_types())


@frappe.whitelist()
def get_config_pack_summary(config_pack: str) -> dict[str, Any]:
    """Return the selected build scope for one readable Config Pack."""

    pack = frappe.get_doc("Config Pack", config_pack)
    pack.check_permission("read")
    selected_rows = [row.as_dict() for row in pack.resources]
    selected_counts = selected_resource_counts(selected_rows)
    return {
        "name": pack.name,
        "package_name": pack.package_name,
        "version": pack.version,
        "status": pack.status,
        "selected_count": sum(selected_counts.values()),
        "selected_counts": selected_counts,
    }


@frappe.whitelist()
def search_resources(
    resource_type: str,
    query: str = "",
    reference_doctype: str | None = None,
    start: int | str = 0,
    page_length: int | str = 20,
    config_pack: str | None = None,
) -> dict[str, Any]:
    """Return a bounded source-site resource page, without changing any record."""

    response = ResourceBrowser().search(
        resource_type,
        query=query or "",
        reference_doctype=reference_doctype or None,
        start=int(start),
        page_length=int(page_length),
    )
    if config_pack:
        pack = frappe.get_doc("Config Pack", config_pack)
        pack.check_permission("read")
        selected_rows = [row.as_dict() for row in pack.resources]
        response["selected_counts"] = selected_resource_counts(selected_rows)
        response["selected_resource_names"] = selected_resource_names(selected_rows)
    else:
        response["selected_counts"] = {}
        response["selected_resource_names"] = {}
    return response


@frappe.whitelist()
def add_resource(config_pack: str, resource_type: str, resource_name: str) -> dict[str, str | bool]:
    """Add a source-derived resource selection to a draft Config Pack."""

    pack = _get_writable_pack(config_pack)
    if pack.status == "Archived":
        frappe.throw("Archived Config Packs cannot be changed.")
    handler = create_default_registry().get_handler(resource_type)
    source = frappe.get_doc(resource_type, resource_name).as_dict()
    identity = handler.serialize(source)["identity"]
    if any(row.resource_type == resource_type and row.resource_name == resource_name for row in pack.resources):
        return {"resource_identity": identity, "message": "Resource is already selected.", "already_selected": True}
    pack.append(
        "resources",
        {
            "resource_type": resource_type,
            "resource_identity": identity,
            "resource_name": resource_name,
            "reference_doctype": source.get("dt") or source.get("doc_type") or source.get("document_type"),
            "selected": 1,
            "status": "Selected",
        },
    )
    pack.status = "Draft"
    pack.save()
    return {"resource_identity": identity, "message": "Resource added to Config Pack.", "already_selected": False}


@frappe.whitelist()
def remove_resource(config_pack: str, resource_type: str, resource_name: str) -> dict[str, str | bool]:
    """Remove one source-resource selection without touching its Frappe record."""

    pack = _get_writable_pack(config_pack)
    if pack.status == "Archived":
        frappe.throw("Archived Config Packs cannot be changed.")
    row = next(
        (
            item
            for item in pack.resources
            if item.resource_type == resource_type and item.resource_name == resource_name
        ),
        None,
    )
    if row is None:
        return {"message": "Resource is not selected in this Config Pack.", "removed": False}
    pack.remove(row)
    pack.status = "Draft"
    pack.save()
    return {"message": "Resource removed from Config Pack.", "removed": True}


@frappe.whitelist()
def build_package(config_pack: str) -> dict[str, Any]:
    """Build and privately store an .fpack using the established Phase 1 engine."""

    return ConfigPackBuildService().build_and_store(_get_writable_pack(config_pack))


@frappe.whitelist()
def scan_dependencies(config_pack: str, add_missing: int | str | bool = False) -> dict[str, Any]:
    """Scan declared dependencies and, after explicit approval, add serializable resource dependencies."""

    return ConfigPackBuildService().scan_dependencies(
        _get_writable_pack(config_pack), add_missing=bool(frappe.utils.cint(add_missing))
    )


@frappe.whitelist()
def get_package_download(config_pack: str) -> dict[str, str]:
    """Return the authenticated private-file URL for a previously built package."""

    pack = frappe.get_doc("Config Pack", config_pack)
    pack.check_permission("read")
    if not pack.package_file:
        frappe.throw("Build this Config Pack before downloading it.")
    file_doc = frappe.get_doc("File", pack.package_file)
    return {"file_name": file_doc.file_name, "file_url": file_doc.file_url}


def _get_writable_pack(name: str):
    pack = frappe.get_doc("Config Pack", name)
    pack.check_permission("write")
    return pack
