"""Deterministic APKG lint rules."""

from __future__ import annotations

import html
import re
import unicodedata
from collections import defaultdict
from contextlib import suppress
from html.parser import HTMLParser
from urllib.parse import unquote

from apkg_lint.config import Settings
from apkg_lint.model import (
    AuditReport,
    Finding,
    PackageSnapshot,
    RuleDefinition,
    Severity,
)

RULES: tuple[RuleDefinition, ...] = (
    RuleDefinition(
        "PKG001",
        Severity.ERROR,
        "SQLite integrity check failed",
        "The collection database did not pass SQLite PRAGMA quick_check.",
    ),
    RuleDefinition(
        "PKG002",
        Severity.WARNING,
        "Unmapped archive member",
        "The APKG contains a member not declared by its collection or media map.",
    ),
    RuleDefinition(
        "DB001",
        Severity.ERROR,
        "Orphan card",
        "A card points to a note that is absent from the package.",
    ),
    RuleDefinition(
        "DB002",
        Severity.ERROR,
        "Missing notetype",
        "A note references a notetype that is absent from the package.",
    ),
    RuleDefinition(
        "DB003",
        Severity.ERROR,
        "Missing deck",
        "A card references a deck that is absent from the package.",
    ),
    RuleDefinition(
        "NOTE001",
        Severity.ERROR,
        "Empty first field",
        "A note has no text or media in its first field.",
    ),
    RuleDefinition(
        "NOTE002",
        Severity.WARNING,
        "Duplicate first field",
        "Multiple notes in one notetype normalize to the same first field.",
    ),
    RuleDefinition(
        "NOTE003",
        Severity.ERROR,
        "Field count mismatch",
        "A note's field count differs from its notetype definition.",
    ),
    RuleDefinition(
        "CLOZE001",
        Severity.ERROR,
        "Cloze note has no deletion",
        "A cloze notetype note contains no supported {{cN::...}} marker.",
    ),
    RuleDefinition(
        "CLOZE002",
        Severity.ERROR,
        "Cloze cards and markers disagree",
        "The card ordinals generated for a note do not match its cloze marker numbers.",
    ),
    RuleDefinition(
        "TEMPLATE001",
        Severity.ERROR,
        "Unknown template field",
        "A card template references a field that its notetype does not define.",
    ),
    RuleDefinition(
        "TEMPLATE002",
        Severity.WARNING,
        "Template front has no field",
        "A normal card template front does not reference any known note field.",
    ),
    RuleDefinition(
        "MEDIA001",
        Severity.ERROR,
        "Mapped media member is missing",
        "The media map points to an archive member that does not exist.",
    ),
    RuleDefinition(
        "MEDIA002",
        Severity.ERROR,
        "Media hash mismatch",
        "The unpacked media SHA-1 differs from the modern media map.",
    ),
    RuleDefinition(
        "MEDIA003",
        Severity.ERROR,
        "Media size mismatch",
        "The unpacked media size differs from the modern media map.",
    ),
    RuleDefinition(
        "MEDIA004",
        Severity.ERROR,
        "Unsafe or non-portable media filename",
        "A media filename is unsafe, non-normalized, or incompatible across common clients.",
    ),
    RuleDefinition(
        "MEDIA005",
        Severity.ERROR,
        "Referenced media is missing",
        "A note or template references a local media filename absent from the package.",
    ),
    RuleDefinition(
        "MEDIA006",
        Severity.INFO,
        "Unused media",
        "A mapped media file is not referenced by any note, template, or stylesheet.",
    ),
    RuleDefinition(
        "MEDIA007",
        Severity.WARNING,
        "Colliding media filenames",
        "Media filenames collide after Unicode normalization and case folding.",
    ),
    RuleDefinition(
        "MEDIA008",
        Severity.ERROR,
        "Media payload could not be verified",
        "A mapped media payload could not be decompressed or read completely.",
    ),
    RuleDefinition(
        "SHARE001",
        Severity.WARNING,
        "Learning progress included",
        "A shared-deck package contains review history or non-new scheduling state.",
    ),
)

