<p align="center">
  <img src="docs/assets/banner.svg" alt="kaizen-flow: a loop of SP, michi and Kaizen" width="100%">
</p>

# kaizen-flow

A small workflow for working with coding agents:

- **SP** (Super Prompt): a user story in 8 fixed sections (role, context, objective, success criteria, constraints, seams, steps, done-when).
- **michi**: the cycle that executes an SP: research, plan (TDD-shaped), act, gates, report, reflect, commit proposal.
- **Kaizen**: every cycle ends with a reflect step, so the workflow gets cheaper and sharper each time.
- **Usage analysis**: tokens and API-equivalent cost per day, session, model and 5 h window, from your local transcripts (metrics only, never conversation content).

Works with **Claude Code** and **Codex CLI** (plus any harness that reads `AGENTS.md`). Node stdlib and Python stdlib only; no telemetry.

## Install

Requirements: Node >= 18, Python 3.

```sh
git clone <this repo> && cd kaizen-flow && npm link   # or: npx kaizen-flow ... once published
cd your-project
kaizen init --harness codex     # or: claude | agents-md
kaizen doctor --harness codex   # exits non-zero if something is missing
```

`init` never overwrites existing files: anything already there is kept and reported.

## Using it with Codex: Codex sets up the Codex-specific parts

The package ships a neutral core and an adapter per harness. For Codex, `kaizen init --harness codex` only drops the neutral material in the project:

- skills in `.agents/skills/`, prompts in `.kaizen/commands/`, helper scripts in `scripts/`;
- a marked block appended to `AGENTS.md` that tells the agent how the workflow works.

**Everything else that is specific to Codex is done by Codex itself**, in your project, on your machine: wiring the prompts into your Codex setup (`~/.codex/prompts`, `config.toml`, approvals and sandbox settings), and mapping Claude-only ideas (hooks, slash commands) to what your Codex version supports. This is deliberate: Codex knows its own installed version and configuration better than this repo can, and the repo does not edit files outside your project.

The easiest way is to let Codex do the install. Open Codex in your project and say:

> Install kaizen-flow for Codex: clone it, run `kaizen init --harness codex`, then read the `AGENTS.md` block it added and set up whatever is Codex-specific (prompts, config, approvals) for my setup. Finish with `kaizen doctor --harness codex`. The install is only complete when `kaizen doctor --harness codex` exits 0: while it does not, run `kaizen doctor --harness codex --fix` (restores what is missing, never overwrites) and re-run `doctor`, repeating until it exits 0. Then tell me what you set up outside the project.

If you prefer to do it by hand, read `AGENTS.md` after `init` and follow the block.

## Use cases

| I want to... | Run | You get |
|---|---|---|
| Start a project with the Kaizen workflow | `kaizen init --harness codex` | skills, prompts, `sp-*` scripts, an `AGENTS.md` block; existing files are kept |
| Check the install is healthy (CI, new machine) | `kaizen doctor --harness codex` | rc 0 when complete, rc 1 and a list of what is missing |
| Repair a broken or partial install | `kaizen doctor --harness codex --fix` | missing pieces restored, nothing overwritten |
| See what my agents cost this month | `kaizen usage --days 30` | totals by day, model, session and 5 h window (API-equivalent USD) |
| Compare Claude and Codex spend | `kaizen usage --source claude,codex` | one table across both transcript stores |
| Keep a weekly record | `kaizen report --week 2026-W42` | a metrics-only Markdown note in `reportsDir` |
| Price a model not in the bundled table | add it to your prices file, set `"prices"` in `kaizen.config.json` | cost instead of `n/a` |
| List my open stories | `kaizen status` | pending SPs by status and priority |
| Cost of one period only | `kaizen usage --since 2026-10-01` | same tables from that date |
| Show only one harness | `kaizen usage --source codex --top 10` | Codex only, top 10 sessions |
| Read transcripts copied from another machine | `kaizen usage --codex-root ./backup/sessions` | totals from that folder |
| Preview a weekly report without writing | `kaizen report --week 2026-W42 --print` | Markdown on stdout |
| Write reports somewhere else | `kaizen report --out docs/usage` | `docs/usage/YYYY-WNN.md` |
| Plan a feature as a story | `python scripts/sp-new.py --project app --slug login --priority P2` | an empty 8-section story in `sp/TODO` |
| Plan a feature with dependent children | `python scripts/sp-new.py --project app --program billing --children "api,ui:api" --priority P2` | parent + two children, `ui` waits for `api` |
| Start and finish a story | `python scripts/sp-move.py login doing` / `done --next` | story moves folders; `--next` opens the next child |
| Check stories are well-formed | `python scripts/sp-validate.py path/to/story.md` | rc 1 if a section is missing |
| Keep CI honest about leaks | `kaizen audit .` | rc 1 if personal data is found |
| See what a handoff would do | `python scripts/sp-handoff.py --launch path/to/story.md --dry-run` | the commands, nothing executed |
| Move to a fresh context mid-story | `sp-handoff` | resume command injected in the pane, or copied to the clipboard |

