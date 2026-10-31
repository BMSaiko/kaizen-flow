# Contributing

Thanks for helping. The rules are short:

- Node stdlib and Python stdlib only; no heavy dependencies, no telemetry.
- Run the tests before opening a PR: `npm test` (runs `tests/*.test.js` with `node --test`, then the Python tests in `tests/`).
- Run `kaizen audit` — it must report nothing. The public repo must not contain personal names, local paths or private notes.
- Never commit transcripts, secrets or `.env` files. Usage reports hold metrics only, never conversation content.
- Keep adapters pure: `Adapter.render(core, target)` returns files, it does not write them.
- Commit messages: conventional (`feat`, `fix`, `docs`, `chore`), subject up to 72 characters.

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
