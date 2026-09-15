from __future__ import annotations

import json
import unittest
import warnings
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from frappe_config_pack.core.exceptions import ChecksumMismatchError, InvalidPackageError
from frappe_config_pack.services.builder import PackageBuilder, ResourceInput
from frappe_config_pack.services.reader import PackageReader
from frappe_config_pack.tests.helpers import custom_field, manifest, property_setter


class TestArchive(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = PackageBuilder()
        self.reader = PackageReader()
        self.inputs = [
            ResourceInput("Custom Field", custom_field()),
            ResourceInput("Property Setter", property_setter()),
        ]

    def test_build_and_read_are_deterministic(self) -> None:
        first = self.builder.build(manifest(), self.inputs)
        second = self.builder.build(manifest(), self.inputs)
        self.assertEqual(first.archive, second.archive)
        self.assertEqual(first.package_checksum, second.package_checksum)
        parsed = self.reader.read(first.archive)
        self.assertEqual(parsed.package_checksum, first.package_checksum)
        self.assertEqual(len(parsed.resources), 2)

    def test_missing_manifest_is_rejected(self) -> None:
        archive = _zip({"meta/checksums.json": b"{}"})
        with self.assertRaises(InvalidPackageError):
            self.reader.read(archive)

    def test_corrupt_zip_is_rejected(self) -> None:
        with self.assertRaises(InvalidPackageError):
            self.reader.read(b"this is not a ZIP archive")

    def test_path_traversal_is_rejected_before_reading(self) -> None:
        archive = _zip({"../manifest.json": b"{}"})
        with self.assertRaises(InvalidPackageError):
            self.reader.read(archive)

    def test_absolute_path_is_rejected_before_reading(self) -> None:
        archive = _zip({"/manifest.json": b"{}"})
        with self.assertRaises(InvalidPackageError):
            self.reader.read(archive)

    def test_malformed_json_is_rejected(self) -> None:
        archive = _zip({"manifest.json": b"not-json", "meta/checksums.json": b"{}"})
        with self.assertRaises(InvalidPackageError):
            self.reader.read(archive)

    def test_checksum_tampering_is_rejected(self) -> None:
        result = self.builder.build(manifest(), self.inputs)
        entries = _entries(result.archive)
        checksums = json.loads(entries["meta/checksums.json"])
        key = next(iter(checksums["resources"]))
        checksums["resources"][key] = "0" * 64
        entries["meta/checksums.json"] = json.dumps(checksums).encode()
        with self.assertRaises(ChecksumMismatchError):
            self.reader.read(_zip(entries))

    def test_unexpected_file_is_rejected(self) -> None:
        result = self.builder.build(manifest(), self.inputs)
        entries = _entries(result.archive)
        entries["run.py"] = b"print('never execute me')"
        with self.assertRaises(InvalidPackageError):
            self.reader.read(_zip(entries))

    def test_duplicate_archive_member_is_rejected(self) -> None:
        result = self.builder.build(manifest(), self.inputs)
        entries = _entries(result.archive)
        duplicate = BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with ZipFile(duplicate, "w", compression=ZIP_DEFLATED) as archive:
                for name, content in entries.items():
                    archive.writestr(name, content)
                archive.writestr("manifest.json", entries["manifest.json"])
        with self.assertRaises(InvalidPackageError):
            self.reader.read(duplicate.getvalue())

    def test_duplicate_resource_identity_is_rejected_by_builder(self) -> None:
        duplicated = [*self.inputs, ResourceInput("Custom Field", custom_field())]
        with self.assertRaises(InvalidPackageError):
            self.builder.build(manifest({"Custom Field": 2, "Property Setter": 1}), duplicated)

    def test_manifest_count_mismatch_is_rejected_by_builder(self) -> None:
        with self.assertRaises(InvalidPackageError):
            self.builder.build(manifest({"Custom Field": 1}), self.inputs)


def _entries(archive: bytes) -> dict[str, bytes]:
    with ZipFile(BytesIO(archive), "r") as source:
        return {name: source.read(name) for name in source.namelist()}


def _zip(entries: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return output.getvalue()