RULE_BY_ID = {rule.id: rule for rule in RULES}
_CLOZE_RE = re.compile(r"\{\{c(\d+)(?:-(\d+))?::", re.IGNORECASE)
_MUSTACHE_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_SOUND_RE = re.compile(r"\[sound:([^\]\r\n]+)\]", re.IGNORECASE)
_CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_SPECIAL_TEMPLATE_FIELDS = {
    "card",
    "deck",
    "frontside",
    "subdeck",
    "tags",
    "type",
}
_MAX_CLOZE_RANGE = 999
_DUPLICATE_GROUP_MINIMUM = 2


class _MediaHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: list[str] = []

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if value is None:
                continue
            lowered = key.lower()
            if lowered in {"src", "poster", "data"}:
                self.values.append(value)
            elif lowered == "srcset":
                self.values.extend(
                    candidate.strip().split(maxsplit=1)[0]
                    for candidate in value.split(",")
                    if candidate.strip()
                )


def _clean_media_reference(value: str) -> str | None:
    candidate = unquote(html.unescape(value.strip().strip("'\"")))
    lowered = candidate.lower()
    if (
        not candidate
        or "{{" in candidate
        or candidate.startswith(("#", "//"))
        or lowered.startswith(("data:", "http:", "https:", "file:", "javascript:"))
    ):
        return None
    return candidate.split("?", 1)[0].split("#", 1)[0]


def media_references(value: str) -> frozenset[str]:
    parser = _MediaHTMLParser()
    with suppress(AssertionError, ValueError):
        parser.feed(value)
    candidates = list(parser.values)
    candidates.extend(match.group(1) for match in _SOUND_RE.finditer(value))
    candidates.extend(match.group(2) for match in _CSS_URL_RE.finditer(value))
    return frozenset(
        cleaned
        for candidate in candidates
        if (cleaned := _clean_media_reference(candidate)) is not None
    )


def _normalize_first_field(value: str) -> str:
    text = _TAG_RE.sub(" ", value)
    text = _SOUND_RE.sub(" ", text)
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    normalized = " ".join(text.split()).casefold()
    references = sorted(media_references(value))
    if references:
        normalized += " " + " ".join(f"<media:{name.casefold()}>" for name in references)
    return normalized.strip()


def _cloze_ordinals(fields: tuple[str, ...]) -> frozenset[int]:
    ordinals: set[int] = set()
    for value in fields:
        for match in _CLOZE_RE.finditer(value):
            start = int(match.group(1))
            end = int(match.group(2) or start)
            if start < 1 or end < start or end - start > _MAX_CLOZE_RANGE:
                continue
            ordinals.update(range(start - 1, end))
    return frozenset(ordinals)


def _template_fields(value: str) -> frozenset[str]:
    fields: set[str] = set()
    for match in _MUSTACHE_RE.finditer(value):
        token = match.group(1).strip()
        if token.startswith("!"):
            continue
        token = token.lstrip("#^/")
        if ":" in token:
            token = token.rsplit(":", 1)[1]
        token = token.strip()
        if token and token.casefold() not in _SPECIAL_TEMPLATE_FIELDS:
            fields.add(token)
    return frozenset(fields)


def _finding(
    settings: Settings,
    rule_id: str,
    *,
    message: str,
    location: str,
    evidence: str,
    remediation: str,
    properties: dict[str, object] | None = None,
) -> Finding | None:
    if rule_id in settings.ignored_rules:
        return None
    rule = RULE_BY_ID[rule_id]
    return Finding(
        rule_id=rule_id,
        severity=settings.severity_overrides.get(rule_id, rule.default_severity),
        message=message,
        location=location,
        evidence=evidence,
        remediation=remediation,
        properties=properties or {},
    )


def _append(findings: list[Finding], finding: Finding | None) -> None:
    if finding is not None:
        findings.append(finding)


