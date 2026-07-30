# apkg-lint v0.1.0

The first public release adds an offline, read-only preflight for Anki `.apkg`
artifacts.

Highlights:

- current zstd/protobuf and legacy JSON APKG formats;
- collection schemas 11–18;
- actionable database, duplicate, cloze, template, media, and progress checks;
- text, JSON, HTML, and SARIF reports;
- reusable GitHub Action and CI-friendly exit codes;
- hostile-archive limits and no CLI network calls;
- 49 automated tests with more than 90% branch-aware coverage;
- wheel, source distribution, example bundle, JSON schema, and SHA-256 manifest.

Start without installing:

```bash
uvx --from git+https://github.com/KanadeK/apkg-lint.git apkg-lint check deck.apkg
```

Verify downloaded assets with `SHA256SUMS` before installation.
