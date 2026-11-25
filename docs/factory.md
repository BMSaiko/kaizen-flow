# Software factory

The factory turns a project goal into merged, quality-gated work. The human decides the goal and the release; everything in between is automatic and bounded.

## Architecture

```
VISION.md -> decompose -> SPs (sp/TODO) -> launch -> gates -> PR -> CI green -> merge -> reflect
                                              |         |                          |
                                       budget cap   quality + design         release: human
```

| Piece | Command | Doc |
|---|---|---|
| Goal | `kaizen vision init\|validate\|decompor` | `VISION.md` with frontmatter and fixed sections |
| Loop | `kaizen factory run <project>` | state in `.kaizen/factory/<project>.json`, log of slugs, phases and numbers only |
| Quality gates | `qualidade` in `kaizen.config.json` | types, complexity, diff coverage; blocking |
| Design gates | `kaizen ds lint\|verify` | `DESIGN.md` + DTCG tokens; only `ui: sim` stories |
| Merge | `pr_fechar.py` | only with green CI, never `--admin` |
| Release | `kf_release.py plan\|prepare` | the factory pauses with `release` |
| Manual mode | `kaizen factory run --manual` | [factory-manual.md](factory-manual.md) |

## Configuration

`kaizen.config.json`: `qualidade` (profile gates), `orcamento` (`spUsd` per story, `diaUsd` per day). Per project: `VISION.md`, `design/tokens.json`. Details in [config.md](config.md).

## Autonomy limits

- A red blocking gate creates one correction story; a second red gate on the same story pauses with `gate-bloqueado`.
- A reached budget cap pauses with `orcamento` before anything is launched.
- Tag, push of tag and publish are never done in auto: `publish` is refused without `--confirmo` (rc 3).
- A lock allows one factory per project (rc 4 for the second).

## The proof: `kaizen demo --factory`

`kaizen demo --factory [--keep]` builds a sample UI project with a `VISION.md` in a temp folder and runs the factory with deterministic fakes for the agent, `gh` and the browser: no network, under 2 minutes, rc 0. It shows each gate and each expected stop: a clean milestone, a red `ds-lint` that becomes a correction story, the release pause and resume, the budget stop and the refused publish. Covered by EC-102..EC-105 and UC-043 (`tests/factory-e2e.test.js`); CI runs it in the smoke job.

### Real end-to-end (opt-in, not in CI)

Needs a real agent, a GitHub repo and a browser, and costs tokens. In a scratch repo: `kaizen vision init demo && kaizen vision validate demo/VISION.md`, set a small `orcamento`, then `kaizen factory run demo --manual`, read the backlog, `approve`, `step`. Stop at the `release` pause; never publish from a trial.

## Troubleshooting

| Symptom | Cause / action |
|---|---|
| `visao-invalida` | `kaizen vision validate <file>` and fix what it lists |
| `orcamento` | raise `orcamento` or finish the story by hand |
| `gate-bloqueado` | read the gate output in the SP; fix, then `run` again |
| `release` | do the release, then `run --release-feito` |
| rc 4 | another factory runs for the project; a dead pid lock is taken over |
| `ds-verify` rc 3 | no browser/axe here; install them or run on a machine that has them |
