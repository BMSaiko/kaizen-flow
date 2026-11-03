# Error log

Every failure of an `sp-*.py` script (an exception or a non-zero exit code) is appended as one JSON line, so recurring errors become visible.

- **Module:** `core/scripts/kf_errlog.py`; tests in `core/scripts/test_kf_errlog.py`.
- **Location:** `$KF_ERRLOG`, else `%LOCALAPPDATA%\kaizen-flow\errors.jsonl`, else `~/.kaizen-flow/errors.jsonl`. Outside git.
- **Rotation:** at 1 MiB the file moves to `errors.jsonl.1` (one generation).
- **Fields:** `ts` (UTC), `script`, `args` (filtered), `tipo` (exception name or `mensagem`), `mensagem` (max 500 chars), `branch`, `rc`, optional `contexto`.
- **Secrets:** values of sensitive flags, `KEY=value` pairs, known token shapes and `.env`/key file paths are replaced by `***`.
- **Best effort:** a failed write never breaks the script; message, stdout and exit code are unchanged.

Wire a script with `sys.exit(kf_errlog.executar("<name>", main))` in its `__main__` block (see `sp-move.py`).
