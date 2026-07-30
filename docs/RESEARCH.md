# Research and non-duplication record

Research date: **2026-07-30**.

The goal was not to invent another generic developer dashboard or UI shell. The
workspace already contained tools for repository analysis, data drift, API
contracts, release evidence, game testing, local privacy scans, manuals, and
many other domains. No existing local project audits Anki/flashcard artifacts.

## Demand signals

- A 2026 analysis of 9,363 explicit software requests reported 698 in
  education/self-improvement and more than 640 requests specifically asking for
  offline-first or privacy-focused tools:
  [Reddit discussion and methodology summary](https://www.reddit.com/r/SaaS/comments/1q5lfur/i_analyzed_9300_i_wish_there_was_an_app_for_this/).
- Current Anki support threads continue to report duplicate cards and confusing
  cloze/card-generation failures:
  [duplicate cards, April 2026](https://forums.ankiweb.net/t/how-to-get-rid-of-multiple-duplicates-in-decks/69357),
  [duplicate cards, January 2026](https://forums.ankiweb.net/t/duplicate-cards/68163),
  and
  [cloze import failure](https://forums.ankiweb.net/t/errors-when-importing-a-deck-with-duplicate-cards/31433).
- Anki officially provides database and media checks, but the media check does
  not inspect question/answer templates:
  [Anki Manual](https://docs.ankiweb.net/media.html#checking-media).
- GitHub's own 2025/2026 trend analysis says fast feedback, deterministic
  environments, reproducibility, and clear contribution paths are winning
  developer adoption:
  [GitHub Blog](https://github.blog/news-insights/octoverse/what-the-fastest-growing-tools-reveal-about-how-software-is-being-built/).

These signals favor a local, deterministic artifact gate over an account-based
SaaS or an AI card generator.

## GitHub repository searches

Public GitHub repository search API results on the research date:

| Query | Total | Relevant result |
| --- | ---: | --- |
| [`anki linter`](https://api.github.com/search/repositories?q=anki%20linter) | 2 | One Ruff-rules deck generator; one BYOK LLM wording critic |
| [`anki deck checker`](https://api.github.com/search/repositories?q=anki%20deck%20checker) | 2 | Update notifier; small Swift project |
| [`apkg validator`](https://api.github.com/search/repositories?q=apkg%20validator) | 2 | AI/PDF deck generation pipelines |
| [`anki media checker`](https://api.github.com/search/repositories?q=anki%20media%20checker) | 0 | none |
| [`anki duplicate checker`](https://api.github.com/search/repositories?q=anki%20duplicate%20checker) | 0 | none |
| [`apkg audit`](https://api.github.com/search/repositories?q=apkg%20audit) | 0 | none |
| [`flashcard linter`](https://api.github.com/search/repositories?q=flashcard%20linter) | 2 | unrelated study-content pipelines |

Name search for `apkg-lint in:name` returned zero repositories.

Search counts are snapshots, not proof that no private, unindexed, or newly
created project exists. The defensible claim is narrower: no discovered public
repository combined offline APKG container hardening, schema-aware SQLite
checks, cloze/template analysis, current media verification, sharing-state
preflight, CI exit codes, and JSON/HTML/SARIF.

## Deliberate differentiation

| Existing category | What it does | `apkg-lint` boundary |
| --- | --- | --- |
| Anki Check Database | Repairs/checks an imported live collection | Reads a publishable APKG without import or mutation |
| Anki Check Media | Finds live-profile missing/unused media | Also verifies package mapping/payloads and scans templates/CSS |
| AI card critics | Judge wording using an API/model | No network or subjective pedagogy; deterministic structure only |
| Deck generators | Create cards/APKGs | Never authors or modifies a card |
| General ZIP/SQLite tools | Inspect containers/databases | Understands Anki versions, schemas, cloze, templates, media, scheduling |

## Star and discovery hypothesis

No project can guarantee stars. The practical discovery strategy is:

1. a searchable name and description containing `Anki`, `.apkg`, `linter`, and
   `offline`;
2. a zero-import `uvx`/`pipx` path;
3. a visible broken-package demo, actionable repairs, and stable rule IDs;
4. a reusable GitHub Action plus SARIF;
5. current and legacy format support sourced from official Anki code;
6. pinned CI, adversarial tests, reproducible Release assets, and contributor
   documentation.

This is a concrete adoption hypothesis, not a promise of star count or traffic.
