"""Safe APKG archive inspection and extraction."""

from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import tempfile
import unicodedata
import zipfile
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from typing import BinaryIO, Protocol, cast

import zstandard

from apkg_lint.config import Settings
from apkg_lint.database import DatabaseReadError, read_database
from apkg_lint.model import MediaEntry, PackageSnapshot
from apkg_lint.protobuf import (
    ProtobufDecodeError,
    decode_utf8,
    first_bytes,
    first_varint,
    repeated_bytes,
)


class PackageReadError(ValueError):
    """Raised when a deck package cannot be safely or unambiguously inspected."""


_WINDOWS_RESERVED = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$",
    re.IGNORECASE,
)
_MAX_FILENAME_BYTES = 255
_FIRST_CONTROL_CODEPOINT = 32


class _BinaryReader(Protocol):
    def read(self, size: int = -1, /) -> bytes: ...


class _BinaryWriter(Protocol):
    def write(self, data: bytes, /) -> object: ...


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _archive_name_safe(name: str) -> bool:
    if not name or "\x00" in name or "\\" in name or ":" in name:
        return False
    path = Path(name)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


def _logical_filename_safe(name: str) -> bool:
    if (
        not name
        or len(name.encode("utf-8")) > _MAX_FILENAME_BYTES
        or name != unicodedata.normalize("NFC", name)
        or name in {".", ".."}
        or name.endswith((" ", "."))
        or "/" in name
        or "\\" in name
        or ":" in name
        or "\x00" in name
        or any(ord(character) < _FIRST_CONTROL_CODEPOINT for character in name)
    ):
        return False
    return _WINDOWS_RESERVED.fullmatch(name) is None


def _copy_limited(source: _BinaryReader, target: _BinaryWriter, limit: int, *, context: str) -> int:
    written = 0
    while True:
        block = source.read(128 * 1024)
        if not block:
            return written
        written += len(block)
        if written > limit:
            raise PackageReadError(f"{context} exceeds the configured size limit")
        target.write(block)


def _read_limited(source: _BinaryReader, limit: int, *, context: str) -> bytes:
    output = io.BytesIO()
    _copy_limited(source, output, limit, context=context)
    return output.getvalue()


def _zstd_reader(source: _BinaryReader, *, context: str) -> BinaryIO:
    try:
        return cast(
            BinaryIO,
            zstandard.ZstdDecompressor().stream_reader(cast(BinaryIO, source)),
        )
    except zstandard.ZstdError as exc:
        raise PackageReadError(f"{context} is not valid zstd data") from exc


def _decode_meta(payload: bytes) -> int:
    try:
        return first_varint(payload, 1)
    except ProtobufDecodeError as exc:
        raise PackageReadError("meta is not a valid PackageMetadata protobuf") from exc


def _decode_modern_media(payload: bytes) -> tuple[MediaEntry, ...]:
    try:
        raw_entries = repeated_bytes(payload, 1)
        entries: list[MediaEntry] = []
        for ordinal, raw in enumerate(raw_entries):
            name = decode_utf8(first_bytes(raw, 1), context=f"media entry {ordinal} name")
            sha1_bytes = first_bytes(raw, 3)
            legacy_index = first_varint(raw, 255, ordinal)
            entries.append(
                MediaEntry(
                    index=legacy_index,
                    name=name,
                    declared_size=first_varint(raw, 2),
                    declared_sha1=sha1_bytes.hex() if sha1_bytes else None,
                    filename_safe=_logical_filename_safe(name),
                )
            )
        return tuple(entries)
    except ProtobufDecodeError as exc:
        raise PackageReadError("media is not a valid MediaEntries protobuf") from exc


