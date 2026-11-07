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

## Workflow (SP and michi)

Larger changes follow the kaizen flow this project ships: write the story as an SP (see `docs/commands.md`), then run it through the michi phases (research, plan, act, gates, review, PR). Small fixes do not need an SP. By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md); report vulnerabilities as described in [SECURITY.md](SECURITY.md).

## Where `core/` comes from

`core/` (skills, commands, scripts) is generated: the maintainer edits the source files in a private vault and runs `kaizen sync` (source folder from `KAIZEN_SOURCE`). Do not edit `core/` by hand; the next `sync` overwrites it, and `sync` fails with a clear message when the source folder does not exist (contributors without the vault do not need it).

- English prose lives in `translations/` (when the folder exists): files there overlay the same path in `core/` after every sync. Edit those to change wording.
- `translations/sources.json` stores the hash of the source each translation was made from; `kaizen sync` warns when the source changed since. After reviewing, run `kaizen sync --stamp`.
- Changes to scripts or behaviour: open an issue or PR describing them; the maintainer applies them at the source and re-syncs.

### Maintainer flow

1. Edit the piece at the source (skills, commands, scripts of the vault).
2. `kaizen sync --check` exits 1 and lists every `core/` file that is out of date (it never writes).
3. `kaizen sync`, then `npm test` and `kaizen audit .`.
4. Write a `COMMIT_*.md` and wait for the maintainer's confirmation before committing. Nothing here commits or pushes on its own; push only on explicit request.

What counts as a piece is defined once, in `bin/sync.js`. Project SPs stay in the vault and are never mirrored.

## Code layout

- `bin/kaizen.js` only routes; each command lives in `bin/commands/<name>.js` (`adapters`, `audit`, `doctor`, `init`, `python`, `sync`).
- `adapters/` renders the core per harness (`claude`, `codex`, `agents-md`); the last two share `agentsAdapter()` in `adapters/util.js`.
- `core/scripts/` shares helpers through `kaizen_engine.py` (`load`, `relocate`, frontmatter). `sp-fila.py` and `sp-handoff.py` are thin entry points over `sp_fila_*.py`, `handoff_pane.py`, `handoff_spawn.py` and `sp_progresso.py`; no module is above 300 lines.
- Dead imports and exports were removed; public behaviour (CLI, commands, skills) is unchanged.
- Architecture diagram: `docs/assets/architecture.svg`, regenerated with `python -I docs/assets/build-diagrams.py` run from `docs/assets/`.

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