def _audit_database(snapshot: PackageSnapshot, settings: Settings, findings: list[Finding]) -> None:
    if snapshot.sqlite_check != ("ok",):
        _append(
            findings,
            _finding(
                settings,
                "PKG001",
                message="SQLite quick_check did not return 'ok'",
                location=snapshot.collection_member,
                evidence="; ".join(snapshot.sqlite_check),
                remediation="Re-export from a healthy Anki profile after running Tools > Check Database.",
            ),
        )

    note_ids = {note.id for note in snapshot.notes}
    for card in snapshot.cards:
        if card.note_id not in note_ids:
            _append(
                findings,
                _finding(
                    settings,
                    "DB001",
                    message=f"Card {card.id} points to missing note {card.note_id}",
                    location=f"cards/{card.id}",
                    evidence=f"nid={card.note_id}",
                    remediation="Run Tools > Check Database, remove the orphan, and re-export.",
                ),
            )
        if card.deck_id not in snapshot.decks:
            _append(
                findings,
                _finding(
                    settings,
                    "DB003",
                    message=f"Card {card.id} points to missing deck {card.deck_id}",
                    location=f"cards/{card.id}",
                    evidence=f"did={card.deck_id}",
                    remediation="Move the card to an existing deck in Anki and re-export.",
                ),
            )

    cards_by_note: dict[int, set[int]] = defaultdict(set)
    for card in snapshot.cards:
        cards_by_note[card.note_id].add(card.ordinal)
    duplicate_groups: dict[tuple[int, str], list[int]] = defaultdict(list)

    for note in snapshot.notes:
        notetype = snapshot.notetypes.get(note.notetype_id)
        if notetype is None:
            _append(
                findings,
                _finding(
                    settings,
                    "DB002",
                    message=f"Note {note.id} points to missing notetype {note.notetype_id}",
                    location=f"notes/{note.id}",
                    evidence=f"mid={note.notetype_id}",
                    remediation="Restore or change the note type in Anki, then re-export.",
                ),
            )
            continue
        if len(note.fields) != len(notetype.field_names):
            _append(
                findings,
                _finding(
                    settings,
                    "NOTE003",
                    message=f"Note {note.id} has {len(note.fields)} fields; "
                    f"{notetype.name} defines {len(notetype.field_names)}",
                    location=f"notes/{note.id}",
                    evidence=f"fields={len(note.fields)}, expected={len(notetype.field_names)}",
                    remediation="Use Change Note Type or repair the fields in Anki, then re-export.",
                ),
            )
        first = _normalize_first_field(note.fields[0] if note.fields else "")
        if not first:
            _append(
                findings,
                _finding(
                    settings,
                    "NOTE001",
                    message=f"Note {note.id} has an empty first field",
                    location=f"notes/{note.id}/fields/0",
                    evidence=f"notetype={notetype.name}",
                    remediation="Add a prompt or media reference to the first field, or delete the note.",
                ),
            )
        else:
            duplicate_groups[(note.notetype_id, first)].append(note.id)

        if notetype.kind == "cloze":
            markers = _cloze_ordinals(note.fields)
            if not markers:
                _append(
                    findings,
                    _finding(
                        settings,
                        "CLOZE001",
                        message=f"Cloze note {note.id} contains no cloze marker",
                        location=f"notes/{note.id}",
                        evidence=f"notetype={notetype.name}",
                        remediation="Add at least one {{c1::deletion}} or change the note type.",
                    ),
                )
            actual = frozenset(cards_by_note.get(note.id, set()))
            if markers and actual != markers:
                _append(
                    findings,
                    _finding(
                        settings,
                        "CLOZE002",
                        message=f"Cloze note {note.id} has marker/card mismatch",
                        location=f"notes/{note.id}",
                        evidence=f"marker ordinals={sorted(markers)}, card ordinals={sorted(actual)}",
                        remediation="Edit the cloze markers, run Empty Cards, and re-export.",
                        properties={
                            "marker_ordinals": sorted(markers),
                            "card_ordinals": sorted(actual),
                        },
                    ),
                )

    for (notetype_id, normalized), ids in sorted(duplicate_groups.items()):
        if len(ids) < _DUPLICATE_GROUP_MINIMUM:
            continue
        notetype_name = snapshot.notetypes[notetype_id].name
        sample = normalized[:120]
        _append(
            findings,
            _finding(
                settings,
                "NOTE002",
                message=f"{len(ids)} notes in {notetype_name} share the same first field",
                location=f"notetypes/{notetype_id}",
                evidence=f"notes={ids[:20]}, normalized={sample!r}",
                remediation="Review with Anki's Find Duplicates tool and merge or distinguish the notes.",
                properties={"note_ids": ids, "normalized_sample": sample},
            ),
        )


