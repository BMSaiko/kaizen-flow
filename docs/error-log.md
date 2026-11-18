# Error log

Every failure of an `sp-*.py` script (an exception or a non-zero exit code) is appended as one JSON line, so recurring errors become visible.

- **Module:** `core/scripts/kf_errlog.py`; tests in `core/scripts/test_kf_errlog.py`.
- **Location:** `$KF_ERRLOG`, else `%LOCALAPPDATA%\kaizen-flow\errors.jsonl`, else `~/.kaizen-flow/errors.jsonl`. Outside git.
- **Rotation:** at 1 MiB the file moves to `errors.jsonl.1` (one generation).
- **Fields:** `ts` (UTC), `script`, `args` (filtered), `tipo` (exception name or `mensagem`), `mensagem` (max 500 chars), `branch`, `rc`, optional `contexto`, optional `ec` (the `EC-NNN` code given or the first one in the message).
- **Secrets:** values of sensitive flags, `KEY=value` pairs, known token shapes and `.env`/key file paths are replaced by `***`.
- **Best effort:** a failed write never breaks the script; message, stdout and exit code are unchanged.
- **Unexpected exception:** printed in the error format below as `EC-010` with rc 1 and no stack trace; `KF_DEBUG=1` or `--debug` re-raises it (full stack).

Wire a script with `sys.exit(kf_errlog.executar("<name>", main))` in its `__main__` block (see `sp-move.py`).

## Phase checkpoint and journal

`core/scripts/sp_journal.py` keeps durable per-SP state so an interrupted run can resume (`kaizen resume` reads it).

- **Files:** `<worktree>/.kaizen/estado/<slug>.json` (atomic checkpoint, `sp_disco.guardar`) and `<slug>.journal.jsonl` (append-only, one JSON event per line: `ts`, `pid`, `fase`, `passo`, `evento` = `inicio|fim|revertido`, `idempotente`; fsync per event). Both are git-ignored.
- **Interrupted step:** an `inicio` without `fim` is reported by `estado` with `acao: repetir` (idempotent) or `reverter` (restore with `michi-checkpoint.py`).
- **Truncated last line:** ignored with a warning and repaired before the next append.
- **Corrupt state:** the file moves to `<file>.corrupt-<ts>` (never deleted, never overwritten) and the state is rebuilt from git and the SP `phase:`; the user confirms.
- **Signals:** SIGINT, SIGBREAK and console close (`CTRL_CLOSE_EVENT`) write `interrompido: true` and re-raise within 1 s.

## Error message format

Every refusal or error of the `sp-*`/michi/kaizen scripts uses one format (module `core/scripts/kf_erros.py`, Node mirror `bin/commands/erros.js`), in European Portuguese, one line per part, with the edge-case code from [catalogo.json](catalogo.json) first:

```
EC-016 O quê: SP x em pausa até 2026-11-18T15:00:00
  Porquê: quota/limite de uso do modelo: Claude usage limit reached …
  Estado guardado: checkpoint e journal intactos
  Próximo: esperar até 2026-11-18T15:00:00 e `kaizen resume x`
```

A contract test (`test_kf_erros_formato.py`) checks that every `EC-NNN` used by the scripts exists in the catalogue. Codes and the next command:

| EC | Situation | Next command |
|---|---|---|
| EC-010 | unexpected exception in a script | rerun with `KF_DEBUG=1`, report with the log line |
| EC-016 | model quota / rate limit / overloaded | wait for `retoma_em`; the queue resumes a live pane, else `kaizen resume <slug>` |
| EC-017 | network down (DNS, reset, timeout) | same as EC-016 (default pause `KF_RETOMA_MIN`) |
| EC-066 | model login/session expired | log in to the harness, then `kaizen resume <slug>` |
| EC-025 | branch behind the main branch | `git merge <main>` in the worktree |
| EC-027 | story orphaned (no live owner) | `kaizen resume <slug>` |
| EC-031 | main checkout off the main branch | `git -C <main checkout> checkout <main>` |
| EC-033 | no free pane slot | wait; the queue reuses the slot |
| EC-036 | no terminal multiplexer | open WezTerm/tmux/herdr or run without `--concorrencia` |
| EC-038 | stale queue to abandon | `--abandonar-obsoleta` or `--parar` |
| EC-042 | lock held by a live process | retry in a few seconds |
| EC-043 | story already running in another pane | wait, or `sp-resume.py <slug> --unlock` if the pane is gone |
| EC-045 / EC-047 | queue or pane state unreadable | `sp-fila.py --parar` |
| EC-050 | no state to resume | `/michi <slug>` from the start |
| EC-060 | dirty worktree at start | commit, or `git stash push -u -m <tag>` (`kaizen preflight --fix`) |
| EC-061 | worktree on the wrong branch | `git checkout agent/<slug>` |
| EC-062 | story worktree missing | `git worktree add <dir> -b agent/<slug>` |
| EC-063 | prunable worktree | `git worktree prune` (`--fix`) |
| EC-064 | merge/rebase half done | `--continue` or `--abort` by hand |
| EC-065 | git or Python missing | install it and open a new terminal |
| EC-067 | invalid request (slug, transition, phase, option) | follow the message |
| EC-068 | kaizen pieces missing in a project | `kaizen doctor --fix` |

## Preflight

`kaizen preflight [slug] [--repo dir] [--json] [--fix]` (`core/scripts/sp-preflight.py`) only reads: it lists each problem above (EC-025/027/031/060-065) with its level (`erro` stops a michi run in auto mode, `aviso` informs) and the safe fix. rc 0 clean, 1 problems, 2 usage error. `--fix` runs only the safe list (`stash push -u -m`, `worktree prune`, `checkout <branch>`), one by one, after a terminal confirmation (EOF counts as no). It never deletes. michi runs it at start, `kaizen resume` before resuming (warnings only). Target: under 2 s.
