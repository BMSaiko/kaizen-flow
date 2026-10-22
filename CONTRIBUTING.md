# Contributing

Thanks for helping. The rules are short:

- Node stdlib and Python stdlib only; no heavy dependencies, no telemetry.
- Run the tests before opening a PR: `npm test`.
- Run `kaizen audit` — it must report nothing. The public repo must not contain personal names, local paths or private notes.
- Never commit transcripts, secrets or `.env` files. Usage reports hold metrics only, never conversation content.
- Keep adapters pure: `Adapter.render(core, target)` returns files, it does not write them.
- Commit messages: conventional (`feat`, `fix`, `docs`, `chore`), subject up to 72 characters.
