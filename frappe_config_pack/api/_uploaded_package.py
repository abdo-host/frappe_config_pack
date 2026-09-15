"""Shared private-file boundary for package inspection workflows."""

from __future__ import annotations

from typing import Any

import frappe

from frappe_config_pack.core.constants import PACKAGE_EXTENSION


def read_private_fpack(file_name: str) -> tuple[Any, bytes]:
    """Return one authorized private .fpack file as bytes without changing it."""

    file_doc = frappe.get_doc("File", file_name)
    file_doc.check_permission("read")
    if not file_doc.is_private:
        frappe.throw("Config Pack uploads must be private files.")
    if not str(file_doc.file_name).lower().endswith(PACKAGE_EXTENSION):
        frappe.throw("Upload a file with the .fpack extension.")
    content = file_doc.get_content()
    if isinstance(content, str):
        content = content.encode()
    if not isinstance(content, bytes):
        frappe.throw("The uploaded Config Pack could not be read.")
    return file_doc, content
