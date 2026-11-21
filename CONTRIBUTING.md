# Contributing

Thanks for helping. The rules are short:

- Node stdlib and Python stdlib only; no heavy dependencies, no telemetry.
- Run the tests before opening a PR: `npm test` (runs `tests/*.test.js` with `node --test`, then the Python tests in `tests/`).
- Run `kaizen audit` — it must report nothing. The public repo must not contain personal names, local paths or private notes.
- Never commit transcripts, secrets or `.env` files. Usage reports hold metrics only, never conversation content.
- Keep adapters pure: `Adapter.render(core, target)` returns files, it does not write them.
- Commit messages: conventional (`feat`, `fix`, `docs`, `chore`), subject up to 72 characters.

## Setup

```
git clone https://github.com/BMSaiko/kaizen-flow.git
cd kaizen-flow
python -m pip install pytest
npm test
node bin/kaizen.js audit .
```

Requires Node 18+ and Python 3. Use a branch per change (`feat/<slug>`, `fix/<slug>`) and open the PR against `main`; the PR template asks for done, decisions, not done and proof.

## Development method

This repo uses `desenvolvimento.metodo: worktree-pr` (`kaizen.config.json`, see `docs/config.md`):

- Work on a branch in its own worktree (`agent/<slug>`); never on `main`.
- Commit, push and PR are automatic from that branch; the PR body follows the template.
- `python scripts/pr_fechar.py <PR> --repo .` watches the PR and merges (squash) only when every check is green and there is no conflict.
- Red checks, a conflict or a requested review stop the flow with the reason; nothing is merged and `--admin` is never used.
- On `main` the automatic permissions fall back to asking.

## Workflow (SP and michi)

Larger changes follow the kaizen flow this project ships: write the story as an SP (see `docs/commands.md`), then run it through the michi phases (research, plan, act, gates, review, PR). Small fixes do not need an SP. By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md); report vulnerabilities as described in [SECURITY.md](SECURITY.md).

## Where `core/` comes from

`core/` (skills, commands, scripts) is the source of truth: edit the pieces here, in the repo. The maintainer's vault receives them with `kaizen sync --to-vault` (vault folder from `KAIZEN_SOURCE`).

- Personal values never live in `core/`: text pieces carry markers (`{{userName}}`, `{{userFullName}}`, `{{agentName}}`, `{{agentSlug}}`). `--to-vault` fills them from the vault's `kaizen.config.json`; `kaizen init`/`doctor` fill them with neutral defaults (`user`, `the user`, `the agent`, `kaizen`).
- `--to-vault` keeps a hash manifest (`.kaizen-sync.json` in the vault). A piece edited in the vault since the last sync makes it refuse (rc 1) and list the file; bring the change into `core/`, or repeat with `--force` to overwrite it.
- `kaizen sync --to-vault --check` writes nothing: exits 0 when the vault matches, 1 with the list of differing or missing pieces.
- The old direction (vault → `core/`) is only available as `kaizen sync --from-vault [--check] [--stamp]` and prints a warning; `kaizen sync` without a direction fails. English prose in `translations/` (when it exists) still overlays `core/` in that direction.

### Maintainer flow

1. Edit the piece in `core/` (skills, commands, scripts).
2. `npm test` and `kaizen audit .`.
3. `KAIZEN_SOURCE=<vault> kaizen sync --to-vault --check`, then `kaizen sync --to-vault`.
4. Write a `COMMIT_*.md` and wait for the maintainer's confirmation before committing. Nothing here commits or pushes on its own; push only on explicit request.

What counts as a piece is defined once, in `bin/sync.js`. Project SPs stay in the vault and are never mirrored.

## Code layout

- `bin/kaizen.js` only routes; each command lives in `bin/commands/<name>.js` (`adapters`, `audit`, `doctor`, `init`, `python`, `sync`).
- `adapters/` renders the core per harness (`claude`, `codex`, `agents-md`); the last two share `agentsAdapter()` in `adapters/util.js`.
- `core/scripts/` shares helpers through `kaizen_engine.py` (`load`, `relocate`, frontmatter). `sp-fila.py` and `sp-handoff.py` are thin entry points over `sp_fila_*.py`, `handoff_pane.py`, `handoff_spawn.py` and `sp_progresso.py`; no module is above 300 lines.
- Dead imports and exports were removed; public behaviour (CLI, commands, skills) is unchanged.
- Diagrams (`architecture.svg`, `michi-cycle.svg`, `sp-workflow.svg`, `sp-fila-parallel.svg` in `docs/assets/`): regenerate from the repo root with `python -I docs/assets/build-diagrams.py docs/assets`.

### Before / after the cleanup (non-test `.py`/`.js`)

| | before (`main`) | after |
|---|---|---|
| files | 38 | 52 |
| lines | 9722 | 10206 |
| `sp-fila.py` | 784 | 187 |
| `sp-handoff.py` | 549 | 162 |
| `bin/kaizen.js` | 268 | 37 |

Lines grew because the monoliths became small modules and new tests went in; the gain is in module size and shared helpers, not total lines.

## Branch protection (ação do maintainer)

Em Settings → Branches → `main`, exigir como checks obrigatórios do PR: `test / test` (todas as combinações da matriz), `coverage / test` e `smoke`. A cobertura é só informativa (artefacto `coverage-*`), sem limiar.