Bad input (unknown harness, invalid `--since`/`--week`/`--days`, malformed prices or `settings.json`) stops with a one-line message and a non-zero exit; unreadable transcript lines or files are skipped, never fatal.

## CLI vs desktop app

| | CLI | Desktop app |
|---|---|---|
| Install | `kaizen init` writes project files | same files; the apps read the project (`.claude/`, `AGENTS.md`, Codex config) |
| Handoff to a fresh context (`sp-handoff`) | injects the clear-context and resume command into the current WezTerm/tmux pane | no pane to inject into: the resume command is copied to the clipboard and printed |
| `kaizen doctor` | prints `handoff: cli (wezterm\|tmux)` | prints `handoff: app (clipboard)` |

## Commands

```sh
kaizen init [repo] [--harness claude|codex|agents-md]
kaizen doctor [repo] [--harness h] [--fix]
kaizen status [repo]                  # pending SPs
kaizen usage [--days N | --since YYYY-MM-DD] [--source claude,codex] [--top N]
kaizen report [--week YYYY-WNN] [--out DIR] [--print]
kaizen audit [dir]                    # fails if personal data leaks into the repo
```

### Command reference

`[repo]` defaults to the current directory. `--harness` defaults to `claude`. Errors stop with one line and a non-zero exit.

| Command | Option | Meaning |
|---|---|---|
| `kaizen init [repo]` | `--harness claude\|codex\|agents-md` | Which adapter to install. `claude`: `.claude/` skills, commands, hooks. `codex`: `.agents/skills/`, `.kaizen/commands/`, `AGENTS.md` block. `agents-md`: `AGENTS.md` block + scripts only. Never overwrites; re-running is safe. |
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

### Workflow scripts (installed in `scripts/`)

Run with `python scripts/<name>.py`. Roots come from `kaizen.config.json`.

| Script | Usage | Options |
|---|---|---|
| `sp-new.py` | create a story in `sp/TODO` | `--project P --priority P1..P3` (required), `--slug S`, `--parent SLUG`, `--depends-on A B`, `--program SLUG --children "a,b:a,c:a+b"` (parent + children; `b:a` = b depends on a) |
| `sp-list.py` | list pending stories | `--all` (include Done), `--status todo\|doing`, `--project P`, `--sort priority\|created\|status`, `--reverse`, `--flat`, `--tree`, `--tree-closed SLUG` (close checklist: rc 0 closed, 1 failures, 2 unknown slug) |
| `sp-move.py` | `<slug> todo\|doing\|done` | `--project P`, `--next` (with `done`: open the next eligible child) |
| `sp-validate.py` | `<file>...` | checks the 8-section contract, rc 1 on failure |
| `sp-organize.py` | tidy stories into program folders | `--project P`, `--apply` (default is a dry run) |
| `sp-handoff.py` | move the story to a fresh context | `--resolve [SLUG]` (find the story), `--write PATH [--file BODY]` (log progress), `--launch PATH` (clear context and resume), plus `--harness claude\|codex`, `--backend wezterm\|tmux\|clipboard`, `--pane ID`, `--dry-run` (print only), `--auto` (no questions; needs a story in Doing) |
| `doc-list.py` | `dr\|dp` | `--all` |
| `doc-move.py` | `dr\|dp <slug> todo\|doing\|done` | |

### Agent commands (typed inside Claude Code / Codex, not in the shell)

These are skills and prompt files, not Python. The Python scripts above are what they call. In Codex, if your version has no slash commands, say the same words ("run the michi skill on this story") and the agent follows `.agents/skills/<name>/SKILL.md`. The skill text is in Portuguese; the agent answers in your language.

