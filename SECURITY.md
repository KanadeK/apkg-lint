# Security policy

## Supported versions

Security fixes are provided for the latest release.

## Reporting

Please use GitHub's private vulnerability reporting for
`KanadeK/apkg-lint`. Do not open a public issue containing an exploit deck,
private study content, credentials, or personal information.

Include:

- `apkg-lint --version`;
- operating system and Python version;
- minimal synthetic reproducer if safe;
- expected versus observed resource use or trust-boundary behavior.

## Threat model

APKG input is untrusted. The linter defends against path traversal, duplicate
member ambiguity, symlink entries, excessive member counts, outer ZIP
expansion, nested zstd expansion, oversized control/database payloads,
non-portable media names, malformed protobuf, and malformed SQLite.

The CLI does not:

- extract members to archive-controlled paths;
- execute deck HTML, CSS, JavaScript, SQL, or add-ons;
- load SQLite extensions;
- write into the input package or a live Anki profile;
- make network requests.

Reports contain package SHA-256, internal IDs, media filenames, and short
evidence. Treat them as potentially sensitive.

## Dependency and release controls

- Runtime dependency range is locked for CI.
- Weekly CI audits the locked environment.
- Release artifacts are built twice and compared.
- `SHA256SUMS` is included with every release.
- Release history rejects unexpected author/committer identities and
  `Co-authored-by` trailers.
