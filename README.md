<p align="center">
  <img src="docs/assets/banner.svg" alt="kaizen-flow: a loop of SP, michi and Kaizen" width="100%">
</p>

<p align="center">
  <img src="docs/assets/mascot.svg" alt="Michi, the kaizen-flow mascot: a violet cat whose tail loops into an upward cycle" width="160">
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

## Documentation

| Doc | Contents |
|---|---|
| [Use cases](docs/use-cases.md) | "I want to..." recipes for install, usage, stories and handoff |
| [Commands](docs/commands.md) | every `kaizen` command, option and workflow script |
| [Agent commands](docs/agent-commands.md) | `/sp`, `/michi`, `/one-shot`, `/sp-handoff` and the michi cycle |
| [Usage and cost](docs/usage-and-cost.md) | transcripts read, prices file, reports |
| [Config](docs/config.md) | `kaizen.config.json` and project folders |
| [Handoff](docs/handoff.md) | fresh-context handoff, backends, CLI vs desktop app |

Quickstart:

```sh
kaizen init --harness codex
python scripts/sp-new.py --project _default --slug login --priority P2   # write a story
kaizen usage --days 30                                                  # what it cost
```

## Known limits

- The Codex transcript parser follows the rollout format (`event_msg` / `token_count`, `last_token_usage`) and is tested with synthetic fixtures; if your Codex version logs usage differently, open an issue with an anonymised sample.
- Codex and `agents-md` run without the context-guard hook (degraded on purpose: `context-guard.py` only reads Claude transcripts and this repo does not wire Codex hooks it cannot verify on your version). The `AGENTS.md` block tells the agent to run the handoff by hand when the context gets long, and `kaizen doctor` prints that notice. If your Codex version has hooks, you can point one at a script that reads its rollout; contributions welcome.
- Cursor, Gemini CLI, opencode and similar are supported only through the `agents-md` fallback.
- The `new conversation` command used by the Codex handoff (`/new`) is an assumption to verify on your version.

## License

MIT. See [LICENSE](LICENSE) and [CONTRIBUTING](CONTRIBUTING.md).
