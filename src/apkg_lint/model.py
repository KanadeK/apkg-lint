"""Shared data structures used by extraction, rules, and reporters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any


class Severity(IntEnum):
    """Finding severity ordered from least to most important."""

    INFO = 10
    WARNING = 20
    ERROR = 30

    @classmethod
    def parse(cls, value: str) -> Severity:
        normalized = value.strip().upper()
        try:
            return cls[normalized]
        except KeyError as exc:
            choices = ", ".join(item.name.lower() for item in cls)
            raise ValueError(f"unknown severity {value!r}; choose one of: {choices}") from exc

    def label(self) -> str:
        return self.name.lower()


@dataclass(frozen=True)
class Finding:
    """A single actionable lint result."""

    rule_id: str
    severity: Severity
    message: str
    location: str
    evidence: str
    remediation: str
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.label()
        return data


@dataclass(frozen=True)
class NoteRecord:
    id: int
    guid: str
    notetype_id: int
    tags: str
    fields: tuple[str, ...]


@dataclass(frozen=True)
class CardRecord:
    id: int
    note_id: int
    deck_id: int
    ordinal: int
    card_type: int
    queue: int
    interval: int
    repetitions: int
    lapses: int


@dataclass(frozen=True)
class TemplateRecord:
    ordinal: int
    name: str
    question_format: str
    answer_format: str


@dataclass(frozen=True)
class NotetypeRecord:
    id: int
    name: str
    kind: str
    field_names: tuple[str, ...]
    templates: tuple[TemplateRecord, ...]
    css: str


@dataclass(frozen=True)
class MediaEntry:
    index: int
    name: str
    declared_size: int | None
    declared_sha1: str | None
    actual_size: int | None = None
    actual_sha1: str | None = None
    present: bool = True
    filename_safe: bool = True
    error: str | None = None


@dataclass(frozen=True)
class PackageSnapshot:
    path: Path
    sha256: str
    package_version: str
    collection_member: str
    schema_version: int
    sqlite_check: tuple[str, ...]
    notes: tuple[NoteRecord, ...]
    cards: tuple[CardRecord, ...]
    notetypes: dict[int, NotetypeRecord]
    decks: dict[int, str]
    media: tuple[MediaEntry, ...]
    mapped_media_members: frozenset[str]
    unmapped_media_members: tuple[str, ...]
    duplicate_members: tuple[str, ...]
    archive_member_count: int
    archive_uncompressed_bytes: int
    review_count: int


@dataclass(frozen=True)
class AuditReport:
    """Stable, serialization-friendly result for one package."""

    source: str
    sha256: str
    package_version: str
    schema_version: int
    counts: dict[str, int]
    findings: tuple[Finding, ...]
    ignored_rules: tuple[str, ...] = ()

    def summary(self) -> dict[str, int]:
        return {
            severity.label(): sum(1 for finding in self.findings if finding.severity is severity)
            for severity in reversed(tuple(Severity))
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "sha256": self.sha256,
            "package_version": self.package_version,
            "schema_version": self.schema_version,
            "counts": dict(sorted(self.counts.items())),
            "summary": self.summary(),
            "ignored_rules": list(self.ignored_rules),
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class RuleDefinition:
    id: str
    default_severity: Severity
    title: str
    description: str
