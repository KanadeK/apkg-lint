# Troubleshooting and repair

## Exit code 2: the package could not be inspected

### `package contains no supported Anki collection member`

The file is not a supported deck export or was manually repacked.

1. Open the source collection in a current Anki desktop version.
2. Select one deck, not **All Decks**.
3. Choose **File → Export → Anki Deck Package (.apkg)**.
4. Export again; do not rename a random ZIP to `.apkg`.
5. Re-run `apkg-lint`.

### `unsupported package metadata version` or `unsupported collection schema`

Anki has introduced a format newer than this release.

1. Record `apkg-lint --version` and the Anki version that exported the deck.
2. Do not force the file through a legacy parser.
3. Open an issue with a minimal, non-sensitive reproducer or the archive member
   names and schema number.
4. As a temporary compatibility route, re-export with **Support older Anki
   versions** enabled, then lint that artifact.

### `not valid zstd data`, protobuf failure, or SQLite read failure

The package is truncated, corrupt, or mislabeled.

1. Compare the file hash with the publisher's SHA-256 if available.
2. Download/copy it again.
3. If you own the deck, run **Tools → Check Database** and **Tools → Check
   Media**, then re-export.
4. If the failure persists, restore a known-good Anki backup before re-exporting.

### size, member-count, or compression-ratio limit

The default limit rejected an unusually large or suspicious package.

1. Inspect the source and exporter before raising limits.
2. Confirm the deck really needs its largest media files.
3. Increase only the specific value in `[limits]`.
4. Keep CI limits lower for untrusted pull requests.

Do not disable limits globally merely to accept one unexplained artifact.

## Rule repair map

### Database (`PKG001`, `DB001`–`DB003`)

1. Back up the Anki profile.
2. Run **Tools → Check Database**.
3. For missing decks, move affected cards to a real deck.
4. For missing notetypes, use **Change Note Type** or restore the notetype.
5. Re-export to a new filename.
6. Re-run the linter on the new file; do not patch the SQLite inside the APKG.

### Notes (`NOTE001`–`NOTE003`)

1. Open **Browse** and find the note ID from the report.
2. Add content to an empty first field.
3. Use **Notes → Find Duplicates** for `NOTE002`; review meaning before merging.
4. Use **Change Note Type** for a field-count mismatch.
5. Re-export and confirm the rule disappears.

### Cloze (`CLOZE001`, `CLOZE002`)

1. Open the reported note in **Browse**.
2. Ensure deletions use `{{c1::text}}`, `{{c2::text}}`, or a supported range.
3. Remove accidental/reversed ranges.
4. Run **Tools → Empty Cards** after edits.
5. Re-export and compare marker ordinals with card ordinals in the new report.

### Templates (`TEMPLATE001`, `TEMPLATE002`)

1. Open a note of the reported type.
2. Click **Cards…**.
3. Correct deleted/renamed fields on both sides.
4. Ensure a normal template front references at least one real note field.
5. Preview every template, then re-export.

### Media (`MEDIA001`–`MEDIA008`)

1. Run **Tools → Check Media**.
2. Restore missing files or remove stale field/template/CSS references.
3. Rename reserved, path-like, non-NFC, or case-colliding names.
4. Reinsert media through Anki so references update consistently.
5. Export with **Include media** enabled.
6. Re-run with payload verification enabled (the default).

Do not delete every `MEDIA006` file blindly. Leading-underscore assets can be
intentionally template-scoped, and custom JavaScript may create references the
static extractor cannot prove.

### Sharing state (`SHARE001`)

For a public/class deck, export again with **Include scheduling information**
disabled. For a personal transfer where progress is expected:

```bash
apkg-lint check backup.apkg --profile backup
```

Do not suppress `SHARE001` on a public artifact until you have confirmed the
review history and tags are safe to disclose.

## CI fails but local passes

1. Confirm CI uses `uv sync --all-groups --locked`.
2. Confirm the same APKG SHA-256 appears in both reports.
3. Check profile, config discovery, and `--fail-on`.
4. Avoid generating the APKG with timestamps or nondeterministic database
   content in a preceding step unless the difference is intentional.
5. Download the CI report artifact and compare rule IDs/evidence.

## Dependency or installation failure

```bash
uv cache clean zstandard
uv sync --all-groups --locked
```

If the platform has no compatible `zstandard` wheel, install a supported Python
3.11–3.13 build and retry. A source build may require a C compiler.

## Failed release attempt

1. Do not move the tag or claim completion while CI/Release is red.
2. Preserve `release/`, logs, and the failed run URL.
3. Fix the source, rerun `scripts/verify.py`, commit, and rerun
   `scripts/release_check.py`.
4. If no public release exists, create the corrected tag once.
5. If a release is already public, publish a new patch version instead of
   silently replacing consumed assets.
6. Download public assets and compare them to `SHA256SUMS`.
