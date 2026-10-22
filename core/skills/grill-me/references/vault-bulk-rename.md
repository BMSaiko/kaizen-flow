# Vault bulk-rename / wholesale-refactor recipe

Concrete pattern for renaming a term across a Second Brain-style vault
where the active codebase is small but `grep -ri` returns hundreds of
hits. Use after the grill-me scope chair has settled the question
"active codebase only, or every hit including worktrees/backups/history?"
(default: active codebase only).

## When this applies

- The user says "rename X to Y", "rebrand Z to W", "deprecate A
  everywhere", or any wholesale string change.
- The repo mixes **source code** (mutable, low count) with
  **historical artifacts** (CHANGELOG, .wt/ worktrees, dated .backup/
  snapshots, draft DP/DR notes) that should NOT be rewritten.
- A naive `rg -l 'X' | xargs sed -i 's/X/Y/g'` would produce a
  multi-MB diff that the user doesn't want.

## The exclusion set (user's Second Brain, 2026-09-02 baseline)

These are the categories that look like "codebase" to a grep but
are not. **Never include in a bulk rename** unless the user explicitly
overrides:

| Path pattern | Category | Why skip |
|---|---|---|
| `.wt/` | Git worktree copies | Git history; rewriting duplicates the change N times |
| `.backup/<name>-<iso>.json` | Dated backups | Mutable in principle, but rewriting is busywork |
| `data/`, `live-data/` | Runtime board state | JSON data, not source |
| `live-data/.wt/`, `data/.wt/` | Worktree live-data | Same as above + worktree |
| `CHANGELOG.md` | Append-only history | Lying about the past |
| `<project>/plans/<date>-*-{DR,DP,DA}.md` | Historical design notes | Designer was thinking about the OLD name |
| `.dp_*.md`, `_draft/` | Work in progress | Will be overwritten |
| `node_modules/`, `.venv/`, `dist/`, `build/` | Generated / vendored | Never |
| `*.lock`, `package-lock.json`, `uv.lock` | Lock files | Never |

## Python walk recipe (works on Windows, no shell quoting issues)

When `rg`/`sed` are flaky on the host (MSYS path translation, missing
binaries, BOM/CRLF traps), use `execute_code` + `os.walk`. This is
the pattern that actually ran on 2026-09-02:

```python
import os
import re
from pathlib import Path

vault = Path("~/Documents/Second-Brain")
os.chdir(vault)

SKIP_DIRS = {
    ".venv", "venv", "node_modules", "dist", "build", ".next",
    ".git", ".obsidian", ".agents", ".claude", ".cursor", ".clinerules",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".wt",       # git worktrees
    ".backup",   # dated backups (often nested under projects)
    "data",      # runtime board state
    "live-data", # alt runtime data dir
}
SKIP_NAMES = {"CHANGELOG.md"}  # add other append-only logs as needed
SKIP_EXT = {".png", ".jpg", ".gif", ".pdf", ".zip", ".lock",
            ".min.js", ".pyc", ".woff", ".woff2"}
KEEP_EXT = {".py", ".ts", ".tsx", ".js", ".mjs", ".md", ".yaml",
            ".yml", ".toml", ".json", ".env", ".sh", ".cmd", ".bat",
            ".html", ".css", ".vue"}

OLD = re.compile(r"kanban", re.IGNORECASE)
NEW = "michi"  # preserve original case via the closure below

def smart_replace(text: str) -> str:
    # kanban -> michi, Kanban -> Michi, KANBAN -> MICHI
    return re.sub(
        r"kanban",
        lambda m: {"kanban": "michi",
                   "Kanban": "Michi",
                   "KANBAN": "MICHI"}[m.group(0)],
        text,
    )

hits = []
for root, dirs, files in os.walk(vault):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for f in files:
        p = Path(root) / f
        if p.name in SKIP_NAMES:
            continue
        ext = p.suffix.lower()
        if ext in SKIP_EXT or (ext and ext not in KEEP_EXT):
            continue
        if "lock" in p.name.lower():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
            if OLD.search(text):
                hits.append(p)
        except OSError:
            pass

# Dry-run first: print, don't write
for h in hits:
    rel = h.relative_to(vault)
    print(f"would patch: {rel}")

# Uncomment to apply:
# for h in hits:
#     text = h.read_text(encoding="utf-8")
#     h.write_text(smart_replace(text), encoding="utf-8")
#     print(f"patched: {h.relative_to(vault)}")
```

## Verification (do this after the patch)

Three quick checks, in order:

1. **Re-grep for the old term, scope-excluded:** the same `os.walk` script
   with `OLD.search` should now return **zero** hits in the active
   codebase. If anything remains, it's a missed case (likely a
   file-extension filter that wasn't in `KEEP_EXT`).

2. **`git diff --stat`** on the working tree: should show < 100 files
   changed, total diff < 1 MB. If the diff is 5+ MB, the exclusion set
   leaked — most likely `.wt/` or `.backup/` got included. Abort,
   reset, tighten the filter.

3. **Spot-check 2-3 representative files** (one source file, one doc,
   one config) for false-positive replacements. Look for: substrings
   that match the regex but weren't meant to (e.g. "kanban" inside a
   domain word, a vendor name, an unrelated concept). The
   `smart_replace` closure above handles case but not semantics.

## Smoke test the runtime

After renaming, the affected surface (CLI verb, dashboard view, etc.)
needs at least one end-to-end run:

- The new name appears in the help/UI where expected.
- The old name does **not** appear (re-grep above is the unit test).
- The feature still works: an action that used to be `hermes kanban
  list` is now `hermes michi list` (or whatever the user picked) and
  returns the same data.
- Backend env vars / SQL table names / tool schema names that you
  intentionally did **not** rename still match what the renamed UI
  passes to them. This is the part where "rename the UI first, backend
  later" needs a temporary alias if the UI passes an identifier to
  the backend (e.g. `?tool=kanban_list` survives a UI rename only if
  the backend keeps the old name).

## Known gotchas

- **MSYS path translation** in `terminal()` can corrupt Windows
  paths. Use `execute_code` + `pathlib.Path("C:/...")` (forward
  slashes work in Python on Windows). See `vault-git-windows` skill.
- **BOM + CRLF** in PowerShell `Out-File` breaks strict TOML/YAML
  parsers. If a write_file ends up with weird encoding, re-read
  with `encoding="utf-8-sig"` to strip the BOM, or write via
  `execute_code` which uses `pathlib`.
- **Worktree-on-the-same-path-as-source**: `.wt/` and `code/` often
  coexist. The exclusion set above prunes `.wt` at the `os.walk`
  level, but if a config file under `code/` references `.wt/...`
  paths (e.g. a docs page listing worktrees), the reference should
  be left alone — it points to the *historical* path, which is what
  the user means when they say "look at the kanban v3 worktree from
  Aug 27". Even after the rename, "michi v3 from Aug 27" only makes
  sense if the worktree path itself is preserved.
- **Tool schema names** (e.g. `kanban_show`) are passed to the model
  as tool identifiers. If the user said "frontend only", leave the
  schema name alone — the model will keep calling `kanban_show` even
  after the dashboard says "michi". This is intentional for the
  phased rename; surface it in the DP if/when the backend rename
  pass is planned.
