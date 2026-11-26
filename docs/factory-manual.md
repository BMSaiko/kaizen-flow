# Factory by hand (manual mode)

The manual mode drops the autonomy, never the guarantees: every story still goes through the `qualidade` gates, the budget (`orcamento`) and the log. State lives in `.kaizen/factory/<project>.json`; use cases: UC-042, edge cases EC-094..EC-101 (`docs/catalogo.json`).

## Pauses

| `paragem` | Meaning | Next action |
|---|---|---|
| `aguarda-aprovacao` | stories exist but none (or not all) approved | `kaizen factory approve <project> [--so a,b]` |
| `passo` | `step` finished one story | `step` again, or `run` |
| `manual` | only paused or taken-over stories are left | the human finishes it, or `resume`/`skip <sp>`, then `run` |

## Recipes

1. **Approve the generated backlog before anything runs.** `kaizen factory run <project> --manual` decomposes the `VISION.md` and stops with `aguarda-aprovacao`. Read the stories in `sp/TODO`, then `approve` (all) or `approve --so a,b` (only those); `run` launches what is approved.
2. **One story at a time.** `kaizen factory step <project>` runs the next eligible approved story to merge (green gates, CI green) and stops with `passo`.
3. **Write a story by hand.** `python -I scripts/sp-new.py --project <project> --slug <slug> ...` (slug without `-visao-mN-`), then `approve --so <slug>`. In manual mode hand-made stories (not mothers) of the project enter the same state, budget and gates; in autonomous mode they are ignored.
4. **Pause and resume a story.** `pause <project> <sp>`: the factory skips it (its dependents wait); `resume <project> <sp>` gives it back.
5. **Skip a story.** `skip <project> <sp>`: counts as met for its dependents and is never launched (`resume` undoes it).
6. **Take over a story.** `takeover <project> <sp>`: the factory never launches or auto-corrects it. When you finish it (PR open, gates green, or the SP in Done) the next `run` merges it through `pr_fechar`, CI green, like any other; a red gate pauses instead of creating a correction story.
7. **Crash or Ctrl+C.** `run` again: the mode, the approvals and the phase of each story are kept; nothing is relaunched or merged twice.
8. **Leave manual mode.** `kaizen factory run <project> --auto`.

With a live factory, `approve|pause|resume|skip|takeover` are queued in `<project>.cmd.jsonl` and applied on its next turn; without one they apply at once. Correction stories created by the factory are approved automatically.
