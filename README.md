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
kaizen doctor [repo] [--harness h]
kaizen status [repo]                  # pending SPs
kaizen usage [--days N | --since YYYY-MM-DD] [--source claude,codex] [--top N]
kaizen report [--week YYYY-WNN] [--out DIR] [--print]
kaizen audit [dir]                    # fails if personal data leaks into the repo
```

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
