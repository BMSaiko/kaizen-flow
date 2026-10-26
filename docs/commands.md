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
| `kaizen sync` | `--check`, `--stamp` | Maintainers only: refreshes `core/` from the author's vault. `--check` verifies without writing, `--stamp` stamps the build. Not needed by users. |

## Workflow scripts (installed in `scripts/`)

Run with `python scripts/<name>.py`. Roots come from [`kaizen.config.json`](config.md).

| Script | Usage | Options |
|---|---|---|
| `sp-new.py` | create a story in `sp/TODO` | `--project P --priority P1..P3` (required; the project folder must exist, `init` creates `_default`), `--slug S`, `--modo auto|manual` (michi mode stored as `modo:` in the front matter; default `manual`), `--commit`/`--push`/`--pr auto\|pergunta\|nunca` (authorizations stored in the front matter), `--restricoes "text"`, `--gate CMD` (repeatable, run by `sp-gates.py`), `--prova`, `--permitir CMD` (repeatable pre-approved command), `--decisao TEXT` (repeatable, goes to `## Decisões`), `--perfil cauteloso\|normal\|autonomo` with `--max-tentativas N`, `--max-requests N`, `--parar-se gate-falha,ambiguidade,ficheiro-fora-de-escopo,custo`, `--escopo GLOBS` / `--fora-de-escopo GLOBS` (comma-separated, no `..`), `--parent SLUG`, `--depends-on A B`, `--program SLUG --children "a,b:a,c:a+b"` (parent + children; `b:a` = b depends on a) |
| `sp-list.py` | list pending stories | `--all` (include Done), `--status todo\|doing`, `--project P`, `--sort priority\|created\|status`, `--reverse`, `--flat`, `--tree`, `--tree-closed SLUG` (close checklist: rc 0 closed, 1 failures, 2 unknown slug) |
| `sp-move.py` | `<slug> todo\|doing\|done` | `--project P`, `--next` (with `done`: open the next eligible child) |
| `sp-estado.py` | `<slug\|file.md>` | `--project P`. Read-only summary of one story in ≤30 lines: phase, steps, gates, dependencies, last `## Progresso` lines, branch and changed files |
| `sp-gates.py` | `<file.md>` | Runs the `gates:` from the front matter in order, stops at the first red. Each gate: `cmd`, optional `cwd`, `timeout` (default 300 s), `inputs` (globs; unchanged since the last green run = skipped). `--full` ignores the cache. rc 0 green or no gates, 1 red/timeout, 2 invalid or forbidden gate |
| `sp-fechar.py` | `<slug>` | Closes a story in one call: gates, context budget, `sp-move done`, then `COMMIT_*.md` with an explicit stage. Never commits or pushes. `--project P`, `--next`, `--msg "subject"`, `--sem-budget`, `--sem-commit`, `--commit-dir DIR`. rc 0 closed, 1 red gate/budget (story stays in Doing), 2 usage error |
| `sp-escalao.py` | propose the size of a task | `--project P --slug S --ficheiros N --horas H` (required), `--priority`, `--risco`, `--escalao` (override); prints the size (pequena, media, grande) and the matching `sp-new.py` command |
| `sp-metricas.py` | `<done-file.md>` | Appends one line per closed story (date, project, slug, hours, cost, reflects, gates on first try) to `knowledge/infra/reports/sp-metricas.md`; called by `sp-move.py` on `done`, no-op without that folder |
| `sp-validate.py` | `<file>...` | checks the 8-section contract (every section non-empty), rc 1 on failure |
| `sp-organize.py` | tidy stories into program folders | `--project P`, `--apply` (default is a dry run) |
| `sp-handoff.py` | move the story to a fresh context | see [handoff](handoff.md) |
| `sp-fila.py` | run eligible stories in sequence | `--dry-run` (order + exclusions), `--max N`, `--ate HH:MM`, `--projeto P`, `--programa SLUG` (tree + budget from the parent story), `--seguinte` (next step of a running queue), `--parar` (abandon the queue), `--orcamento N` (total requests) |
| `doc-list.py` | `dr\|dp` | `--all` |
| `doc-move.py` | `dr\|dp <slug> todo\|doing\|done` | |
| `kaizen_hooks.py` | `fire <event> --slug S --project P [--de X --para Y]` | runs the commands of `kaizen-hooks.json` for a michi/SP event; blocking ones run before (rc != 0 or timeout aborts), informative ones after (a failure only warns); the command comes from the config file, never from the SP |
| `skill-cut.py` | `<skill> <heading> <ref> --title T [--numbered]` | moves the blocks of a `SKILL.md` section into `references/`, leaving a one-line index per block; writes only if the block counts match |

Bad input (unknown harness, invalid `--since`/`--week`/`--days`, malformed prices or `settings.json`) stops with a one-line message and a non-zero exit; unreadable transcript lines or files are skipped, never fatal.
