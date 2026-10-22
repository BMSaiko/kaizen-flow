# michi — Skip-grill play (the `skip grill + vague scope` gate)

> The pitfall in `SKILL.md` "skip grill + vague large-scope instruction"
> links here. When the user says `skip grill` and the instruction is
> large and fuzzy ("refactor X", "clean up Y", "fix all the bugs in Z"),
> do NOT jump straight to DR/DP/DA and do NOT ask 5 clarifying questions.
> Do this instead.

## The 5-minute scan (run before asking)

A scan is not research; it is a census. The goal is to know what exists
and what would break, not to understand the system.

| Probe | Tool | Why |
|-------|------|-----|
| Top-level layout | `search_files(target='files', pattern='*', path=<repo>)` | Know what kind of repo this is (TS/Node, Python, Go, …) |
| File sizes of the suspect area | `execute_code` + `pathlib` over the dir, count `b'\n'` per file | Identify the **single** monolith that needs refactor (vs 30 already-small files) |
| Exported surface | grep `^export ` / `^export default function` / `^export class` | Public contract — every refactor must preserve it |
| Public entry points | routes (`router.X` / `app.X` / `s.middlewares.use`) OR function names | What the tests + client depend on |
| Tests that touch the area | `search_files(target='files', pattern='*test*')` + content grep for the public entry points | The minimum gate you must not break |
| Git state | `git -C <repo> status --short`, `branch --show-current`, `worktree list` | Worktree trap, clean tree vs dirty, which branch you are on |

If the scan takes >5 minutes, you are doing research, not scanning. Stop,
write what you have, ask the question.

## The courage table (the alignment artifact)

The user skipped grill. They are not going to answer 6 questions. They
are willing to answer 1. Make that 1 question a multi-option choice
where each option is a **meaningfully different shape** (different
amount of code touched, different risk, different dependencies added).

Template:

```
== Onde aterrar — preciso de 1 decisão tua ==

A — <safe>: <what + diff size hint>. <risk one-liner>.
B — <+1 axis>: <what + diff size hint + which axis>. <risk one-liner>.
C — <rewrite>: <what + diff size hint + which framework/pattern>. <risk one-liner>.

Honestamente, <recommendation> é o que "<user's words>" quer dizer sem
transbordar. <mention what would change your recommendation>.

Diz:
- <which level> (A/B/C)
- <escopo yes/no>
- <one other axis if unavoidable>
```

The recommendation is not optional — the user skipped grill *to avoid
deciding everything*. They want a senior to pick. The table is the
option set; the recommendation is your best read.

## The one-decision ask

End with **one** question that bundles:
- which level (A/B/C) — almost always the recommendation
- which scope (the area or the whole backend) — to bound the diff
- one **unavoidable** axis (e.g. "can I add zod as a dep?") — if the
  level you are pitching requires it

NEVER bundle:
- branch choice (look it up; it is in your scan)
- path choices (derive from project structure)
- tests-to-run (derive from the test list)
- "anything else I should know" — if you need this, your scan is
  incomplete; go back

If the user comes back with "do A and B but skip C", honour it. They
own the ladder; you pick the rung.

## What NOT to do

- Do not run `dp` on the vague instruction. DP needs a one-screen
  goal; "refactor todo o backend" is not a goal, it is a direction.
- Do not produce a 30-item todo list. If you need 30 items to express
  the work, you have not finished the courage table.
- Do not start editing before the user answers. The skip-grill play is
  about *exposing the shape*, not about being fast. A 2-minute scan +
  1 decision ask is faster than 3 patches the user has to revert.
- Do not rephrase the user. "refactor the backend" → your table must
  *name* what the backend is, not echo "backend". The scan earns the
  right to name things.

## User did not answer the free-text ask (2026-09-04, atlas polish-A cycle)

The `clarify` call has a time window. If the user does not respond
within it, do **not** stall on a missing decision. Ponytail rule
applies: ship the lazy version, apply the most conservative defaults
that preserve the SP contract, and surface every applied default in
the DP's "What you should know before signing off" section so the
user can override on review.

Three concrete defaults that have held up:

1. **Worktree state** when an existing dir+branch on disk have
   uncommitted work from a prior session → recover+finish
   (`git worktree prune` + re-add without `-b`). Never wipe + restart:
   the on-disk work is the answer to most of the phases already.
2. **A leftover `stash@{0}` from a prior session** → leave stashed,
   never touch in this epic. Popping it conflates two sessions'
   scopes and likely breaks SP hard-invariants (e.g. `server/**`
   byte-identical).
3. **A previous gate run that failed a bar** (e.g. Lighthouse perf
   91 vs SP ≥95) → re-run once on the current state and trust the
   new number. Cheap, may have been a preview-server artifact.
   If still failing, file a conditional sub-phase in the DP, do not
   lower the bar.

The rule is "do not silently assume" — surface the default, name
the conservative choice, link the rule it falls back to. See the
parent SKILL.md Style section for the matching inline rule.

## Worked example (2026-09-02, atlas backend refactor)

