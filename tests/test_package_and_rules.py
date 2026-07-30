from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
import zstandard

from apkg_lint.config import Limits, Settings
from apkg_lint.model import Severity
from apkg_lint.package import PackageReadError, load_package
from apkg_lint.rules import audit, media_references
from scripts.build_examples import build_broken_legacy, build_clean_modern


def _examples(tmp_path: Path) -> tuple[Path, Path]:
    clean = tmp_path / "clean.apkg"
    broken = tmp_path / "broken.apkg"
    build_clean_modern(clean)
    build_broken_legacy(broken)
    return clean, broken


def _rewrite(path: Path, replacements: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path) as source:
        members = [(info.filename, source.read(info)) for info in source.infolist()]
    with zipfile.ZipFile(path, "w") as target:
        for name, payload in members:
            target.writestr(name, replacements.get(name, payload))


def test_loads_and_audits_clean_modern_package(tmp_path: Path) -> None:
    clean, _ = _examples(tmp_path)
    snapshot = load_package(clean, Settings())
    assert snapshot.package_version == "latest"
    assert snapshot.collection_member == "collection.anki21b"
    assert snapshot.schema_version == 18
    assert snapshot.sqlite_check == ("ok",)
    assert len(snapshot.notes) == len(snapshot.cards) == len(snapshot.media) == 1
    assert snapshot.media[0].name == "capital.png"
    assert snapshot.media[0].actual_sha1 == snapshot.media[0].declared_sha1
    assert audit(snapshot, Settings()).findings == ()


def test_broken_package_exercises_expected_rules(tmp_path: Path) -> None:
    _, broken = _examples(tmp_path)
    report = audit(load_package(broken, Settings()), Settings())
    rule_ids = {finding.rule_id for finding in report.findings}
    assert {
        "DB001",
        "DB002",
        "DB003",
        "NOTE001",
        "NOTE002",
        "NOTE003",
        "CLOZE001",
        "CLOZE002",
        "TEMPLATE001",
        "TEMPLATE002",
        "MEDIA001",
        "MEDIA004",
        "MEDIA005",
        "MEDIA006",
        "MEDIA007",
        "PKG002",
        "SHARE001",
    } <= rule_ids
    assert report.summary()["error"] > 0
    assert report.counts["notes"] == 9


def test_backup_profile_ignore_and_severity_override(tmp_path: Path) -> None:
    _, broken = _examples(tmp_path)
    settings = Settings(
        profile="backup",
        ignored_rules=frozenset({"MEDIA006"}),
        severity_overrides={"NOTE002": Severity.ERROR},
    )
    report = audit(load_package(broken, settings), settings)
    rule_ids = {finding.rule_id for finding in report.findings}
    assert "SHARE001" not in rule_ids
    assert "MEDIA006" not in rule_ids
    duplicate = next(finding for finding in report.findings if finding.rule_id == "NOTE002")
    assert duplicate.severity is Severity.ERROR
    assert report.ignored_rules == ("MEDIA006",)


def test_can_skip_media_payload_verification(tmp_path: Path) -> None:
    clean, _ = _examples(tmp_path)
    settings = Settings(verify_media=False)
    snapshot = load_package(clean, settings)
    assert snapshot.media[0].actual_sha1 is None
    assert audit(snapshot, settings).findings == ()


def test_detects_modern_media_hash_and_size_mismatch(tmp_path: Path) -> None:
    clean, _ = _examples(tmp_path)
    compressor = zstandard.ZstdCompressor(level=3)
    _rewrite(clean, {"0": compressor.compress(b"different")})
    report = audit(load_package(clean, Settings()), Settings())
    assert {"MEDIA002", "MEDIA003"} <= {finding.rule_id for finding in report.findings}


def test_media_reference_parser_handles_html_sound_css_and_remote_values() -> None:
    value = """
<img src="hello%20world.png">
<video poster='cover.jpg'></video>
<source srcset="one.png 1x, two.png 2x">
[sound:voice.mp3]
body { background: url("paper.png") }
<img src="https://example.invalid/remote.png">
<img src="{{Dynamic}}">
"""
    assert media_references(value) == {
        "hello world.png",
        "cover.jpg",
        "one.png",
        "two.png",
        "voice.mp3",
        "paper.png",
    }


@pytest.mark.parametrize(
    ("filename", "builder", "message"),
    [
        ("missing.apkg", None, "does not exist"),
        ("deck.zip", "clean", "ending in .apkg"),
    ],
)
def test_rejects_missing_or_wrong_extension(
    tmp_path: Path,
    filename: str,
    builder: str | None,
    message: str,
) -> None:
    path = tmp_path / filename
    if builder == "clean":
        build_clean_modern(path)
    with pytest.raises(PackageReadError, match=message):
        load_package(path, Settings())


