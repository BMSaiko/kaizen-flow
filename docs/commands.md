# Command reference

`[repo]` defaults to the current directory. `--harness` defaults to `claude`. Errors stop with one line and a non-zero exit.

```sh
kaizen init [repo] [--harness claude|codex|agents-md]
kaizen doctor [repo] [--harness h] [--fix]
kaizen status [repo]                  # pending SPs
kaizen usage [--days N | --since YYYY-MM-DD] [--source claude,codex] [--top N]
kaizen report [--week YYYY-WNN] [--out DIR] [--print]
kaizen audit [dir]                    # fails if personal data leaks into the repo
```

| Command | Option | Meaning |
|---|---|---|
| `kaizen init [repo]` | `--harness claude\|codex\|agents-md` | Which adapter to install. `claude`: `.claude/` skills, commands, hooks. `codex`: `.agents/skills/`, `.kaizen/commands/`, `AGENTS.md` block. `agents-md`: `AGENTS.md` block + scripts only. Never overwrites; re-running is safe. Also creates the example project folder `knowledge/projects/kaizen/_default/{sp,dr,dp}/{TODO,Doing,Done}`. |
| `kaizen doctor [repo]` | `--harness h` | Checks the install for that harness, that Python 3 runs the scripts, and that every SP has the 8 sections. Prints `handoff: cli\|app (backend)`. rc 0 = ok. |
| | `--fix` | Restores what is missing (same as `init`, nothing overwritten), then re-checks. |
| `kaizen status [repo]` | | Lists all SPs (TODO, Doing, Done) grouped by program. |
| `kaizen usage` | `--days N` | Last N days (N > 0). |
| | `--since YYYY-MM-DD` | From that date. Wins over `--days`. |
| | `--source claude,codex` | Transcript stores to read (default: config `sources`, then both). |
| | `--top N` | Sessions in the "top sessions" table (default 5). |
| | `--prices FILE` | Prices JSON (default: config `prices`, then the bundled file). |
| | `--repo DIR` | Where `kaizen.config.json` lives (default `.`). |
| | `--claude-root DIR`, `--codex-root DIR` | Override `~/.claude/projects` / `~/.codex/sessions` (other machines, backups, tests). |
| `kaizen report` | `--week YYYY-WNN` | ISO week to report (default: last closed week). |
| | `--out DIR` | Output folder (default: config `reportsDir`, then `reports/usage`). |
| | `--print` | Print instead of writing a file. |
| | `--source`, `--prices`, `--repo`, `--claude-root`, `--codex-root` | Same as `usage`. |
| `kaizen audit [dir]` | | Scans for personal data (names, local paths, wikilinks). rc 1 on any hit. |
| `kaizen sync` | | Maintainers only: refreshes `core/` from the author's vault. Not needed by users. |

## Workflow scripts (installed in `scripts/`)

Run with `python scripts/<name>.py`. Roots come from [`kaizen.config.json`](config.md).

| Script | Usage | Options |
|---|---|---|
| `sp-new.py` | create a story in `sp/TODO` | `--project P --priority P1..P3` (required; the project folder must exist, `init` creates `_default`), `--slug S`, `--parent SLUG`, `--depends-on A B`, `--program SLUG --children "a,b:a,c:a+b"` (parent + children; `b:a` = b depends on a) |
| `sp-list.py` | list pending stories | `--all` (include Done), `--status todo\|doing`, `--project P`, `--sort priority\|created\|status`, `--reverse`, `--flat`, `--tree`, `--tree-closed SLUG` (close checklist: rc 0 closed, 1 failures, 2 unknown slug) |
| `sp-move.py` | `<slug> todo\|doing\|done` | `--project P`, `--next` (with `done`: open the next eligible child) |
| `sp-validate.py` | `<file>...` | checks the 8-section contract (every section non-empty), rc 1 on failure |
| `sp-organize.py` | tidy stories into program folders | `--project P`, `--apply` (default is a dry run) |
| `sp-handoff.py` | move the story to a fresh context | see [handoff](handoff.md) |
| `doc-list.py` | `dr\|dp` | `--all` |
| `doc-move.py` | `dr\|dp <slug> todo\|doing\|done` | |

Bad input (unknown harness, invalid `--since`/`--week`/`--days`, malformed prices or `settings.json`) stops with a one-line message and a non-zero exit; unreadable transcript lines or files are skipped, never fatal.
