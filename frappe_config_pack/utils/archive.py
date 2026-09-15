"""Safe, deterministic ZIP-compatible .fpack creation and reading."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any, BinaryIO
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

from frappe_config_pack.core.checksums import package_checksum, resource_checksum
from frappe_config_pack.core.constants import (
    CHECKSUMS_PATH,
    MANIFEST_PATH,
    MAX_ARCHIVE_MEMBERS,
    MAX_COMPRESSION_RATIO,
    MAX_MEMBER_SIZE,
    MAX_TOTAL_UNCOMPRESSED_SIZE,
)
from frappe_config_pack.core.exceptions import (
    ChecksumMismatchError,
    DuplicateResourceError,
    InvalidPackageError,
    ResourceValidationError,
)
from frappe_config_pack.core.manifest import validate_manifest
from frappe_config_pack.core.registry import ResourceRegistry
from frappe_config_pack.core.serializer import stable_json_bytes


@dataclass(frozen=True)
class BuildResult:
    archive: bytes
    resource_checksums: dict[str, str]
    package_checksum: str


@dataclass(frozen=True)
class ReadPackage:
    manifest: dict[str, Any]
    resources: tuple[dict[str, Any], ...]
    resource_checksums: dict[str, str]
    package_checksum: str


class SafeArchiveBuilder:
    """Build a reproducible archive from already normalized resource payloads."""

    def __init__(self, registry: ResourceRegistry) -> None:
        self.registry = registry

    def build(self, manifest: Mapping[str, Any], resources: Iterable[Mapping[str, Any]]) -> BuildResult:
        validated_manifest = validate_manifest(manifest)
        payloads = [dict(payload) for payload in resources]
        resource_checksums, counts = self._validate_resources(payloads)
        if validated_manifest["resources"] != counts or validated_manifest["total_resources"] != len(payloads):
            raise InvalidPackageError("Manifest resource counts do not match resources passed to the builder.")
        package_digest = package_checksum(validated_manifest, resource_checksums)
        checksums = {"package_checksum": package_digest, "resources": resource_checksums}

        entries: dict[str, bytes] = {
            MANIFEST_PATH: stable_json_bytes(validated_manifest),
            CHECKSUMS_PATH: stable_json_bytes(checksums),
        }
        for payload in payloads:
            handler = self.registry.get_handler(payload["resource_type"])
            path = handler.archive_path(payload)
            if path in entries:
                raise DuplicateResourceError(f"Duplicate archive path {path!r}.")
            entries[path] = stable_json_bytes(payload)
        archive = _write_deterministic_zip(entries)
        return BuildResult(archive, resource_checksums, package_digest)

    def _validate_resources(self, payloads: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, int]]:
        seen: set[str] = set()
        counts: dict[str, int] = {}
        checksums: dict[str, str] = {}
        for payload in payloads:
            if not isinstance(payload, dict) or not isinstance(payload.get("resource_type"), str):
                raise ResourceValidationError("Each packaged resource requires a resource_type.")
            handler = self.registry.get_handler(payload["resource_type"])
            handler.validate(payload)
            key = _resource_key(payload)
            if key in seen:
                raise DuplicateResourceError(f"Duplicate resource identity {key!r}.")
            seen.add(key)
            counts[payload["resource_type"]] = counts.get(payload["resource_type"], 0) + 1
            checksums[key] = resource_checksum(payload)
        return dict(sorted(checksums.items())), dict(sorted(counts.items()))


class SafeArchiveReader:
    """Validate archive structure and content entirely in memory."""

    def __init__(self, registry: ResourceRegistry) -> None:
        self.registry = registry

    def read(self, source: bytes | BinaryIO) -> ReadPackage:
        stream: BinaryIO = BytesIO(source) if isinstance(source, bytes) else source
        try:
            with ZipFile(stream, "r") as archive:
                infos = archive.infolist()
                self._validate_infos(infos)
                names = [info.filename for info in infos]
                if len(names) != len(set(names)):
                    raise InvalidPackageError("Archive contains duplicate member paths.")
                if MANIFEST_PATH not in names:
                    raise InvalidPackageError("Archive is missing manifest.json.")
                if CHECKSUMS_PATH not in names:
                    raise InvalidPackageError("Archive is missing meta/checksums.json.")
                for name in names:
                    if name not in {MANIFEST_PATH, CHECKSUMS_PATH} and not name.startswith("resources/"):
                        raise InvalidPackageError(f"Archive contains unexpected file {name!r}.")
                manifest = validate_manifest(_read_json(archive, MANIFEST_PATH))
                checksum_data = _read_json(archive, CHECKSUMS_PATH)
                resource_checksums, asserted_package_checksum = _validate_checksum_metadata(checksum_data)
                resources = self._read_resources(archive, infos, resource_checksums)
        except BadZipFile as error:
            raise InvalidPackageError("Package is not a valid ZIP archive.") from error

        computed_package_checksum = package_checksum(manifest, resource_checksums)
        if asserted_package_checksum != computed_package_checksum:
            raise ChecksumMismatchError("Package logical checksum does not match its manifest and resources.")
        _validate_manifest_resource_counts(manifest, resources)
        return ReadPackage(manifest, tuple(resources), resource_checksums, computed_package_checksum)

    def _validate_infos(self, infos: list[ZipInfo]) -> None:
        if len(infos) > MAX_ARCHIVE_MEMBERS:
            raise InvalidPackageError("Archive contains too many members.")
        total_size = 0
        for info in infos:
            _validate_member_name(info.filename)
            if info.is_dir():
                raise InvalidPackageError("Directory entries are not permitted in a package archive.")
            if info.file_size > MAX_MEMBER_SIZE:
                raise InvalidPackageError(f"Archive member {info.filename!r} exceeds the size limit.")
            total_size += info.file_size
            if total_size > MAX_TOTAL_UNCOMPRESSED_SIZE:
                raise InvalidPackageError("Archive uncompressed content exceeds the size limit.")
            if info.file_size and (not info.compress_size or info.file_size / info.compress_size > MAX_COMPRESSION_RATIO):
                raise InvalidPackageError(f"Archive member {info.filename!r} has an unsafe compression ratio.")

    def _read_resources(
        self, archive: ZipFile, infos: list[ZipInfo], resource_checksums: Mapping[str, str]
    ) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []
        seen: set[str] = set()
        for info in infos:
            if not info.filename.startswith("resources/"):
                continue
            payload = _read_json(archive, info.filename)
            if not isinstance(payload, dict) or not isinstance(payload.get("resource_type"), str):
                raise InvalidPackageError(f"Resource {info.filename!r} has no valid resource_type.")
            handler = self.registry.get_handler(payload["resource_type"])
            handler.validate(payload)
            if info.filename != handler.archive_path(payload):
                raise InvalidPackageError(f"Resource {info.filename!r} is not at its canonical archive path.")
            key = _resource_key(payload)
            if key in seen:
                raise DuplicateResourceError(f"Duplicate resource identity {key!r}.")
            seen.add(key)
            calculated = resource_checksum(payload)
            try:
                asserted = resource_checksums[key]
            except KeyError as error:
                raise ChecksumMismatchError(f"Resource checksum is missing for {key!r}.") from error
            if asserted != calculated:
                raise ChecksumMismatchError(f"Resource checksum mismatch for {key!r}.")
            resources.append(payload)
        if set(resource_checksums) != seen:
            raise ChecksumMismatchError("Checksum metadata does not exactly match packaged resources.")
        return resources


def _write_deterministic_zip(entries: Mapping[str, bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(entries):
            info = ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, entries[path], compress_type=ZIP_DEFLATED, compresslevel=9)
    return output.getvalue()


def _read_json(archive: ZipFile, path: str) -> Any:
    try:
        content = archive.read(path)
        return json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidPackageError(f"Archive member {path!r} is not valid UTF-8 JSON.") from error


def _validate_member_name(name: str) -> None:
    if not name or "\\" in name or "\x00" in name:
        raise InvalidPackageError("Archive contains an unsafe member name.")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise InvalidPackageError(f"Archive contains unsafe member path {name!r}.")


def _validate_checksum_metadata(value: Any) -> tuple[dict[str, str], str]:
    if not isinstance(value, dict) or set(value) != {"package_checksum", "resources"}:
        raise InvalidPackageError("checksums.json has an invalid schema.")
    resources, package_digest = value["resources"], value["package_checksum"]
    if not isinstance(resources, dict) or not isinstance(package_digest, str):
        raise InvalidPackageError("checksums.json has invalid checksum data.")
    for key, digest in resources.items():
        if not isinstance(key, str) or not isinstance(digest, str) or len(digest) != 64:
            raise InvalidPackageError("checksums.json contains an invalid resource checksum.")
    if len(package_digest) != 64:
        raise InvalidPackageError("checksums.json contains an invalid package checksum.")
    return dict(sorted(resources.items())), package_digest


def _validate_manifest_resource_counts(manifest: Mapping[str, Any], resources: list[Mapping[str, Any]]) -> None:
    counts: dict[str, int] = {}
    for resource in resources:
        resource_type = resource["resource_type"]
        counts[resource_type] = counts.get(resource_type, 0) + 1
    if manifest["resources"] != counts or manifest["total_resources"] != len(resources):
        raise InvalidPackageError("Manifest resource counts do not match archive content.")


def _resource_key(payload: Mapping[str, Any]) -> str:
    return f"{payload['resource_type']}:{payload['identity']}"
