# Bulk-rename / wholesale-refactor recipe

Concrete pattern for renaming a term across a notes vault or a mixed
repo where the active codebase is small but `grep -ri` returns hundreds
of hits. Use after the grill-me scope chair has settled the question
"active codebase only, or every hit including worktrees/backups/history?"
(default: active codebase only).

## When this applies

- The user says "rename X to Y", "rebrand Z to W", "deprecate A
  everywhere" (pt-PT: "renomear X para Y", "trocar X por Y em todo o
  lado"), or any wholesale string change.
- The repo mixes **source code** (mutable, low count) with
  **historical artifacts** (changelogs, git worktrees, dated backups,
  draft plan notes) that should NOT be rewritten.
- A naive `rg -l 'X' | xargs sed -i 's/X/Y/g'` would produce a
  multi-MB diff that the user doesn't want.

## Suggested default exclusions

These categories look like "codebase" to a grep but are not. **Never
include them in a bulk rename** unless the user explicitly overrides.
Treat the list as a configurable default: adapt it to the project.

| Path pattern | Category | Why skip |
|---|---|---|
| `.wt/` | Git worktree copies | Git history; rewriting duplicates the change N times |
| `.backup/`, `backups/` | Dated backups | Mutable in principle, but rewriting is busywork |
| `data/`, `live-data/` | Runtime state | Data, not source |
| `CHANGELOG.md` | Append-only history | Lying about the past |
| `plans/`, `_draft/`, `.dp_*.md` | Historical design notes / work in progress | Written about the OLD name, or overwritten later |
| `node_modules/`, `.venv/`, `dist/`, `build/` | Generated / vendored | Never |
| `*.lock`, `package-lock.json`, `uv.lock` | Lock files | Never |

## Python walk recipe (works on Windows, no shell quoting issues)

When `rg`/`sed` are flaky on the host (MSYS path translation, missing
binaries, BOM/CRLF traps), use plain Python with `os.walk`. Run it from
the root of the tree to rename, as
`python rename.py OLD NEW` (dry-run) or `python rename.py OLD NEW --apply`.

```python
import os
import re
import sys
from pathlib import Path

root = Path.cwd()
old, new = sys.argv[1], sys.argv[2]
apply = "--apply" in sys.argv[3:]

# Configurable defaults: adapt to the project.
SKIP_DIRS = {
    ".git", ".obsidian", ".venv", "venv", "node_modules", "dist", "build",
    ".next", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".wt",       # git worktrees
    ".backup",   # dated backups
    "data", "live-data",  # runtime state
}
SKIP_NAMES = {"CHANGELOG.md"}  # add other append-only logs as needed
KEEP_EXT = {".py", ".ts", ".tsx", ".js", ".mjs", ".md", ".yaml", ".yml",
            ".toml", ".json", ".sh", ".cmd", ".bat", ".html", ".css", ".vue"}

pattern = re.compile(re.escape(old), re.IGNORECASE)

def smart_replace(text: str) -> str:
    # Preserve case: old -> new, Old -> New, OLD -> NEW
    def repl(m: re.Match) -> str:
        s = m.group(0)
        if s.isupper():
            return new.upper()
        if s[0].isupper():
            return new[:1].upper() + new[1:]
        return new
    return pattern.sub(repl, text)

hits = []
for dirpath, dirs, files in os.walk(root):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for f in files:
        p = Path(dirpath) / f
        if p.name in SKIP_NAMES or "lock" in p.name.lower():
            continue
        if p.suffix.lower() not in KEEP_EXT:
            continue
        try:
            if pattern.search(p.read_text(encoding="utf-8")):
                hits.append(p)
        except (OSError, UnicodeDecodeError):
            pass

for h in hits:
    rel = h.relative_to(root)
    if apply:
        h.write_text(smart_replace(h.read_text(encoding="utf-8")), encoding="utf-8")
        print(f"patched: {rel}")
    else:
        print(f"would patch: {rel}")
```

## Verification (do this after the patch)

Three quick checks, in order:

1. **Re-search for the old term, scope-excluded:** the dry-run above
   should now return **zero** hits in the active codebase. If anything
   remains, it's a missed case (likely a file extension missing from
   `KEEP_EXT`).

2. **`git diff --stat`** on the working tree: should show < 100 files
   changed, total diff < 1 MB. If the diff is 5+ MB, the exclusion set
   leaked (most likely `.wt/` or `.backup/` got included). Abort,
   reset, tighten the filter.

3. **Spot-check 2-3 representative files** (one source file, one doc,
   one config) for false-positive replacements: substrings that match
   but weren't meant to (a domain word, a vendor name, an unrelated
   concept). The case-preserving closure handles case, not semantics.

## Smoke test the runtime

After renaming, the affected surface (CLI verb, dashboard view, etc.)
needs at least one end-to-end run:

- The new name appears in the help/UI where expected.
- The old name does **not** appear (re-search above is the unit test).
- The feature still works: an action that used to be `tool old list`
  is now `tool new list` and returns the same data.
- Backend env vars / SQL table names / tool schema names that you
  intentionally did **not** rename still match what the renamed UI
  passes to them. If the UI passes an identifier to the backend, a
  "rename the UI first, backend later" plan needs a temporary alias.

## Known gotchas

- **MSYS path translation** in a shell can corrupt Windows paths. Use
  `pathlib.Path("C:/...")` in Python (forward slashes work on Windows).
- **BOM + CRLF** from PowerShell `Out-File` breaks strict TOML/YAML
  parsers. Re-read with `encoding="utf-8-sig"` to strip the BOM, or
  write via Python's `pathlib`.
- **Worktree on the same path as source**: `.wt/` and the source tree
  often coexist. The exclusion set prunes `.wt` at the `os.walk` level,
  but a config file that references `.wt/...` paths should be left
  alone: it points to the *historical* path, which is what people mean
  when they say "look at the old worktree from August".
- **Tool schema names** are passed to the model as tool identifiers. If
  the user said "frontend only", leave the schema name alone, or the
  model keeps calling the old name after the UI changes. Surface it in
  the plan if a backend rename pass is coming.
