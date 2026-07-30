# Rule catalog

Rule IDs are stable API. Default severities can be changed in configuration;
rules can be ignored explicitly.

| Rule | Default | Meaning | Primary repair |
| --- | --- | --- | --- |
| `PKG001` | error | SQLite `quick_check` did not return `ok` | Run **Tools → Check Database**, restore if needed, re-export |
| `PKG002` | warning | Archive member is not collection metadata or mapped media | Re-export from Anki; do not hand-edit the ZIP |
| `DB001` | error | Card points to a missing note | Check database, remove orphan, re-export |
| `DB002` | error | Note points to a missing notetype | Restore/change notetype, re-export |
| `DB003` | error | Card points to a missing deck | Move card to an existing deck, re-export |
| `NOTE001` | error | First field has neither text nor media | Add a prompt/media or delete the note |
| `NOTE002` | warning | Same normalized first field occurs more than once in one notetype | Review **Find Duplicates**; merge or distinguish |
| `NOTE003` | error | Stored field count differs from notetype fields | Repair with **Change Note Type**, re-export |
| `CLOZE001` | error | Cloze note has no supported deletion | Add `{{c1::...}}` or change notetype |
| `CLOZE002` | error | Cloze marker numbers and generated card ordinals differ | Correct markers, run **Empty Cards**, re-export |
| `TEMPLATE001` | error | Template references an undefined field | Correct the field in **Cards…** |
| `TEMPLATE002` | warning | Normal template front references no defined note field | Add a field or remove the template |
| `MEDIA001` | error | Media map points to an absent numeric member | Restore file, run **Check Media**, include media on export |
| `MEDIA002` | error | Current-format media SHA-1 differs | Replace damaged media and re-export |
| `MEDIA003` | error | Current-format media size differs | Replace damaged media and re-export |
| `MEDIA004` | error | Filename is unsafe or non-portable | Rename in Anki and update references |
| `MEDIA005` | error | Note/template/CSS references absent media | Add media or remove stale reference |
| `MEDIA006` | info | Mapped non-underscore media has no discovered reference | Review **Check Media** before deleting |
| `MEDIA007` | warning | Filenames collide after NFC + case folding | Rename to cross-platform-unique names |
| `MEDIA008` | error | Mapped media cannot be decompressed/read | Re-add the file and re-export |
| `SHARE001` | warning | Shared profile contains reviews or scheduled cards | Export without scheduling or use backup profile |

## Configuration example

```toml
[apkg_lint]
ignore = ["MEDIA006"]

[severity]
NOTE002 = "error"
```

Ignoring a rule removes its findings and records the ignored ID in JSON/HTML
report metadata. Unknown rule IDs are accepted as policy placeholders but have
no effect until such a rule exists; CI reviewers should still review config
changes.