def _decode_legacy_media(payload: bytes) -> tuple[MediaEntry, ...]:
    try:
        mapping = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackageReadError("legacy media map is not valid UTF-8 JSON") from exc
    if not isinstance(mapping, dict):
        raise PackageReadError("legacy media map must be a JSON object")
    entries: list[MediaEntry] = []
    for raw_index, raw_name in mapping.items():
        if not str(raw_index).isdigit() or not isinstance(raw_name, str):
            raise PackageReadError("legacy media map keys must be numbers and values strings")
        entries.append(
            MediaEntry(
                index=int(raw_index),
                name=raw_name,
                declared_size=None,
                declared_sha1=None,
                filename_safe=_logical_filename_safe(raw_name),
            )
        )
    return tuple(sorted(entries, key=lambda entry: entry.index))


def _validate_archive(archive: zipfile.ZipFile, settings: Settings) -> tuple[tuple[str, ...], int]:
    infos = archive.infolist()
    if len(infos) > settings.limits.max_members:
        raise PackageReadError(
            f"archive has {len(infos)} members; limit is {settings.limits.max_members}"
        )
    names = [info.filename for info in infos]
    duplicates = tuple(sorted(name for name in set(names) if names.count(name) > 1))
    if duplicates:
        raise PackageReadError(
            "archive contains ambiguous duplicate members: " + ", ".join(duplicates[:10])
        )
    total = 0
    for info in infos:
        if not _archive_name_safe(info.filename):
            raise PackageReadError(f"archive member has an unsafe path: {info.filename!r}")
        unix_mode = info.external_attr >> 16
        if unix_mode and stat.S_ISLNK(unix_mode):
            raise PackageReadError(f"archive member is a symbolic link: {info.filename!r}")
        if info.is_dir():
            raise PackageReadError(f"archive contains an unexpected directory: {info.filename!r}")
        total += info.file_size
        if total > settings.limits.max_uncompressed_bytes:
            raise PackageReadError("archive exceeds the configured uncompressed size limit")
        if info.file_size:
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > settings.limits.max_compression_ratio:
                raise PackageReadError(
                    f"archive member {info.filename!r} has suspicious compression ratio {ratio:.1f}"
                )
    return duplicates, total


def _format_from_archive(archive: zipfile.ZipFile, settings: Settings) -> tuple[str, str, bool]:
    names = frozenset(archive.namelist())
    if "meta" in names:
        with archive.open("meta") as source:
            meta = _read_limited(
                source, settings.limits.max_control_bytes, context="package metadata"
            )
        version = _decode_meta(meta)
        formats = {
            1: ("legacy-1", "collection.anki2", False),
            2: ("legacy-2", "collection.anki21", False),
            3: ("latest", "collection.anki21b", True),
        }
        if version not in formats:
            raise PackageReadError(f"unsupported package metadata version {version}")
        selected = formats[version]
    elif "collection.anki21" in names:
        selected = ("legacy-2", "collection.anki21", False)
    elif "collection.anki2" in names:
        selected = ("legacy-1", "collection.anki2", False)
    else:
        raise PackageReadError("package contains no supported Anki collection member")
    if selected[1] not in names:
        raise PackageReadError(
            f"package metadata expects {selected[1]!r}, but that member is missing"
        )
    return selected


def _extract_database(
    archive: zipfile.ZipFile,
    member: str,
    modern: bool,
    target: Path,
    settings: Settings,
) -> None:
    try:
        with archive.open(member) as compressed, target.open("wb") as output:
            if modern:
                with _zstd_reader(compressed, context=member) as source:
                    _copy_limited(
                        source,
                        output,
                        settings.limits.max_database_bytes,
                        context="decompressed collection",
                    )
            else:
                _copy_limited(
                    compressed,
                    output,
                    settings.limits.max_database_bytes,
                    context="collection",
                )
    except (zipfile.BadZipFile, zstandard.ZstdError) as exc:
        raise PackageReadError(f"could not extract {member}: {exc}") from exc


