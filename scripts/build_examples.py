"""Build deterministic clean and intentionally broken APKG examples."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path

import zstandard

from apkg_lint.config import Settings
from apkg_lint.package import load_package
from apkg_lint.rules import audit

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)
_VARINT_CONTINUATION = 0x80
_SCHEDULED_NOTE_ID = 102

SCHEMA11 = """
CREATE TABLE col (
  id integer PRIMARY KEY, crt integer NOT NULL, mod integer NOT NULL,
  scm integer NOT NULL, ver integer NOT NULL, dty integer NOT NULL,
  usn integer NOT NULL, ls integer NOT NULL, conf text NOT NULL,
  models text NOT NULL, decks text NOT NULL, dconf text NOT NULL, tags text NOT NULL
);
CREATE TABLE notes (
  id integer PRIMARY KEY, guid text NOT NULL, mid integer NOT NULL,
  mod integer NOT NULL, usn integer NOT NULL, tags text NOT NULL,
  flds text NOT NULL, sfld integer NOT NULL, csum integer NOT NULL,
  flags integer NOT NULL, data text NOT NULL
);
CREATE TABLE cards (
  id integer PRIMARY KEY, nid integer NOT NULL, did integer NOT NULL,
  ord integer NOT NULL, mod integer NOT NULL, usn integer NOT NULL,
  type integer NOT NULL, queue integer NOT NULL, due integer NOT NULL,
  ivl integer NOT NULL, factor integer NOT NULL, reps integer NOT NULL,
  lapses integer NOT NULL, left integer NOT NULL, odue integer NOT NULL,
  odid integer NOT NULL, flags integer NOT NULL, data text NOT NULL
);
CREATE TABLE revlog (
  id integer PRIMARY KEY, cid integer NOT NULL, usn integer NOT NULL,
  ease integer NOT NULL, ivl integer NOT NULL, lastIvl integer NOT NULL,
  factor integer NOT NULL, time integer NOT NULL, type integer NOT NULL
);
CREATE TABLE graves (usn integer NOT NULL, oid integer NOT NULL, type integer NOT NULL);
"""

SCHEMA18_ADDITIONS = """
CREATE TABLE fields (
  ntid integer NOT NULL, ord integer NOT NULL, name text NOT NULL,
  config blob NOT NULL, PRIMARY KEY (ntid, ord)
) without rowid;
CREATE TABLE templates (
  ntid integer NOT NULL, ord integer NOT NULL, name text NOT NULL,
  mtime_secs integer NOT NULL, usn integer NOT NULL, config blob NOT NULL,
  PRIMARY KEY (ntid, ord)
) without rowid;
CREATE TABLE notetypes (
  id integer NOT NULL PRIMARY KEY, name text NOT NULL,
  mtime_secs integer NOT NULL, usn integer NOT NULL, config blob NOT NULL
);
CREATE TABLE decks (
  id integer PRIMARY KEY NOT NULL, name text NOT NULL,
  mtime_secs integer NOT NULL, usn integer NOT NULL,
  common blob NOT NULL, kind blob NOT NULL
);
"""


def _varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("example protobuf encoder only accepts non-negative integers")
    output = bytearray()
    while value >= _VARINT_CONTINUATION:
        output.append((value & 0x7F) | _VARINT_CONTINUATION)
        value >>= 7
    output.append(value)
    return bytes(output)


def _field_varint(number: int, value: int) -> bytes:
    return _varint(number << 3) + _varint(value)


def _field_bytes(number: int, value: bytes) -> bytes:
    return _varint((number << 3) | 2) + _varint(len(value)) + value


def _template_config(question: str, answer: str) -> bytes:
    return _field_bytes(1, question.encode()) + _field_bytes(2, answer.encode())


def _notetype_config(*, cloze: bool, css: str) -> bytes:
    return _field_varint(1, int(cloze)) + _field_bytes(3, css.encode())


def _media_map(entries: list[tuple[str, bytes]]) -> bytes:
    payload = bytearray()
    for name, data in entries:
        entry = (
            _field_bytes(1, name.encode())
            + _field_varint(2, len(data))
            + _field_bytes(
                3,
                hashlib.sha1(data, usedforsecurity=False).digest(),
            )
        )
        payload.extend(_field_bytes(1, entry))
    return bytes(payload)


def _insert_collection(
    connection: sqlite3.Connection, *, version: int, models: str, decks: str
) -> None:
    connection.execute(
        "INSERT INTO col VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (1, 0, 0, 0, version, 0, 0, 0, "{}", models, decks, "{}", "{}"),
    )


def _insert_note(
    connection: sqlite3.Connection,
    *,
    note_id: int,
    guid: str,
    notetype_id: int,
    fields: list[str],
    tags: str = "",
) -> None:
    connection.execute(
        "INSERT INTO notes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            note_id,
            guid,
            notetype_id,
            1_700_000_000,
            0,
            tags,
            "\x1f".join(fields),
            fields[0] if fields else "",
            0,
            0,
            "",
        ),
    )


def _insert_card(
    connection: sqlite3.Connection,
    *,
    card_id: int,
    note_id: int,
    deck_id: int = 1,
    ordinal: int = 0,
    card_type: int = 0,
    interval: int = 0,
    repetitions: int = 0,
    lapses: int = 0,
) -> None:
    connection.execute(
        "INSERT INTO cards VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            card_id,
            note_id,
            deck_id,
            ordinal,
            1_700_000_000,
            0,
            card_type,
            0,
            card_id,
            interval,
            0,
            repetitions,
            lapses,
            0,
            0,
            0,
            0,
            "",
        ),
    )


def _new_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA11)
    return connection


def _finish_database(connection: sqlite3.Connection) -> None:
    connection.commit()
    connection.execute("VACUUM")
    connection.close()


def _zip_write(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    archive.writestr(info, payload, compresslevel=9)


def _write_apkg(path: Path, members: list[tuple[str, bytes]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in members:
            _zip_write(archive, name, payload)


def build_clean_modern(path: Path) -> None:
    """Create a schema-18, zstd/protobuf package with one healthy card and image."""

    media = [("capital.png", b"\x89PNG\r\n\x1a\napkg-lint-example")]
    compressor = zstandard.ZstdCompressor(level=9, write_checksum=True, threads=0)
    with tempfile.TemporaryDirectory(prefix="apkg-lint-clean-") as temporary:
        database_path = Path(temporary) / "collection.sqlite"
        connection = _new_database(database_path)
        connection.executescript(SCHEMA18_ADDITIONS)
        _insert_collection(connection, version=18, models="", decks="")
        connection.execute(
            "INSERT INTO notetypes VALUES (?, ?, ?, ?, ?)",
            (
                1000,
                "Basic",
                1_700_000_000,
                0,
                _notetype_config(cloze=False, css=".card { font-family: sans-serif; }"),
            ),
        )
        connection.executemany(
            "INSERT INTO fields VALUES (?, ?, ?, ?)",
            [(1000, 0, "Front", b""), (1000, 1, "Back", b"")],
        )
        connection.execute(
            "INSERT INTO templates VALUES (?, ?, ?, ?, ?, ?)",
            (
                1000,
                0,
                "Card 1",
                1_700_000_000,
                0,
                _template_config(
                    "{{Front}}",
                    '{{FrontSide}}<hr id="answer">{{Back}}',
                ),
            ),
        )
        connection.execute(
            "INSERT INTO decks VALUES (?, ?, ?, ?, ?, ?)",
            (1, "Example::Capitals", 1_700_000_000, 0, b"", b""),
        )
        _insert_note(
            connection,
            note_id=1_700_000_000_001,
            guid="clean-guid",
            notetype_id=1000,
            fields=[
                'What is the capital of France?<br><img src="capital.png">',
                "Paris",
            ],
        )
        _insert_card(
            connection,
            card_id=1_700_000_000_101,
            note_id=1_700_000_000_001,
        )
        _finish_database(connection)
        members = [
            ("meta", _field_varint(1, 3)),
            ("collection.anki21b", compressor.compress(database_path.read_bytes())),
            ("media", compressor.compress(_media_map(media))),
            ("0", compressor.compress(media[0][1])),
        ]
        _write_apkg(path, members)


def _legacy_models() -> str:
    models = {
        "1000": {
            "id": 1000,
            "name": "Broken Basic",
            "type": 0,
            "css": ".card { background: url('missing-background.png'); }",
            "flds": [{"name": "Front", "ord": 0}, {"name": "Back", "ord": 1}],
            "tmpls": [
                {
                    "name": "Card 1",
                    "ord": 0,
                    "qfmt": "{{MissingField}}",
                    "afmt": "{{FrontSide}}<hr>{{Back}}",
                }
            ],
        },
        "2000": {
            "id": 2000,
            "name": "Broken Cloze",
            "type": 1,
            "css": "",
            "flds": [{"name": "Text", "ord": 0}, {"name": "Extra", "ord": 1}],
            "tmpls": [
                {
                    "name": "Cloze",
                    "ord": 0,
                    "qfmt": "{{cloze:Text}}",
                    "afmt": "{{cloze:Text}}<hr>{{Extra}}",
                }
            ],
        },
    }
    return json.dumps(models, sort_keys=True, separators=(",", ":"))


def build_broken_legacy(path: Path) -> None:
    """Create a safe-to-open package containing deliberate semantic defects."""

    decks = json.dumps(
        {"1": {"id": 1, "name": "Broken Example"}},
        sort_keys=True,
        separators=(",", ":"),
    )
    with tempfile.TemporaryDirectory(prefix="apkg-lint-broken-") as temporary:
        database_path = Path(temporary) / "collection.sqlite"
        connection = _new_database(database_path)
        _insert_collection(
            connection,
            version=11,
            models=_legacy_models(),
            decks=decks,
        )
        notes = [
            (101, "empty", 1000, ["", "answer"]),
            (102, "dupe-a", 1000, ["Duplicate", "first"]),
            (103, "dupe-b", 1000, ["<b>duplicate</b>", "second"]),
            (104, "short", 1000, ["only one field"]),
            (105, "cloze-empty", 2000, ["No deletion here", ""]),
            (106, "cloze-mismatch", 2000, ["{{c2::wrong ordinal}}", ""]),
            (107, "missing-media", 1000, ['Image <img src="missing.png">', ""]),
            (108, "used-media", 1000, ['Image <img src="used.png">', ""]),
            (109, "missing-notetype", 9999, ["unknown type", ""]),
        ]
        for note_id, guid, notetype_id, fields in notes:
            _insert_note(
                connection,
                note_id=note_id,
                guid=guid,
                notetype_id=notetype_id,
                fields=fields,
            )
            _insert_card(
                connection,
                card_id=note_id + 1000,
                note_id=note_id,
                card_type=2 if note_id == _SCHEDULED_NOTE_ID else 0,
                interval=30 if note_id == _SCHEDULED_NOTE_ID else 0,
                repetitions=5 if note_id == _SCHEDULED_NOTE_ID else 0,
            )
        _insert_card(connection, card_id=9991, note_id=999999)
        _insert_card(connection, card_id=9992, note_id=102, deck_id=999)
        connection.execute(
            "INSERT INTO revlog VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (1_700_000_000_999, 1102, 0, 3, 30, 10, 2500, 1000, 1),
        )
        _finish_database(connection)
        media_map = {
            "0": "used.png",
            "1": "unused.mp3",
            "2": "missing-member.png",
            "3": "CON.jpg",
            "4": "Photo.png",
            "5": "photo.png",
        }
        members = [
            ("collection.anki21", database_path.read_bytes()),
            ("media", json.dumps(media_map, sort_keys=True, separators=(",", ":")).encode()),
            ("0", b"\x89PNG\r\n\x1a\nused"),
            ("1", b"ID3unused"),
            ("3", b"unsafe-name"),
            ("4", b"case-one"),
            ("5", b"case-two"),
            ("99", b"unmapped"),
        ]
        _write_apkg(path, members)


def _validate_examples() -> None:
    clean = audit(load_package(EXAMPLES / "clean-modern.apkg", Settings()), Settings())
    if clean.findings:
        raise RuntimeError(f"clean example unexpectedly has findings: {clean.findings}")
    broken = audit(load_package(EXAMPLES / "broken-legacy.apkg", Settings()), Settings())
    required = {
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
    }
    observed = {finding.rule_id for finding in broken.findings}
    if not required <= observed:
        raise RuntimeError(f"broken example is missing rules: {sorted(required - observed)}")


def build_all() -> None:
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    build_clean_modern(EXAMPLES / "clean-modern.apkg")
    build_broken_legacy(EXAMPLES / "broken-legacy.apkg")
    _validate_examples()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate committed examples without replacing them",
    )
    args = parser.parse_args()
    if args.check:
        _validate_examples()
        print("Example packages passed semantic validation.")
    else:
        build_all()
        print("Built examples/clean-modern.apkg and examples/broken-legacy.apkg.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