def _audit_templates(
    snapshot: PackageSnapshot, settings: Settings, findings: list[Finding]
) -> None:
    for notetype in snapshot.notetypes.values():
        known = set(notetype.field_names)
        for template in notetype.templates:
            question_fields = _template_fields(template.question_format)
            all_fields = question_fields | _template_fields(template.answer_format)
            for unknown in sorted(all_fields - known):
                _append(
                    findings,
                    _finding(
                        settings,
                        "TEMPLATE001",
                        message=f"Template {template.name} references unknown field {unknown!r}",
                        location=f"notetypes/{notetype.id}/templates/{template.ordinal}",
                        evidence=f"known fields={list(notetype.field_names)}",
                        remediation="Correct the template field name in Anki's Cards editor.",
                    ),
                )
            if notetype.kind == "normal" and not (question_fields & known):
                _append(
                    findings,
                    _finding(
                        settings,
                        "TEMPLATE002",
                        message=f"Template {template.name} front references no known field",
                        location=f"notetypes/{notetype.id}/templates/{template.ordinal}/front",
                        evidence=f"front fields={sorted(question_fields)}",
                        remediation="Add a note field to the front template or remove the card template.",
                    ),
                )


def _all_media_references(snapshot: PackageSnapshot) -> dict[str, list[str]]:
    references: dict[str, list[str]] = defaultdict(list)
    for note in snapshot.notes:
        for ordinal, value in enumerate(note.fields):
            for name in media_references(value):
                references[name].append(f"notes/{note.id}/fields/{ordinal}")
    for notetype in snapshot.notetypes.values():
        for name in media_references(notetype.css):
            references[name].append(f"notetypes/{notetype.id}/css")
        for template in notetype.templates:
            for side, value in (
                ("front", template.question_format),
                ("back", template.answer_format),
            ):
                for name in media_references(value):
                    references[name].append(
                        f"notetypes/{notetype.id}/templates/{template.ordinal}/{side}"
                    )
    return references