def _read_media_map(
    archive: zipfile.ZipFile, modern: bool, settings: Settings
) -> tuple[MediaEntry, ...]:
    if "media" not in archive.namelist():
        return ()
    try:
        with archive.open("media") as compressed:
            if modern:
                with _zstd_reader(compressed, context="media map") as source:
                    payload = _read_limited(
                        source,
                        settings.limits.max_control_bytes,
                        context="decompressed media map",
                    )
                return _decode_modern_media(payload)
            payload = _read_limited(
                compressed, settings.limits.max_control_bytes, context="legacy media map"
            )
            return _decode_legacy_media(payload)
    except (zipfile.BadZipFile, zstandard.ZstdError) as exc:
        raise PackageReadError(f"could not read media map: {exc}") from exc


def _hash_stream(source: _BinaryReader, limit: int, *, context: str) -> tuple[int, str]:
    digest = hashlib.sha1(usedforsecurity=False)
    size = 0
    while True:
        block = source.read(128 * 1024)
        if not block:
            return size, digest.hexdigest()
        size += len(block)
        if size > limit:
            raise PackageReadError(f"{context} exceeds the remaining media size limit")
        digest.update(block)


def _inspect_media(
    archive: zipfile.ZipFile,
    entries: Iterable[MediaEntry],
    *,
    modern: bool,
    settings: Settings,
) -> tuple[MediaEntry, ...]:
    inspected: list[MediaEntry] = []
    remaining = settings.limits.max_uncompressed_bytes
    names = frozenset(archive.namelist())
    for entry in entries:
        member = str(entry.index)
        if member not in names:
            inspected.append(replace(entry, present=False, error="mapped member is missing"))
            continue
        if not settings.verify_media:
            inspected.append(entry)
            continue
        try:
            with archive.open(member) as compressed:
                if modern:
                    with _zstd_reader(compressed, context=f"media member {member}") as source:
                        size, sha1 = _hash_stream(
                            source, remaining, context=f"media member {member}"
                        )
                else:
                    size, sha1 = _hash_stream(
                        compressed, remaining, context=f"media member {member}"
                    )
            remaining -= size
            inspected.append(replace(entry, actual_size=size, actual_sha1=sha1))
        except (zipfile.BadZipFile, zstandard.ZstdError, PackageReadError) as exc:
            inspected.append(replace(entry, error=str(exc)))
    return tuple(inspected)


def load_package(path: Path, settings: Settings) -> PackageSnapshot:
    """Inspect one APKG and return all data required by the rule engine."""

    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise PackageReadError(f"package does not exist or is not a file: {path}")
    if resolved.suffix.lower() != ".apkg":
        raise PackageReadError("expected a file ending in .apkg")
    try:
        with zipfile.ZipFile(resolved) as archive:
            duplicate_members, uncompressed_bytes = _validate_archive(archive, settings)
            package_version, collection_member, modern = _format_from_archive(archive, settings)
            with tempfile.TemporaryDirectory(prefix="apkg-lint-") as temporary:
                database_path = Path(temporary) / "collection.sqlite"
                _extract_database(archive, collection_member, modern, database_path, settings)
                database = read_database(database_path)
            media = _read_media_map(archive, modern, settings)
            inspected_media = _inspect_media(archive, media, modern=modern, settings=settings)
            mapped = frozenset(str(entry.index) for entry in media)
            control = {"meta", "media", collection_member}
            unmapped = tuple(
                sorted(
                    name
                    for name in archive.namelist()
                    if name not in control and name not in mapped
                )
            )
            return PackageSnapshot(
                path=resolved,
                sha256=_file_sha256(resolved),
                package_version=package_version,
                collection_member=collection_member,
                schema_version=database.schema_version,
                sqlite_check=database.sqlite_check,
                notes=database.notes,
                cards=database.cards,
                notetypes=database.notetypes,
                decks=database.decks,
                media=inspected_media,
                mapped_media_members=mapped,
                unmapped_media_members=unmapped,
                duplicate_members=duplicate_members,
                archive_member_count=len(archive.infolist()),
                archive_uncompressed_bytes=uncompressed_bytes,
                review_count=database.review_count,
            )
    except zipfile.BadZipFile as exc:
        raise PackageReadError("file is not a valid ZIP/APKG archive") from exc
    except DatabaseReadError as exc:
        raise PackageReadError(str(exc)) from exc
