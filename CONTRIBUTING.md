# Contributing

Issues and focused pull requests are welcome.

## Before opening a change

1. Do not attach a private deck. Build a minimal synthetic reproducer.
2. For a format claim, link the relevant official Anki source or documentation.
3. Preserve released rule IDs and report schema fields.
4. Add both a passing case and an adversarial/failing case.

## Development

```bash
uv sync --all-groups --locked
uv run python scripts/verify.py
```

The same gate runs in CI. New code must remain typed, offline at runtime,
read-only toward input packages, and within the configured resource limits.

## Commit and pull request scope

- Keep unrelated changes separate.
- Explain user impact and evidence.
- Include the exact acceptance command.
- Update `docs/RULES.md` for rule behavior.
- Update `docs/FORMAT_SUPPORT.md` for format/schema behavior.
- Never commit real learner data, tokens, generated credentials, or private
  media.

By contributing, you agree that your contribution is licensed under MIT.
