# APKG format support

The compatibility contract is deliberately explicit. An unsupported format
fails with exit code 2 instead of being guessed.

## Package generations

| Generation | Detection | Collection | Media map | Payload compression |
| --- | --- | --- | --- | --- |
| legacy v1 | no `meta`; `collection.anki2` present | `collection.anki2` | JSON object | none |
| legacy v2 | no `meta`; `collection.anki21` present | `collection.anki21` | JSON object | none |
| current v3 | protobuf `meta.version = 3` | `collection.anki21b` | protobuf `MediaEntries` | zstd |

The mapping comes from Anki's official
[`meta.rs`](https://github.com/ankitects/anki/blob/main/rslib/src/import_export/package/meta.rs)
and
[`import_export.proto`](https://github.com/ankitects/anki/blob/main/proto/anki/import_export.proto).

## Collection schemas

Schemas 11 through 18 are supported.

- Schema 11–14 reads notetypes and decks from the legacy JSON columns in `col`.
- Schema 15–18 reads normalized `notetypes`, `fields`, `templates`, and `decks`.
- Template and notetype config blobs are decoded using the field numbers in
  Anki's official
  [`notetypes.proto`](https://github.com/ankitects/anki/blob/main/proto/anki/notetypes.proto).

The accepted upper bound follows the current package exporter, which selects
schema 18 for the latest package generation. When Anki introduces a newer
schema, `apkg-lint` will fail closed until fixtures and adapters are added.

## Media

Legacy maps associate numeric ZIP member names with logical filenames. Current
maps provide filename, declared uncompressed size, and SHA-1. Current media
members are individually zstd-compressed; the linter streams, expands, hashes,
and size-checks each mapped payload by default.

Reference extraction covers:

- HTML `src`, `srcset`, `poster`, and `data` attributes;
- Anki `[sound:filename]`;
- CSS `url(...)`;
- note fields, question templates, answer templates, and notetype CSS;
- percent-encoded filenames.

Remote/data/file/javascript URLs and dynamic `{{Field}}` URLs are not treated as
local filenames.

Anki's own media checker documents that it does not scan question or answer
templates, which is one reason this package-level check is useful:
[Anki Manual: Checking Media](https://docs.ankiweb.net/media.html#checking-media).

## Sharing state

The `shared` profile warns when `revlog` entries or non-new scheduling state are
present. Anki documents that shared packages normally exclude learning
progress, while progress is useful when moving between profiles:
[Anki Manual: Packaged Decks](https://docs.ankiweb.net/importing/packaged-decks.html)
and [Exporting](https://docs.ankiweb.net/exporting.html).

Use `--profile backup` when progress is intentional.

## Out of scope

- `.colpkg` full-collection replacement packages;
- a live `collection.anki2` beside a running Anki process;
- executing JavaScript or rendering card templates;
- evaluating pedagogical quality;
- repairing or rewriting packages;
- schema versions above 18 until implemented and tested.
