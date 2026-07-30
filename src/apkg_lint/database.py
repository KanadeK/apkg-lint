"""Read Anki collection SQLite files without importing or mutating them."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from apkg_lint.model import CardRecord, NoteRecord, NotetypeRecord, TemplateRecord
from apkg_lint.protobuf import ProtobufDecodeError, first_bytes, first_varint


class DatabaseReadError(ValueError):
    """Raised when an extracted collection is corrupt or structurally unsupported."""


MIN_SCHEMA_VERSION = 11
MODERN_SCHEMA_VERSION = 15
MAX_SCHEMA_VERSION = 18


@dataclass(frozen=True)
class DatabaseSnapshot:
    schema_version: int
    sqlite_check: tuple[str, ...]
    notes: tuple[NoteRecord, ...]
    cards: tuple[CardRecord, ...]
    notetypes: dict[int, NotetypeRecord]
    decks: dict[int, str]
    review_count: int


def _tables(connection: sqlite3.Connection) -> frozenset[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ).fetchall()
    return frozenset(str(row[0]) for row in rows)


def _one_collection_row(connection: sqlite3.Connection) -> sqlite3.Row:
    rows = connection.execute("SELECT * FROM col").fetchall()
    if len(rows) != 1:
        raise DatabaseReadError(f"expected one row in col, found {len(rows)}")
    return cast(sqlite3.Row, rows[0])


def _legacy_notetypes(collection_row: sqlite3.Row) -> dict[int, NotetypeRecord]:
    raw = collection_row["models"]
    try:
        models = json.loads(str(raw or "{}"))
    except json.JSONDecodeError as exc:
        raise DatabaseReadError("col.models is not valid JSON") from exc
    if not isinstance(models, dict):
        raise DatabaseReadError("col.models must be a JSON object")
    notetypes: dict[int, NotetypeRecord] = {}
    for raw_id, model in models.items():
        if not isinstance(model, dict):
            raise DatabaseReadError(f"notetype {raw_id} is not a JSON object")
        notetype_id = int(raw_id)
        fields_raw = model.get("flds", [])
        templates_raw = model.get("tmpls", [])
        if not isinstance(fields_raw, list) or not isinstance(templates_raw, list):
            raise DatabaseReadError(f"notetype {notetype_id} fields/templates are malformed")
        ordered_fields = sorted(
            (item for item in fields_raw if isinstance(item, dict)),
            key=lambda item: int(item.get("ord", 0)),
        )
        ordered_templates = sorted(
            (item for item in templates_raw if isinstance(item, dict)),
            key=lambda item: int(item.get("ord", 0)),
        )
        notetypes[notetype_id] = NotetypeRecord(
            id=notetype_id,
            name=str(model.get("name", f"notetype-{notetype_id}")),
            kind="cloze" if int(model.get("type", 0)) == 1 else "normal",
            field_names=tuple(str(item.get("name", "")) for item in ordered_fields),
            templates=tuple(
                TemplateRecord(
                    ordinal=int(item.get("ord", ordinal)),
                    name=str(item.get("name", f"Card {ordinal + 1}")),
                    question_format=str(item.get("qfmt", "")),
                    answer_format=str(item.get("afmt", "")),
                )
                for ordinal, item in enumerate(ordered_templates)
            ),
            css=str(model.get("css", "")),
        )
    return notetypes


def _legacy_decks(collection_row: sqlite3.Row) -> dict[int, str]:
    raw = collection_row["decks"]
    try:
        decks_raw = json.loads(str(raw or "{}"))
    except json.JSONDecodeError as exc:
        raise DatabaseReadError("col.decks is not valid JSON") from exc
    if not isinstance(decks_raw, dict):
        raise DatabaseReadError("col.decks must be a JSON object")
    decks: dict[int, str] = {}
    for raw_id, deck in decks_raw.items():
        if isinstance(deck, dict):
            decks[int(raw_id)] = str(deck.get("name", f"deck-{raw_id}"))
    return decks


def _modern_notetypes(connection: sqlite3.Connection) -> dict[int, NotetypeRecord]:
    fields_by_notetype: dict[int, list[tuple[int, str]]] = {}
    for row in connection.execute("SELECT ntid, ord, name FROM fields ORDER BY ntid, ord"):
        fields_by_notetype.setdefault(int(row["ntid"]), []).append(
            (int(row["ord"]), str(row["name"]))
        )

    templates_by_notetype: dict[int, list[TemplateRecord]] = {}
    for row in connection.execute(
        "SELECT ntid, ord, name, config FROM templates ORDER BY ntid, ord"
    ):
        config = bytes(row["config"])
        try:
            question = first_bytes(config, 1).decode("utf-8")
            answer = first_bytes(config, 2).decode("utf-8")
        except (UnicodeDecodeError, ProtobufDecodeError) as exc:
            raise DatabaseReadError(
                f"template {row['ntid']}/{row['ord']} config is invalid"
            ) from exc
        templates_by_notetype.setdefault(int(row["ntid"]), []).append(
            TemplateRecord(
                ordinal=int(row["ord"]),
                name=str(row["name"]),
                question_format=question,
                answer_format=answer,
            )
        )

    notetypes: dict[int, NotetypeRecord] = {}
    for row in connection.execute("SELECT id, name, config FROM notetypes ORDER BY id"):
        config = bytes(row["config"])
        try:
            kind_value = first_varint(config, 1)
            css = first_bytes(config, 3).decode("utf-8")
        except (UnicodeDecodeError, ProtobufDecodeError) as exc:
            raise DatabaseReadError(f"notetype {row['id']} config is invalid") from exc
        notetype_id = int(row["id"])
        notetypes[notetype_id] = NotetypeRecord(
            id=notetype_id,
            name=str(row["name"]),
            kind="cloze" if kind_value == 1 else "normal",
            field_names=tuple(name for _, name in fields_by_notetype.get(notetype_id, [])),
            templates=tuple(templates_by_notetype.get(notetype_id, [])),
            css=css,
        )
    return notetypes


def _modern_decks(connection: sqlite3.Connection) -> dict[int, str]:
    return {
        int(row["id"]): str(row["name"])
        for row in connection.execute("SELECT id, name FROM decks ORDER BY id")
    }


def _read_notes(connection: sqlite3.Connection) -> tuple[NoteRecord, ...]:
    return tuple(
        NoteRecord(
            id=int(row["id"]),
            guid=str(row["guid"]),
            notetype_id=int(row["mid"]),
            tags=str(row["tags"]),
            fields=tuple(str(row["flds"]).split("\x1f")),
        )
        for row in connection.execute("SELECT id, guid, mid, tags, flds FROM notes ORDER BY id")
    )


def _read_cards(connection: sqlite3.Connection) -> tuple[CardRecord, ...]:
    return tuple(
        CardRecord(
            id=int(row["id"]),
            note_id=int(row["nid"]),
            deck_id=int(row["did"]),
            ordinal=int(row["ord"]),
            card_type=int(row["type"]),
            queue=int(row["queue"]),
            interval=int(row["ivl"]),
            repetitions=int(row["reps"]),
            lapses=int(row["lapses"]),
        )
        for row in connection.execute(
            """
            SELECT id, nid, did, ord, type, queue, ivl, reps, lapses
            FROM cards
            ORDER BY id
            """
        )
    )


def read_database(path: Path) -> DatabaseSnapshot:
    """Load the supported parts of a collection into immutable Python records."""

    uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.create_collation(
            "unicase",
            lambda left, right: (
                (left.casefold() > right.casefold()) - (left.casefold() < right.casefold())
            ),
        )
        connection.execute("PRAGMA trusted_schema = OFF")
        tables = _tables(connection)
        required = {"col", "notes", "cards"}
        missing = required - tables
        if missing:
            raise DatabaseReadError(
                f"collection is missing required tables: {', '.join(sorted(missing))}"
            )
        collection_row = _one_collection_row(connection)
        schema_version = int(collection_row["ver"])
        if not MIN_SCHEMA_VERSION <= schema_version <= MAX_SCHEMA_VERSION:
            raise DatabaseReadError(
                f"unsupported collection schema {schema_version}; supported range is 11-18"
            )
        sqlite_check = tuple(
            str(row[0]) for row in connection.execute("PRAGMA quick_check").fetchall()
        )
        notes = _read_notes(connection)
        cards = _read_cards(connection)
        if schema_version >= MODERN_SCHEMA_VERSION:
            modern_required = {"fields", "templates", "notetypes", "decks"}
            missing_modern = modern_required - tables
            if missing_modern:
                raise DatabaseReadError(
                    "modern collection is missing tables: " + ", ".join(sorted(missing_modern))
                )
            notetypes = _modern_notetypes(connection)
            decks = _modern_decks(connection)
        else:
            notetypes = _legacy_notetypes(collection_row)
            decks = _legacy_decks(collection_row)
        review_count = (
            int(connection.execute("SELECT COUNT(*) FROM revlog").fetchone()[0])
            if "revlog" in tables
            else 0
        )
        return DatabaseSnapshot(
            schema_version=schema_version,
            sqlite_check=sqlite_check,
            notes=notes,
            cards=cards,
            notetypes=notetypes,
            decks=decks,
            review_count=review_count,
        )
    except sqlite3.DatabaseError as exc:
        raise DatabaseReadError(f"SQLite could not read the collection: {exc}") from exc
    finally:
        if "connection" in locals():
            connection.close()
