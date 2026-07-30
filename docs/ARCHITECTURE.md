# Architecture

## Goal

Inspect an untrusted APKG artifact without importing it, executing deck content,
or modifying a live Anki profile. Produce deterministic findings that can be
reviewed by a person or gated in CI.

## Pipeline

```text
APKG path
  │
  ├─ archive guard
  │   ├─ member/path/symlink/duplicate checks
  │   └─ count, size, and compression-ratio limits
  │
  ├─ package adapter
  │   ├─ legacy v1/v2 JSON + raw SQLite/media
  │   └─ current v3 protobuf + zstd SQLite/media
  │
  ├─ read-only SQLite adapter
  │   ├─ schema 11–14 legacy models/decks
  │   └─ schema 15–18 normalized notetypes/templates/decks
  │
  ├─ immutable PackageSnapshot
  │
  ├─ deterministic rules
  │   ├─ database / note / cloze / template
  │   ├─ media references and payload evidence
  │   └─ shared-vs-backup policy
  │
  └─ text / JSON / HTML / SARIF
```

## Modules

| Module | Responsibility |
| --- | --- |
| `package.py` | ZIP trust boundary, APKG version selection, zstd and media payload verification |
| `protobuf.py` | Minimal forward-skipping protobuf wire decoder for four known message shapes |
| `database.py` | Read-only SQLite access and schema 11–18 adapters |
| `model.py` | Immutable package, finding, and report records |
| `rules.py` | Stable rule catalog and deterministic audit |
| `reporting.py` | Escaped human and machine reporters |
| `config.py` | Fail-closed TOML configuration and resource limits |
| `cli.py` | Discovery, exit-code policy, and report I/O |

## Trust boundaries

### Archive

Member paths are validated but never used as extraction destinations. Only the
selected collection is copied to a tool-created temporary filename. Media is
streamed from the archive. Duplicate names are rejected because choosing the
first or last entry would make evidence ambiguous.

### Compression

ZIP and nested zstd expansion are both considered. Outer member count, expanded
ZIP size, per-member ZIP ratio, database expansion, control-message expansion,
and aggregate verified media expansion are bounded.

### SQLite

The extracted database is opened with URI `mode=ro&immutable=1`.
`trusted_schema` is disabled. The `unicase` collation required by current Anki
schemas is provided locally. No extension loading or deck-provided SQL occurs.

### HTML

HTML inside note fields is parsed only to identify local media references. It
is never rendered by the linter. The standalone report escapes every
deck-derived value.

## Determinism

Reports omit timestamps, sort findings by severity/rule/location/message, sort
JSON keys, and use the package SHA-256 as identity. Release ZIP timestamps and
`SOURCE_DATE_EPOCH` are fixed. The release gate builds twice and compares every
asset hash.

## Extending rules

Add one `RuleDefinition` to `RULES`, implement the evidence in the appropriate
audit stage, add positive and negative fixtures, document the repair in
`docs/RULES.md`, and preserve the rule ID once released. New format semantics
must be sourced from official Anki code or documentation.