def _audit_media(snapshot: PackageSnapshot, settings: Settings, findings: list[Finding]) -> None:
    names = {entry.name for entry in snapshot.media if entry.present}
    collisions: dict[str, list[str]] = defaultdict(list)
    for entry in snapshot.media:
        location = f"media/{entry.index}:{entry.name}"
        collisions[unicodedata.normalize("NFC", entry.name).casefold()].append(entry.name)
        if not entry.present:
            _append(
                findings,
                _finding(
                    settings,
                    "MEDIA001",
                    message=f"Media map entry {entry.index} is missing from the archive",
                    location=location,
                    evidence=f"filename={entry.name!r}",
                    remediation="Run Tools > Check Media, restore the file, and re-export with media.",
                ),
            )
        if not entry.filename_safe:
            _append(
                findings,
                _finding(
                    settings,
                    "MEDIA004",
                    message=f"Media filename is unsafe or non-portable: {entry.name!r}",
                    location=location,
                    evidence="Expected one NFC-normalized basename valid on Windows, macOS, and Linux.",
                    remediation="Rename the media in Anki and update all references before re-exporting.",
                ),
            )
        if entry.error and entry.present:
            _append(
                findings,
                _finding(
                    settings,
                    "MEDIA008",
                    message=f"Could not verify media payload {entry.name!r}",
                    location=location,
                    evidence=entry.error,
                    remediation="Re-add the media file in Anki and export the package again.",
                ),
            )
        if (
            entry.declared_sha1 is not None
            and entry.actual_sha1 is not None
            and entry.declared_sha1 != entry.actual_sha1
        ):
            _append(
                findings,
                _finding(
                    settings,
                    "MEDIA002",
                    message=f"Media hash differs for {entry.name!r}",
                    location=location,
                    evidence=f"declared={entry.declared_sha1}, actual={entry.actual_sha1}",
                    remediation="Replace the damaged media and export the deck again.",
                ),
            )
        if (
            entry.declared_size is not None
            and entry.actual_size is not None
            and entry.declared_size != entry.actual_size
        ):
            _append(
                findings,
                _finding(
                    settings,
                    "MEDIA003",
                    message=f"Media size differs for {entry.name!r}",
                    location=location,
                    evidence=f"declared={entry.declared_size}, actual={entry.actual_size}",
                    remediation="Replace the damaged media and export the deck again.",
                ),
            )

    for variants in collisions.values():
        unique = sorted(set(variants))
        if len(variants) > 1:
            _append(
                findings,
                _finding(
                    settings,
                    "MEDIA007",
                    message="Media filenames collide across case-insensitive clients",
                    location="media",
                    evidence=", ".join(repr(name) for name in unique),
                    remediation="Give every media file a case-insensitively unique filename.",
                    properties={"filenames": unique},
                ),
            )

    references = _all_media_references(snapshot)
    for name, locations in sorted(references.items()):
        if name not in names:
            _append(
                findings,
                _finding(
                    settings,
                    "MEDIA005",
                    message=f"Referenced media is absent: {name!r}",
                    location=locations[0],
                    evidence=f"referenced from {len(locations)} location(s)",
                    remediation="Add the media to Anki or remove the stale reference, then re-export.",
                    properties={"locations": locations[:100]},
                ),
            )
    unused = sorted(name for name in names if name not in references and not name.startswith("_"))
    if unused:
        _append(
            findings,
            _finding(
                settings,
                "MEDIA006",
                message=f"{len(unused)} mapped media file(s) are unused",
                location="media",
                evidence=", ".join(repr(name) for name in unused[:20]),
                remediation="Review with Tools > Check Media and remove only files you no longer need.",
                properties={"count": len(unused), "sample": unused[:100]},
            ),
        )


def audit(snapshot: PackageSnapshot, settings: Settings) -> AuditReport:
    """Apply every rule to one fully loaded package."""

    findings: list[Finding] = []
    _audit_database(snapshot, settings, findings)
    _audit_templates(snapshot, settings, findings)
    _audit_media(snapshot, settings, findings)

    for member in snapshot.unmapped_media_members:
        _append(
            findings,
            _finding(
                settings,
                "PKG002",
                message=f"Archive member {member!r} is not mapped",
                location=member,
                evidence="The member is not metadata, the collection, or a media-map entry.",
                remediation="Re-export from Anki instead of manually editing the APKG archive.",
            ),
        )

    if settings.profile == "shared":
        scheduled_cards = sum(
            1
            for card in snapshot.cards
            if card.repetitions or card.lapses or card.interval or card.card_type != 0
        )
        if snapshot.review_count or scheduled_cards:
            _append(
                findings,
                _finding(
                    settings,
                    "SHARE001",
                    message="Shared-deck profile found learning progress",
                    location=snapshot.collection_member,
                    evidence=f"revlog={snapshot.review_count}, scheduled_cards={scheduled_cards}",
                    remediation="Export again with 'Include scheduling information' disabled, "
                    "or use --profile backup when progress is intentional.",
                    properties={
                        "review_count": snapshot.review_count,
                        "scheduled_cards": scheduled_cards,
                    },
                ),
            )

    findings.sort(key=lambda item: (-int(item.severity), item.rule_id, item.location, item.message))
    return AuditReport(
        source=snapshot.path.name,
        sha256=snapshot.sha256,
        package_version=snapshot.package_version,
        schema_version=snapshot.schema_version,
        counts={
            "notes": len(snapshot.notes),
            "cards": len(snapshot.cards),
            "notetypes": len(snapshot.notetypes),
            "decks": len(snapshot.decks),
            "media": len(snapshot.media),
            "reviews": snapshot.review_count,
            "archive_members": snapshot.archive_member_count,
            "archive_uncompressed_bytes": snapshot.archive_uncompressed_bytes,
        },
        findings=tuple(findings),
        ignored_rules=tuple(sorted(settings.ignored_rules)),
    )