def test_rejects_non_zip_and_unsupported_metadata(tmp_path: Path) -> None:
    plain = tmp_path / "plain.apkg"
    plain.write_bytes(b"not a zip")
    with pytest.raises(PackageReadError, match="valid ZIP"):
        load_package(plain, Settings())

    unsupported = tmp_path / "unsupported.apkg"
    with zipfile.ZipFile(unsupported, "w") as archive:
        archive.writestr("meta", b"\x08\x04")
    with pytest.raises(PackageReadError, match="metadata version 4"):
        load_package(unsupported, Settings())


def test_rejects_unsafe_duplicate_symlink_and_bomb_members(tmp_path: Path) -> None:
    unsafe = tmp_path / "unsafe.apkg"
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../collection.anki2", b"x")
    with pytest.raises(PackageReadError, match="unsafe path"):
        load_package(unsafe, Settings())

    duplicate = tmp_path / "duplicate.apkg"
    with zipfile.ZipFile(duplicate, "w") as archive:
        archive.writestr("collection.anki2", b"x")
        archive.writestr("collection.anki2", b"y")
    with pytest.raises(PackageReadError, match="duplicate"):
        load_package(duplicate, Settings())

    symlink = tmp_path / "symlink.apkg"
    with zipfile.ZipFile(symlink, "w") as archive:
        info = zipfile.ZipInfo("collection.anki2")
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        archive.writestr(info, b"target")
    with pytest.raises(PackageReadError, match="symbolic link"):
        load_package(symlink, Settings())

    bomb = tmp_path / "bomb.apkg"
    with zipfile.ZipFile(bomb, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("collection.anki2", b"A" * 100_000)
    settings = Settings(
        limits=Limits(
            max_members=10,
            max_uncompressed_bytes=200_000,
            max_database_bytes=200_000,
            max_control_bytes=1_000,
            max_compression_ratio=2,
        )
    )
    with pytest.raises(PackageReadError, match="compression ratio"):
        load_package(bomb, settings)


def test_rejects_member_count_and_uncompressed_size_limits(tmp_path: Path) -> None:
    too_many = tmp_path / "many.apkg"
    with zipfile.ZipFile(too_many, "w") as archive:
        archive.writestr("collection.anki2", b"x")
        archive.writestr("media", b"{}")
    with pytest.raises(PackageReadError, match="2 members"):
        load_package(
            too_many,
            Settings(
                limits=Limits(
                    max_members=1,
                    max_uncompressed_bytes=100,
                    max_database_bytes=100,
                    max_control_bytes=100,
                    max_compression_ratio=100,
                )
            ),
        )

    too_large = tmp_path / "large.apkg"
    with zipfile.ZipFile(too_large, "w") as archive:
        archive.writestr("collection.anki2", b"12345")
    with pytest.raises(PackageReadError, match="uncompressed size"):
        load_package(
            too_large,
            Settings(
                limits=Limits(
                    max_members=10,
                    max_uncompressed_bytes=4,
                    max_database_bytes=100,
                    max_control_bytes=100,
                    max_compression_ratio=100,
                )
            ),
        )


def test_rejects_missing_collection_and_invalid_legacy_media(tmp_path: Path) -> None:
    missing = tmp_path / "missing-collection.apkg"
    with zipfile.ZipFile(missing, "w") as archive:
        archive.writestr("media", b"{}")
    with pytest.raises(PackageReadError, match="no supported"):
        load_package(missing, Settings())

    clean, _ = _examples(tmp_path)
    with zipfile.ZipFile(clean) as source:
        database = zstandard.ZstdDecompressor().decompress(source.read("collection.anki21b"))
    invalid_media = tmp_path / "bad-media.apkg"
    with zipfile.ZipFile(invalid_media, "w") as archive:
        archive.writestr("collection.anki2", database)
        archive.writestr("media", b"[]")
    with pytest.raises(PackageReadError, match="JSON object"):
        load_package(invalid_media, Settings())


def test_rejects_invalid_modern_zstd(tmp_path: Path) -> None:
    path = tmp_path / "bad-zstd.apkg"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("meta", b"\x08\x03")
        archive.writestr("collection.anki21b", b"not-zstd")
        archive.writestr("media", b"not-zstd")
    with pytest.raises(PackageReadError, match=r"could not extract|zstd"):
        load_package(path, Settings())