| Command | Arguments | What it does |
|---|---|---|
| `/sp [topic]` | topic of the story | Builds a **Super Prompt** (SP = one user story with 8 fixed sections: role, context, objective, success criteria, constraints, seams, steps, done-when). Chains brainstorm, SWOT, grill-me and deep research, then writes it to `sp/TODO` with `sp-new.py`. |
| `/michi [--auto] <idea or SP file>` | an idea, or the path of an SP | Runs the whole improvement cycle on one story. |
| `/sp-list [flags]` | same flags as `sp-list.py` | Lists open stories, then offers a picker to start one. |
| `/sp-handoff [slug]` | optional slug | Logs progress in the story in Doing, prints the `/michi <path>` to resume, and (if you say yes) clears the context and resumes in the same pane. |
| `/one-shot <idea>` | the project idea | One long interview (25+ questions, hours available), then a tree of stories (parent, children, grandchildren) executed by michi without questions. |
| `/grill-me`, `/dr`, `/dp`, `/da`, `/brainstorm`, `/swot` | topic | The building blocks michi chains; usable alone. |

**The michi cycle** (stop after any step, resume later):

| # | Phase | Output |
|---|---|---|
| 1 | Grill (`/grill-me`) | what, why and shape agreed |
| 2 | Deep research (`/dr`) | where the change lands, constraints, risks |
| 3 | Deep planning (`/dp`) | 3-7 TDD-shaped phases, audit table, risks |
| 4 | Deep acting (`/da`) | implementation phase by phase, with a proof per phase (screenshot, real call, output) saved in `proofs/` |
| 5 | Gates | build, tests, lint, e2e; every command and rc recorded; proof of done before the story moves to Done |
| 6 | Report | what changed, what was verified, real difficulties, what is open; no commit |
| 7 | Reflect | friction found and a proposed fix to the workflow itself; you apply it |
| 8 | Commit proposal | one conventional message; nothing is committed or pushed until you confirm |

A Super Prompt given as input skips phases 1-2. Say "skip <phase>" or "go to DA" to jump. If you say the work is wrong or broken, michi asks which phase failed and restarts there (default: grill).

**michi options**

| Form | Effect |
|---|---|
| `/michi <idea>` | full cycle from the grill |
| `/michi <path/to/sp.md>` | start from an existing story (moved to Doing with `sp-move.py`) |
| `/michi --auto <sp>` (or `mode: auto` in the front matter) | no questions: local commit, `sp-move done` on its own, handoff with `--launch --auto`; never pushes |
| `/michi help` | usage and supplementary skills (five-whys, swot, ooda-loop, eisenhower-matrix) |
| `skip <phase>`, `go to DA` | jump phases |

Typical flow: `/sp login page` (write the story) → `/michi <path to the story>` (do it) → review the report → confirm the commit. When the context fills up, `/sp-handoff` moves to a fresh one without losing the thread.

### Usage and cost

`kaizen usage` reads Claude Code transcripts (`~/.claude/projects`) and Codex sessions (`~/.codex/sessions`) and prints totals by day, model, session and 5 h window. `kaizen report` writes the weekly version to `reports/usage/YYYY-WNN.md`.

Cost is the equivalent at API prices, a relative measure and not what a subscription charges. Prices live in `usage/prices.json` (Claude models); **add the OpenAI/GPT models you use** there, or point to your own file. A model with no price shows cost `n/a` and a warning; it never fails.

### `kaizen.config.json` (optional, project root)

```json
{
  "spRoot": "knowledge/projects/kaizen",
  "docsRoot": "knowledge/projects",
  "reportsDir": "reports/usage",
  "sources": ["claude", "codex"],
  "prices": "my-prices.json"
}
```

## Known limits

- The Codex transcript parser follows the rollout format (`event_msg` / `token_count`, `last_token_usage`) and is tested with synthetic fixtures; if your Codex version logs usage differently, open an issue with an anonymised sample.
- Codex has no hook system equivalent to Claude Code's: hook behaviours become instructions in `AGENTS.md`.
- Cursor, Gemini CLI, opencode and similar are supported only through the `agents-md` fallback.
- The `new conversation` command used by the Codex handoff (`/new`) is an assumption to verify on your version.

## License

MIT. See [LICENSE](LICENSE) and [CONTRIBUTING](CONTRIBUTING.md).
