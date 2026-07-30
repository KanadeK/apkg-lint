# Acceptance

These commands reproduce the release claims from a fresh clone.

## Prerequisites

- Git
- Python 3.11, 3.12, or 3.13
- [uv](https://docs.astral.sh/uv/)

## Install the locked development environment

```bash
uv sync --all-groups --locked
```

Expected: exit 0 and `apkg-lint==0.1.0` installed from the checkout.

## Full source gate

```bash
uv run python scripts/verify.py
```

Expected:

- Ruff format and lint pass;
- strict mypy passes for `src` and `scripts`;
- 49 tests pass;
- total branch-aware coverage is at least 90%;
- `clean-modern.apkg` exits 0 with no findings;
- `broken-legacy.apkg` exits 1 and reports the intentional rule set;
- tracked-text secret scan passes;
- wheel and source distribution build.

## Direct functional rehearsal

```bash
uv run apkg-lint check examples/clean-modern.apkg --fail-on warning
```

Expected: `PASS`, zero findings, exit 0.

```bash
uv run apkg-lint check examples/broken-legacy.apkg
```

Expected: `FAIL`, findings including `DB001`, `NOTE001`, `CLOZE002`,
`MEDIA005`, and `SHARE001`, exit 1.

PowerShell can display the exit code with:

```powershell
$LASTEXITCODE
```

Bash can display it with:

```bash
echo $?
```

## Reporter rehearsal

```bash
uv run apkg-lint check examples/broken-legacy.apkg \
  --format json --fail-on none --output report.json
uv run apkg-lint check examples/broken-legacy.apkg \
  --format html --fail-on none --output report.html
uv run apkg-lint check examples/broken-legacy.apkg \
  --format sarif --fail-on none --output report.sarif
```

Expected: three non-empty reports and exit 0 because `--fail-on none` is an
explicit report-only policy.

## Release assets

```bash
uv run python scripts/package_release.py
```

Expected `release/`:

```text
SHA256SUMS
apkg-lint-0.1.0-examples.zip
apkg-lint-report-v1.schema.json
apkg_lint-0.1.0-py3-none-any.whl
apkg_lint-0.1.0.tar.gz
```

Verify checksums:

```bash
sha256sum -c release/SHA256SUMS
```

On PowerShell:

```powershell
Get-Content release/SHA256SUMS | ForEach-Object {
  $parts = $_ -split "  ", 2
  if ((Get-FileHash "release/$($parts[1])" -Algorithm SHA256).Hash.ToLower() -ne $parts[0]) {
    throw "checksum mismatch: $($parts[1])"
  }
}
```

## Final committed release gate

After committing all intended files:

```bash
uv run python scripts/release_check.py
```

Expected:

- clean worktree;
- HEAD author and committer are
  `KanadeK <121669563+KanadeK@users.noreply.github.com>`;
- `git shortlog -sne HEAD` contains only the intended contributor identity;
- no `Co-authored-by` trailer;
- all required release/documentation files exist;
- two consecutive builds have identical file hashes;
- wheel contents are complete;
- wheel installs in a fresh virtual environment;
- the installed CLI passes the clean modern example.

Development-only diagnosis may use `--allow-dirty` or `--skip-clean-install`,
but neither option is used for a release claim.
