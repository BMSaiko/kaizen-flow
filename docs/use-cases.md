# Use cases

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
| Plan a feature as a story | `python scripts/sp-new.py --project _default --slug login --priority P2` | an empty 8-section story in `sp/TODO` |
| Plan a feature with dependent children | `python scripts/sp-new.py --project _default --program billing --children "api,ui:api" --priority P2` | parent + two children, `ui` waits for `api` |
| Start and finish a story | `python scripts/sp-move.py login doing` / `done --next` | story moves folders; `--next` opens the next child |
| Check stories are well-formed | `python scripts/sp-validate.py path/to/story.md` | rc 1 if a section is missing or empty |
| Keep CI honest about leaks | `kaizen audit .` | rc 1 if personal data is found |
| See what a handoff would do | `python scripts/sp-handoff.py --launch path/to/story.md --dry-run` | the commands, nothing executed |
| Move to a fresh context mid-story | `/sp-handoff` | resume command injected in the pane, or copied to the clipboard |
