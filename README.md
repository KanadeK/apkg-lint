# apkg-lint

[![CI](https://github.com/KanadeK/apkg-lint/actions/workflows/ci.yml/badge.svg)](https://github.com/KanadeK/apkg-lint/actions/workflows/ci.yml)
[![Security](https://github.com/KanadeK/apkg-lint/actions/workflows/security.yml/badge.svg)](https://github.com/KanadeK/apkg-lint/actions/workflows/security.yml)
[![Python 3.11–3.13](https://img.shields.io/badge/python-3.11%E2%80%933.13-3776AB)](https://www.python.org/)
[![MIT](https://img.shields.io/badge/license-MIT-161616)](LICENSE)

**Find broken Anki decks before your learners do.**

`apkg-lint` is a read-only, offline preflight and CI linter for Anki `.apkg`
files. It opens the package directly—without importing it into Anki—and checks
the ZIP container, SQLite collection, notes, cards, cloze markers, templates,
media, and accidental learning-progress disclosure.

```console
$ apkg-lint check pharmacology.apkg
apkg-lint 0.1.0

FAIL  pharmacology.apkg
  package=latest  schema=18  notes=842  cards=963  media=217

  ERROR MEDIA005  Referenced media is absent: 'renal-clearance.png'
    at: notes/1700123456789/fields/1
    evidence: referenced from 3 location(s)
    fix: Add the media to Anki or remove the stale reference, then re-export.

Summary: files=1, operational_errors=0, errors=1, warnings=0, info=0
```

[简体中文](README.zh-CN.md) ·
[Rules](docs/RULES.md) ·
[Acceptance](docs/ACCEPTANCE.md) ·
[Troubleshooting](docs/TROUBLESHOOTING.md) ·
[Example HTML report](examples/broken-report.html)

## Why this exists

Anki's built-in **Check Database** and **Check Media** are useful after a deck
has been imported into a profile. They are not a portable, reviewable preflight
for an exported package, and Anki's media check explicitly does not scan card
templates. Deck authors, course maintainers, and CI pipelines need a command
that can inspect the artifact they are about to publish.

The closest GitHub results found during the project research were a
bring-your-own-key LLM add-on that critiques card wording and a small Swift
project. Neither statically audits exported APKG structure, templates, media,
and sharing state. The reproducible search notes are in
[docs/RESEARCH.md](docs/RESEARCH.md).

## What it catches

| Layer | Checks |
| --- | --- |
| Package | unsafe paths, symlinks, duplicate members, ZIP bombs, missing collection, unmapped files |
| Database | SQLite integrity, supported schema, orphan cards, missing decks and notetypes |
| Notes | empty first fields, normalized duplicates, field-count drift |
| Cloze | missing deletions, multi-card ranges, marker/card ordinal mismatch |
| Templates | references to deleted fields, fronts that render no note field |
| Media | missing references, missing mapped files, zstd failures, SHA-1/size drift, unused files, cross-platform filename collisions |
| Sharing | review history or scheduled cards accidentally included in a shared deck |

Every finding includes a stable rule ID, evidence, an APKG-internal location,
and a repair instruction. The complete catalog is in
[docs/RULES.md](docs/RULES.md).

## Install

From the GitHub repository:

```bash
pipx install git+https://github.com/KanadeK/apkg-lint.git
```

Run without a persistent install:

```bash
uvx --from git+https://github.com/KanadeK/apkg-lint.git apkg-lint check deck.apkg
```

Or download the wheel from the
[latest GitHub Release](https://github.com/KanadeK/apkg-lint/releases/latest):

```bash
python -m pip install apkg_lint-0.1.0-py3-none-any.whl
```

Python 3.11–3.13 is supported on Windows, macOS, and Linux. `apkg-lint` has one
runtime dependency, `zstandard`, for Anki's current package format.

## Use

Inspect one package:

```bash
apkg-lint check deck.apkg
```

Inspect every APKG below a directory:

```bash
apkg-lint check releases/
```

Generate machine-readable and reviewable evidence:

```bash
apkg-lint check deck.apkg --format json  -o report.json
apkg-lint check deck.apkg --format sarif -o report.sarif
apkg-lint check deck.apkg --format html  -o report.html
```

Use backup semantics when scheduling information is intentional:

```bash
apkg-lint check profile-backup.apkg --profile backup
```

List the rules without opening a deck:

```bash
apkg-lint rules
apkg-lint rules --format json
```

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Every inspected package is below `--fail-on` |
| `1` | A finding met or exceeded `--fail-on` |
| `2` | Usage, configuration, input, or report-write failure |

The default gate is `--fail-on warning`. Use `--fail-on error`, `info`, or
`none` to match your release policy.

## Configure

Place `apkg-lint.toml` in the working directory or pass `--config`:

```toml
[apkg_lint]
profile = "shared"
fail_on = "warning"
verify_media = true
ignore = []

[severity]
MEDIA006 = "info"

[limits]
max_members = 100000
max_uncompressed_mb = 4096
max_database_mb = 2048
max_control_mb = 64
max_compression_ratio = 1000
```

Unknown keys and invalid values fail closed with exit code 2. The complete
sample is [examples/apkg-lint.toml](examples/apkg-lint.toml).

## GitHub Action

Commit the APKG or produce it in an earlier workflow step:

```yaml
name: Deck preflight
on: [push, pull_request]

jobs:
  lint-deck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: KanadeK/apkg-lint@v0.1.0
        with:
          path: dist/course.apkg
          profile: shared
          fail-on: warning
          format: sarif
          output: apkg-lint.sarif
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: apkg-lint-report
          path: apkg-lint.sarif
```

For high-assurance workflows, pin third-party actions to immutable commit SHAs.
This repository's own workflows do so.

## Format support

| APKG generation | Collection | Compression | Status |
| --- | --- | --- | --- |
| legacy v1 | `collection.anki2` | none | supported |
| legacy v2 | `collection.anki21` | none | supported |
| current v3 | `collection.anki21b` | zstd | supported |

Both legacy JSON and current protobuf notetype/media metadata are decoded.
Collection schemas 11 through 18 are accepted. See
[docs/FORMAT_SUPPORT.md](docs/FORMAT_SUPPORT.md) for the exact compatibility
contract and official Anki source references.

## Safety and privacy

- No network calls are made by the CLI.
- The input is opened read-only and never imported into a live Anki profile.
- The temporary SQLite copy is removed when inspection ends.
- Archive members are never extracted by their embedded path.
- Member counts, expanded sizes, database size, control payloads, filenames,
  symlinks, and compression ratios are bounded before deeper parsing.
- HTML output escapes deck-derived values.

APKG files can contain private study material. Reports intentionally include
filenames and short normalized evidence, so review them before publishing.
Security policy and threat boundaries are documented in [SECURITY.md](SECURITY.md).

## Development and verification

```bash
uv sync --all-groups --locked
uv run python scripts/verify.py
uv run python scripts/package_release.py
```

The gate runs format/lint/type checks, 51 positive and adversarial tests with
at least 90% branch-aware coverage, semantic example validation, clean/broken
CLI rehearsals, a secret scan, and package builds. The final release check also
verifies Git identity and history, reproducible assets, SHA-256 manifests, and
an isolated wheel install.

Exact acceptance commands and expected outcomes are in
[docs/ACCEPTANCE.md](docs/ACCEPTANCE.md). Failure-by-failure repair procedures
are in [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## Scope

`apkg-lint` is a package preflight, not an Anki replacement, scheduler, deck
generator, or AI writing critic. It does not modify decks. Findings are
structural and deterministic; they do not claim that a card is pedagogically
good.

This project is independent and is not affiliated with or endorsed by Anki or
Ankitects.

## License

[MIT](LICENSE)
