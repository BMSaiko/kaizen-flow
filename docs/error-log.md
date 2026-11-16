# Error log

Every failure of an `sp-*.py` script (an exception or a non-zero exit code) is appended as one JSON line, so recurring errors become visible.

- **Module:** `core/scripts/kf_errlog.py`; tests in `core/scripts/test_kf_errlog.py`.
- **Location:** `$KF_ERRLOG`, else `%LOCALAPPDATA%\kaizen-flow\errors.jsonl`, else `~/.kaizen-flow/errors.jsonl`. Outside git.
- **Rotation:** at 1 MiB the file moves to `errors.jsonl.1` (one generation).
- **Fields:** `ts` (UTC), `script`, `args` (filtered), `tipo` (exception name or `mensagem`), `mensagem` (max 500 chars), `branch`, `rc`, optional `contexto`.
- **Secrets:** values of sensitive flags, `KEY=value` pairs, known token shapes and `.env`/key file paths are replaced by `***`.
- **Best effort:** a failed write never breaks the script; message, stdout and exit code are unchanged.

Wire a script with `sys.exit(kf_errlog.executar("<name>", main))` in its `__main__` block (see `sp-move.py`).

## Phase checkpoint and journal

`core/scripts/sp_journal.py` keeps durable per-SP state so an interrupted run can resume (`kaizen resume` reads it).

- **Files:** `<worktree>/.kaizen/estado/<slug>.json` (atomic checkpoint, `sp_disco.guardar`) and `<slug>.journal.jsonl` (append-only, one JSON event per line: `ts`, `pid`, `fase`, `passo`, `evento` = `inicio|fim|revertido`, `idempotente`; fsync per event). Both are git-ignored.
- **Interrupted step:** an `inicio` without `fim` is reported by `estado` with `acao: repetir` (idempotent) or `reverter` (restore with `michi-checkpoint.py`).
- **Truncated last line:** ignored with a warning and repaired before the next append.
- **Corrupt state:** the file moves to `<file>.corrupt-<ts>` (never deleted, never overwritten) and the state is rebuilt from git and the SP `phase:`; the user confirms.
- **Signals:** SIGINT, SIGBREAK and console close (`CTRL_CLOSE_EVENT`) write `interrompido: true` and re-raise within 1 s.