User: "faz refactor ao backend todo do projeto atlas, da skip ao grillme".

Scan output that fed the table:
- `server/api.ts`: 1500 lines, single `export default function atlasApi():
  Plugin` (Vite plugin), ~35 inline handlers, 35 helper functions
- `server/config.ts`: 75 lines (clean)
- `server/roadmap.ts`: 81 lines (clean)
- `server/snapshots.ts`: 155 lines (already a module)
- `server/prompts/`: already split
- Client uses only 6 endpoints from `src/api.ts`
- `test/_atlas-harness.mjs` + `test/ci-gate.test.mjs` hit the real
  server; rest of tests are frontend
- `live-data/.wt/atlas/` has 14 historical feature worktrees

Courage table (final form sent to user):

| A — extrair só handlers | ~200 LoC, 35 handlers → `server/routes/*.ts`, dispatch table | baixo |
| B — extrair + normalizar erros/validação | A + `readBody<T>(schema)` + `sendError` | médio (se zod, **add dep**) |
| C — extrair + Router real | B + `express.Router`/Hono/find-my-way | alto — `configureServer` middlewares + router é terreno escorregadio |

Recommendation: A. "Refactor todo o backend" is structural; A is the
minimum that earns that label.

User never answered (interrupted) → michi paused at phase 1. Reflect
still owed (per the "hijacked mid-stream" pitfall), and the lesson
("vague scope + skip grill needs a 5-min scan + courage table, not
zero questions") is now encoded as a michi pitfall.

## After the courage-table answer: bundle wire-only with first move

When the user picks A/B/C, the next thing the plan does is usually
"extract the dispatch skeleton → run gates → then move handlers".
**If the dispatch skeleton ships empty (no real routes, no real
behavior change, tests pass identically), the wire-only phase is
not a phase — it is half a phase.** Bundle it with the first real
move (e.g. "wire the dispatcher AND move the simplest domain (3
handlers) into it, then gates"). The user signed off on the courage
table; they did not sign off on a separate approval gate between
"skeleton compiles" and "first feature moves".

Pattern after a courage-table pick:

1. Define `done-when` for the next concrete phase in user-visible
   terms ("X routes moved out of `api.ts`, all gates RC=0,
   `api.ts` down N lines").
2. Inside that phase, do the wire work AND the first real move.
   The wire work is justified as the prerequisite; the real move
   is the deliverable.
3. Surface the wire work in the report as a sub-section, not as
   a separate "phase done" item.

The exception is when the wire work IS the risk (new auth model,
new build step, new runtime dependency). Then the wire-only
phase gates the risk and the bundling rule does not apply. Pure
structural refactors are not in that exception list.

Worked counter-example (atlas backend refactor, 2026-09-02): the
plan split into "Phase 2A: wire dispatch table, move 0 handlers"
and "Phase 2B: move first domain (terms/*) into the table". After
2A, the report section was empty (zero behavior change, identical
tests, all gates green) and I stopped to ask the user to confirm
the per-domain plan shape — which was an approval gate the
courage table had not asked for. 2A and 2B should have been one
phase. Bundled, the same work would have been one report section
"wire dispatcher + moved 3 terms handlers, gates green" instead
of two turns of confirmation for zero behavior change.


## Gate hygiene — two rules that pay for themselves in skip-grill

These are reflexes the cycle pays for when you skip them,
regardless of which courage level you picked.

### Rule 1 — never broad-kill during gates

When a Phase 5 gate hangs (build/test/lint that does not return),
the reflex is `taskkill /F /IM <interpreter>` (e.g. `node.exe`,
`python.exe`, `java.exe`). On Windows this kills **every** process
matching the name — including the user's live dev server, the
IDE's child process, the LLM harness the user is reading this
session from. The user feels it as "the kanban went down" or "VS
Code reloaded".

Recipe: scope the kill to the PID you actually have, or to a
narrow filter.

```bash
# BAD — kills every node process on the box
taskkill /F /IM node.exe /T

# GOOD — kill only the PID you spawned for the gate
taskkill /F /PID <pid> /T

# GOOD — narrow by commandline (atlas pattern: killWtLockers
# in server/api.ts:206-211)
powershell -NoProfile -NonInteractive -Command \
  "Get-CimInstance Win32_Process | \
   Where-Object { $_.CommandLine -match '<unique-substring>' } | \
   ForEach-Object { taskkill /PID $_.ProcessId /T /F }"
```

Detection that you already broad-killed: `tasklist` shows the
expected process is gone AND other unrelated processes are also
gone. Re-check with `tasklist /FI "IMAGENAME eq <interpreter>"`
before claiming "I cleaned up".

### Rule 2 — for EOL symptoms, `git config --show-origin` first

When a user says "EOL is mixed / lines are wrong / gitattributes
doesn't take effect", the temptation is to immediately rewrite
files or set `core.autocrlf` and watch what happens. Wastes
2-5 minutes when the answer is one command away.

```bash
# 1. Show every value of core.autocrlf and where it comes from
git config --show-origin --get-all core.autocrlf

# 2. Same for core.eol
git config --show-origin --get-all core.eol

# 3. Show what the index actually thinks the file is
git check-attr -a -- <file>
```

If `core.autocrlf` is `true` at the `--system` scope (Git for
Windows default) and `--local` says `false`, **system wins for
checkout** on Windows — the file is rewritten on every `git
checkout` regardless of local config. The `.gitattributes`
`eol=lf` is a no-op. `git checkout HEAD -- <file>` STILL writes
CRLF. **Fix:** rewrite files via Python
(`.read_bytes().replace(b'\r\n', b'\n')` + `git add` + commit)
with `core.autocrlf=false` local. Cannot `--system --unset`
without admin.

Reference: atlas EOL cycle, 2026-09-04 — three failed `git
checkout` attempts at normalize before realising system
autocrlf was active. One `Path.write_bytes` + `git add` + commit
succeeded in one shot. Pattern is reusable whenever the file is
text and the system autocrlf is hostile.

### Rule 3 — Windows profile: `patch` / `read_file` / `search_files` fail with generic errors; default to `execute_code`+`pathlib`

On the user Windows profile, `terminal()` runs in an MSYS sandbox
where `git`, `uv`, `python` are not on the PATH, and the
`read_file` / `search_files` / `patch` tools are workspace-bound
with broken path resolution. Symptom: every one returns a generic
"Failed to read file" or "search requires rg" for paths inside
the workspace. `write_file` for content with embedded single-quote
characters also fails with `unexpected EOF` (bash escape inside
the sandbox).

Cost without this rule: 3-5 min per file trying the broken tools
before switching to `execute_code` with `pathlib`.

**Recipe (default for any FS work on this profile):**

```python
# Read
from pathlib import Path
content = Path(r"~\Documents\hermes-agent\file.py").read_text(encoding="utf-8", errors="replace")

# Write (overwrite; create parents)
Path(r"C:\...").write_text(content, encoding="utf-8")

# Delete
Path(r"C:\...").unlink(missing_ok=True)

# Iterate / search
for p in Path(r"C:\...").rglob("*.py"):
    if "needle" in p.read_text(encoding="utf-8", errors="replace"):
        ...
```

For shell work (git, uv, python, etc.):

```python
import subprocess
# Always absolute exe path on this profile — PATH inside the sandbox is empty
GIT = r"C:\Program Files\Git\bin\git.exe"
UV = r"~\.local\bin\uv.exe"
PY = r"~\Documents\hermes-agent\.venv\Scripts\python.exe"
r = subprocess.run([GIT, "status", "--short"], cwd=str(repo),
                   capture_output=True, text=True, timeout=15)
# tasklist output is cp1252; decode with errors="replace"
r2 = subprocess.run([r"C:\Windows\System32\tasklist.exe"],
                    capture_output=True, timeout=10)
text = r2.stdout.decode("cp1252", errors="replace")
```

**Detection that you're on the broken profile:** `read_file`
returns `Failed to read file: <path>` for a path that `ls` (or
`Path.exists()`) can see. Don't retry the same broken tool —
switch to `execute_code`.

**Why this belongs in michi:** every michi cycle on this profile
hits this friction. Not having the recipe in the skill means
re-discovering it every session. The first DA call to
`execute_code` should be the pivot, not the third.

Reference: hermes-agent michi cycle 2026-09-04 (windows-notify
feature) — DA lost 3-5 min on the broken tools before pivoting.

## Pre-DA state gate — snapshot before edit, ask once if drift

Even with a Super Prompt that names branch + last commit + worktree
state, **those facts drift** between SP write and michi exec. One
cycle's SP said "clean working tree, branch main, last commit
5bca0e345" — reality was `wip/main-features` with 7 files dirty
from a parallel session (gateway wizard work, not the SP's scope).
The michi flow's "user decides" handle saved the cycle, but only
after a wasted 5-min scan.

**Recipe (3 lines, run before the first edit):**

```bash
git -C <repo> status --short | head -20
git -C <repo> branch --show-current
git -C <repo> log -1 --oneline
```

Compare each to the SP's claims. If ANY fact disagrees, surface
the divergence in **one** free-text ask before touching the tree:

> SP says clean + main + 5bca0e345. Reality is dirty
> (7 modified, 20 untracked) + wip/main-features + <other-sha>.
> Branch mismatch + parallel work in tree. OK to write into
> the dirty tree, or feature branch from HEAD?

**Cost of skipping the gate:** 2-5 min of confusion mid-DA when
`git diff` shows the whole file as removed+added because the
working tree's HEAD ≠ the SP's expected base, or you accidentally
branch off the wrong commit. The state gate is 5 seconds.

**Why free-text, not multi-choice:** the user already knows what
they have on disk. The ask is "still on wip/main-features? / still
want feature branch from HEAD?" — one-word answer, not a 4-option
list. (This is the michi "default to free-text" Style rule applied
to the pre-DA gate.)
