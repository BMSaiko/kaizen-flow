# Agent commands

Typed inside Claude Code / Codex, not in the shell. These are skills and prompt files, not Python; the Python scripts in [commands](commands.md) are what they call. In Codex, if your version has no slash commands, say the same words ("run the michi skill on this story") and the agent follows `.agents/skills/<name>/SKILL.md`. The skill text is in Portuguese; the agent answers in your language.

| Command | Arguments | What it does |
|---|---|---|
| `/sp [topic]` | topic of the story | Builds a **Super Prompt** (SP = one user story with 8 fixed sections: role, context, objective, success criteria, constraints, seams, steps, done-when). Chains brainstorm, SWOT, grill-me and deep research, then writes it to `sp/TODO` with `sp-new.py`. |
| `/michi [--auto] <idea or SP file>` | an idea, or the path of an SP | Runs the whole improvement cycle on one story. |
| `/sp-list [flags]` | same flags as `sp-list.py` | Lists open stories, then offers a picker to start one. |
| `/sp-handoff [slug]` | optional slug | Logs progress in the story in Doing, prints the `/michi <path>` to resume, and (if you say yes) clears the context and resumes in the same pane. |
| `/handoff [slug]` | optional short name | Like `/sp-handoff`, for a free conversation with no story: writes an ephemeral handoff (`handoff.py --write`), and (if you say yes) clears the context; the new session runs `handoff.py --consume`, which prints and deletes it. |
| `/sp-fila [--dry-run] [--max N] [--ate HH:MM] [--projeto P] [--programa SLUG]` | optional limits | Runs the eligible stories in sequence (`modo: auto`, `gates:` set, dependencies met), each in a clean session; stops on the first failure and writes a report. `--programa` runs only a parent story's tree, bounded by its `orcamento_horas`/`orcamento_usd`/`orcamento_requests`; on a stop it appends `## Progresso` to the parent so the next run resumes. |
| `/grill-me`, `/dr`, `/dp`, `/da`, `/brainstorm`, `/swot` | topic | The building blocks michi chains; usable alone. |

## The michi cycle

Stop after any step, resume later.

| # | Phase | Output |
|---|---|---|
| 1 | Grill (`/grill-me`) | what, why and shape agreed |
| 2 | Deep research (`/dr`) | where the change lands, constraints, risks |
| 3 | Deep planning (`/dp`) | 3-7 TDD-shaped phases, audit table, risks |
| 4 | Deep acting (`/da`) | implementation phase by phase, with a proof per phase (screenshot, real call, output) saved in `proofs/` |
| 5 | Gates | build, tests, lint, e2e, plus the `/harden` gate when that skill is installed (not shipped in `core/`); every command and rc recorded; proof of done before the story moves to Done |
| 6 | Report | what changed, what was verified, real difficulties, what is open; no commit |
| 7 | Reflect | friction found and a proposed fix to the workflow itself; you apply it |
| 8 | Commit proposal | one conventional message; nothing is committed or pushed until you confirm |

A Super Prompt given as input skips phases 1-2. Say "skip <phase>" or "go to DA" to jump. If you say the work is wrong or broken, michi asks which phase failed and restarts there (default: grill).

## michi options

| Form | Effect |
|---|---|
| `/michi <idea>` | full cycle from the grill |
| `/michi <path/to/sp.md>` | start from an existing story (moved to Doing with `sp-move.py`); with no `--auto` and no `mode:` it asks once "with or without auto?" (default: without) |
| `/michi --auto <sp>` (or `mode: auto` in the front matter) | no questions (no start-up prompt): local commit, `sp-move done` on its own; never pushes |
| `/michi help` | usage and supplementary skills |
| `skip <phase>`, `go to DA` | jump phases (`skip harden` skips the optional `/harden` gate) |

Typical flow: `/sp login page` (write the story) → `/michi <path to the story>` (do it) → review the report → confirm the commit. When the context fills up, `/sp-handoff` moves to a fresh one without losing the thread.
