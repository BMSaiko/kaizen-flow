# Michi — pitfalls

Movido de `SKILL.md` (## Pitfalls); texto integral, 26 entradas.

## 1. Treating `/michi` as a single-shot: the user may want to pause at any

- Treating `/michi` as a single-shot: the user may want to pause at any
  phase. Read the room.

## 2. Re-asking the user a fact they already gave you

- **Re-asking the user a fact they already gave you.** "dev branch? you
  said dev" → you wasted a turn. Multi-choice `clarify` for already-stated
  facts is the canonical waste — see Style section.

## 3. `/michi skip grill` + vague large-scope instruction

- Skipping the grill phase "because it's obvious": obvious to whom? The
  plan pays for the alignment now or the rework later.
  - **`/michi skip grill` + vague large-scope instruction** (e.g. "refactor
    the whole backend", "rescrever X por que funciona mal"). Skip-grill does NOT
    mean zero alignment — o user waiveed the conversation, not the safety net.
    **Mesmo com skip grill, a 1ª pergunta do DR tem de ser 1 free-text sobre o
    symptom real** ("cola o erro / o card / a mensagem UI"). Vague "não funciona"
    tem ≥3 significados diferentes; perguntar 1 vez é mais barato do que escrever
    1 test para a layer errada (BUG 3h lição, atlas wrapper cycle 2026-09-03).
    Minimum gate antes de DR/DP: (1) a 5-minute scan que nomeia o que existe
    (`ls`, line counts, exported symbols, route registrations, tests touching
    it); (2) a courage-level table (A=safe refactor / B=+validation /
    C=+framework) com one-line risk per row; (3) **one decision** ask
    ("qual level, qual scope") — não multi-question clarify. A table é o
    alignment artifact. Re-asking facts já stated (branch, project, etc.)
    wastes the turn que o user gastou a skiptar grill. Ver
    `references/michi-skip-grill-play.md` para a worked shape.
  - **EOL / CRLF symptoms: first action is always `git config --show-origin --get core.autocrlf`** (atlas EOL cycle, 2026-09-04). The user reports "EOL mixto no repo X". The reflex is to start writing fixes. Don't. First one-liner:
    `git config --show-origin --get core.autocrlf` (and `core.eol`). Three possible shapes:
    1. **`false` at local** + `true` at system → **system overrides local on checkout**. The `.gitattributes` `eol=lf` is a no-op. `git checkout HEAD -- <file>` STILL writes CRLF. **Fix:** rewrite files via Python (`.read_bytes().replace(b'\r\n', b'\n')` + `git add` + commit). Cannot `--system --unset` without admin.
    2. **`true` at local** → user's local config opted-in. `git config --local core.autocrlf false` fixes it.
    3. **`input` or absent** → likely `text=auto` in `.gitattributes` only. Normalize + commit + lock.
    The waste pattern: spend 5 min trying `-c core.autocrlf=false checkout`, `GIT_CONFIG_NOS_SYSTEM`, `git rm --cached`, etc. — none of those override a system-level `true` on checkout. The 1-line `show-origin` triage costs 0.5s and tells you which shape you're in. **Rule:** EOL debug starts with `show-origin`, always.
  - **Never broad-kill during michi gates — narrow `taskkill /F /IM <name>` or by PID** (atlas EOL cycle, 2026-09-04). When a Phase 2 gate (e.g. `vite build`) hangs in the sandbox, the reflex is `taskkill /F /IM node.exe /T`. That kills **every** node process — including the user's own dev server / daemon / IDE plugin host — not just the hung one. Even if the agent "got lucky" (no node processes left after the kill, the hang is gone), the user may have lost work-in-progress in another shell. **Recipe:** (1) `tasklist /FI "IMAGENAME eq node.exe" /FO TABLE` to see what's there. (2) If the list is >1 process, kill by **PID** (`taskkill /F /PID <pid>`) after `wmic process get ProcessId,CommandLine | findstr <pattern>`. (3) If you're sure only 1 process is yours, kill by name (`taskkill /F /IM node.exe`). **Cost of a broad kill:** user loses unrelated work. **Cost of the narrow recipe:** 30s. Default to narrow.
  - **`runCIGate`-style "build inside dev repo" pattern: isolate output to a sibling dir, don't touch `dist/`** (atlas EOL cycle, 2026-09-04). When the dev server (`npm run dev`) and the CI gate (`vite build`) share the same `dist/`, the build clobbers the dev's open handles / hot-reload watcher / port. The fix is NOT a new worktree manager (YAGNI), it's `--outDir` to a sibling dir (`dist-gate-<ts>/` or `.ci-gate/<ts>/`), gitignored, cleaned best-effort after the gate. **BC contract for the gate function:** add an optional `wtDir` param so future worktree-isolated callers can pass a real isolated worktree; current callers pass `repo` and get the sibling-dir behaviour. Pattern (the one shipped):
    ```ts
    async function runCIGate(repo: string, wtDir?: string) {
      const ciRoot = wtDir || repo
      // ... tsc gate on ciRoot ...
      let outDir: string | null = null
      if (!wtDir) {
        outDir = join(repo, '.ci-gate', String(Date.now()))   // sibling dir, not dist/
        const bd = await runCmd('vite.cmd', ['build', '--outDir', outDir], repo)
      } else {
        const bd = await runCmd('vite.cmd', ['build'], ciRoot)
      }
      if (outDir) try { await rm(outDir, { recursive: true, force: true }) } catch {}
    }
    ```
    The BC signature (`wtDir?` optional) is load-bearing — the 2 existing callers (`w:approve-agent`, `w:approve`) keep working without changes; future worktree-aware callers can opt in.
  - Bundling multiple unrelated changes in one michi run. If the user's
    project has two distinct goals, suggest splitting.
  - **`/michi skip grill` + "rescrever tudo / reescrever de raíz" (Atlas wrapper cycle, 2026-09-03).** "Rescrever" é o pedido mais perigoso que se pode fazer num refactor — perde 7+ bugs resolvidos (no caso do `atlas-wrapper-python`, a skill tem-nos todos documentados como BUG 1/2/3/3b/3c/3d/3e/3f/3g/3h). Regra operacional: antes de propor o plano de reescrita, **extrair a lista de invariants que o código actual carrega** (ler o `atlas-wrapper-python/SKILL.md` secção "Não-objetivos" — lá estavam os motivos pelos quais o autor original não fez a substituição). Honra-os no novo design. "Rescrever mais simples" sem o why-keep-this list = reescrita que reintroduz bugs já pagos. A pergunta grátis pós-DR deve ser: "o que MORRE / o que FICA / o que MUDA" — não "como é que queres o novo".
  - **`extract 1 helper from 4 copies` é o padrão natural de skip-grill DR (Atlas wrapper cycle, 2026-09-03).** Quando o DR encontra **N cópias idênticas** de uma string-array / função / template (no atlas: 4 spawn sites `python -c "..."` em `launchHermes`/`launchDp`/`launchGitOp`/`spawnHeadless`), o DP default é **extrair 1 módulo + N chamadas magras**. Não refactorar cada site individualmente — extrair primeiro, simplificar depois. O win em LOC vem dos call-sites a encolher, não do helper a ser mais pequeno. Audit table row pattern: `phase | 4 cópias hoje | 1 helper + 4 chamadas depois | redundant=no (DRY)`. O helper exporta 1 função `runCard(opts) -> Promise<{code, mergeResult}>` que encapsula heartbeat + auto-merge + log capture; os 4 sites passam a `await runCard(...)` em 3-5 LOC. Reaproveita a regra "tier 2: already in this codebase" do Ponytail.
  - "Gates passed" without the actual command output. State the command and
    its result; the user does not trust vibes.
  - **Parse-only gates are not gates for runtime/UI changes** (wezterm michi
    2026-09-02 Round 4). `wezterm show-keys RC=0`, `lua -p`, `tsc --noEmit`
    only prove the file parses. Bugs in `update-right-status`,
    `format-tab-title`, OSC handlers, pane hooks live at EVENT-FIRE time —
    when the runtime uses the value, not at parse. For visual/runtime
    heuristics Phase 5 needs ONE runtime proof: reload, trigger the event,
    log/screenshot the result. If you cannot run it yourself, say so in
    the report and stop — do not declare done on parse alone.
  - **esbuild CSS minifier trips on custom-property names with inner dashes** (atlas polish-A michi, 2026-09-04). Adding `--space-1: 4px; --space-2: 8px;` inside a CSS file builds and runs fine in dev, but `vite build` → esbuild minify emits `[WARNING] Expected identifier but found whitespace [css-syntax-error]` on the first var with `--name-N` (custom-property names that contain a hyphen between the leading `--` and the rest). Confirmed with two separate build runs. **Fix:** prefer `--space1` (no inner dash), OR if the new scale is just an alias of an existing one, drop it (YAGNI — the existing `--s1..7` already covers it). Don't add scales the toolchain can't parse. Surface the warning in the report and strike the scale from the DP before commit, don't paper over with `// eslint-disable`.
  - **`npm install --save-dev` of gate tools (lighthouse, @axe-core/cli) can fail with `ETARGET` against versions the registry HAS** (atlas polish-A michi, 2026-09-04). Symptom: `No matching version found for ws@^8.21.3` / `axios@^1.19.0` even though `npm view ws@8.x versions --json` lists them. Cause: a stale npm cache holding old manifests. **Recipe:** `npm cache clean --force` then retry. One line, 30s, fixes it. Cost of skipping: a 10-min yak-shave chasing a phantom network/proxy issue.
  - **Vite build "hangs at 240s" is often `npm install` async cleanup, not vite** (atlas polish-A michi, 2026-09-04). When `npm run build` appears to hang in the sandbox with no stdout, suspect (1) the previous `npm install` is still flushing its postinstall scripts into stdout (the vite "hang" was actually the install tail), OR (2) an earlier bg process from the same tool family is still holding the lock. Recipe: poll the build log file with `tail -f` for the `transforming...` line before concluding it's hung. A real vite hang shows nothing; an install-tail shows `added N packages`. If the install-tail is the culprit, just wait it out (≤60s) and the build then completes in 1-2s.
  - **Diagnostic probes via shell get blocked — let the gate tool itself report** (atlas polish-A michi, 2026-09-04). When `vite preview` is up and you want to know if it's responding, DO NOT probe via `curl http://127.0.0.1:4321/` or `node -e "fetch(...)"`. The user has blocked both patterns. Just run the gate tool (`npx lighthouse http://...`, `npx @axe-core/cli http://...`) — they handle their own connection attempts and emit a clean error if the URL is unreachable. Cost of probing yourself: 1+ blocked calls + lost trust. Cost of running the gate: 0 — the tool was about to run anyway.
  - **Lighthouse perf ≥ 95 is noisy — use 3-runs median, not 1st run (michi 2026-09-04, atlas polish-A).** Lighthouse on the same code can return 90 / 95 / 99 across 3 runs (range 6-9 points confirmed). Per michi rule "Gates passed" without the actual command output" a single perf=99 is a vibe — the user does not trust a single measurement. **Recipe when the gate is `Performance ≥ N`:** run **3 times**, take the median, and report all three numbers. If the median ≥ N: gate PASS. If the median < N: gate FAIL, the 3 numbers are evidence of real variance, not "bad luck on one run". The Ponytail exception does NOT apply here — running the gate 3× is the gate, not a redundant probe (the SP cost is "≥ 95 in CI", not "≥ 95 on the first try"). **Cost of skipping:** the agent commits with perf=99, the next CI run returns perf=88 (also real, also noisy), the user has to re-decide. **Companion rule:** when the gate fails for the same code on different runs, the fix usually is NOT in the code but in a runtime artifact (font CDN cache, Chrome profile state, network jitter). The code-side fix is "ship what the median says, then iterate". **Do NOT keep re-running until you get a passing number** — that's p-hacking, not measurement.

## 4. Interruption mid-DA leaves the on-disk state 80% done, 0% committed (michi 2026-09-04, atlas polish-A recovery

- **Interruption mid-DA leaves the on-disk state 80% done, 0% committed (michi 2026-09-04, atlas polish-A recovery).** When the previous session was killed mid-DA (Hermes restart, model timeout, user `/stop`), the uncommitted work is in the worktree's working tree but NOT in git. The branch HEAD equals the parent's HEAD. The next agent scanning the worktree via `git status` sees N files modified and 0 commits ahead — and may mistake it for "no work in progress" or "dirty tree, start over". **Recipe (atlas polish-A validated):** 1) `git status --short` + `git diff --stat` to inventory the uncommitted work. 2) If files in the worktree are 80%+ of the planned work, the work IS done — write a v2 DP that says "recovery, not clean start" (use the `DP supersession by rename, not overwrite` pattern: `git mv plans/<slug>-DP plans/<slug>-DP-v1`, then write v2 at the canonical path with a `supersedes: plans/<slug>-DP-v1/DP.md` frontmatter line). 3) Run gates against the recovered tree. 4) Commit. **Anti-patterns:** (a) wipe-and-restart, throwing away the on-disk work — that's a $30min mistake, you redid 80% in a worse shape; (b) `git stash` + start over — same outcome, with extra steps; (c) write v2 DP at `<slug>-DP-v2/` instead of renaming v1 — splits context, makes "where is the live plan" ambiguous. **Companion rule:** if the previous session's work is partially in the worktree AND partially in a stash, treat them as a single recovery decision. Popping the stash into the recovered worktree conflates two sessions' scopes; surface both as separate decisions in the same ask. **Detection that you already lost the work:** `git status --short` no longer shows the files you expected; recovery = redo.

## 5. Banner-sectioned single-file split > N-file split when class-name families overlap heavily

- **Banner-sectioned single-file split > N-file split when class-name families overlap heavily** (atlas polish-A michi, 2026-09-04). SP §6 may say "split into 8 files via `@import`", but when the CSS has heavy cross-class overlap (`.kmodal-actions` overlaps with `.modal`, `.dash-head` overlaps with `.kcard`, etc.), the bin-by-class heuristic produces 100+ fragmented runs across 7 files. **Default for "split for navigation, not perf":** add a TOC at the top + 6-9 SECTION banners + keep ONE file. The SP allows "OR sectioned with clear banner comments" — that branch is the boring-but-correct one. Cost of forcing N-file split: 30+ min of bin-by-class heuristics + cascade-order risk. Cost of banner sectioning: +2.5 KB of comments, zero cascade risk.
  - **`patch` tool silently mis-indents inside deeply-nested closures; `tsc --noEmit` doesn't catch it (atlas-mundo-workflow-michi, 2026-09-05).** Symptom: a `patch` that adds a block at the end of a large function (or near a `}` of an inner arrow / `.then` callback) can land the new lines at the wrong indentation depth. The closing `}` that was supposed to close `renderNotes` ends up closing the wrong enclosing function, and the new block lives inside a `.then(ok => {})` callback instead of the top-level scope. `tsc --noEmit` rc=0 — closures nest happily in JS, and template-string HTML inside the misplaced block parses fine. **Manifests at runtime:** the feature wired into the misplaced block never executes on the happy path (only when some unrelated callback fires). User reports "X feature doesn't show up in the UI"; agent wonders why. **Recipe (pre-patch):** when patching near the end of a large function (>200 LOC), open the file and **print each line with its leading-space count** around the patch site. Locate the function's intended closing `}` by indent depth, not by visual proximity. See `references/michi-patch-indent-audit.md` for the executable procedure. **Recipe (post-patch):** `wc -l <file>` BEFORE and AFTER the patch. If line count dropped by more than the patch's net delta (i.e. a `}` was consumed), the patch crossed scope — revert via `git checkout HEAD -- <file>` and re-patch with corrected anchoring. **Cost of skipping:** the feature ships in a "wired but never reached" state, gates all pass, manual smoke reveals the gap, one user round-trip. **Companion rule:** when patching template-string-heavy JS (where the HTML inside the misplaced block still parses), no static check will save you — brace-depth is the only audit that finds this. Same family as the Worktree-trap pitfall (silent, type-clean, only visible by inspection).
  - **Honour `DA` as a jump, not a re-run.** `/michi DA` after `/michi <idea>`
    means "go implement now with what we have". Do NOT re-run grill/DR/DP
    from scratch — the earlier phases already happened. Re-pickup is
    context restoration, not re-execution. If the user wants a phase,
    they say `/michi dr` or `/michi dp`, not `DA`.

## 6. `/michi` + "no questions, do all phases" is a bounded auto-pilot, not infinite licence (michi 2026-09-04, atla

- **`/michi` + "no questions, do all phases" is a bounded auto-pilot, not infinite licence (michi 2026-09-04, atlas polish-A).** When the user says "no questions, do all phases" alongside a Super Prompt, the auto-pilot covers the EXECUTION path, NOT the gate decisions when gates fail. **Rule:** apply ponytail defaults internally for low-stakes forks (worktree state = recover+finish, stashes = leave alone, single commit per phase boundary), but **DO NOT auto-decide a SP-contradicting constraint** (e.g. SP §4 demands `Performance ≥ 95` AND SP §5 forbids touching `index.html` — the only fix that gets to 95 is font preload in `index.html`, mutually exclusive). For contradictory constraints OR a non-recoverable gate failure, **stop and report**, even if the user said "no questions". The user is granting execution autonomy, not sign-off on a contract change. **Recipe:** at the first gate that fails for a reason that cannot be fixed without violating another SP clause, surface the contradiction in the report (cite both clauses, the perf numbers, the proposed fix) and ask for the one decision that breaks the tie. Do not silently ship a "PASS-WITH-CAVEAT" commit. The caveat-only path is acceptable ONLY if the user explicitly approves it in the same turn; the report can recommend it but the commit waits. **Cost of bypassing this rule:** the user comes back, sees perf=90 + the SP said ≥95, and the entire epic needs to be re-decided from a position of "the agent already shipped something I have to defend". **Anti-pattern:** the agent decides "perf=90 is good enough, let me commit and report" — that is a unilateral contract change.
  - **`Worktree trap` (canonical).** A repo with `.wt/<name>/` directories
    holds checked-out worktrees of past features. `read_file` /
    `search_files` / `patch` may resolve a path to a worktree instead of the
    working tree. Before editing: `git rev-parse --show-toplevel` +
    `git status --short -- <file>`. After: `git diff -w -- <file>`. If
    the diff shows the whole file as removed+added, the file you edited
    is not the one Git is tracking — revert and re-read from the working
    tree, NOT the worktree. Also: a 1-line "minimal" patch that crosses
    paths can silently drop unrelated lines from the live version. Cheap
    integrity checks: `wc -l` and CRLF count (`b'\r\n'` in Python)
    before AND after applying. If line count drops unexpectedly, the
    patch crossed paths; revert.
    - **`patch` to a deleted worktree dir succeeds silently and writes to a path git no longer tracks (atlas keyboard-first, 2026-09-05).** If the user (or a prior `git worktree remove`) deleted a worktree dir while the dir's on-disk path still resolves, `patch` (and `write_file`) to that path appears successful but lands in a directory that is no longer git-aware. Symptom: `git status` shows nothing after the patch; the file exists on disk but is not in any worktree's tracking. The agent may think "patch didn't take" and re-issue, then "still doesn't take" and conclude the tool is broken — when actually the writes are landing somewhere git can't see. **Recipe when you suspect this:**
      1. Run `git worktree list --porcelain` — confirm every path that the work is supposed to land in.
      2. If the path is missing from `worktree list`, the writes are leaking to a stale dir. Fix by re-creating the worktree (`git worktree add <path> <branch>`) OR by patching the parent checkout's path instead (`code/src/...` not `code/.wt/<name>/src/...`).
      3. **Cheap check before patching** when the path is inside `.wt/<name>/`: `git -C <path> rev-parse --show-toplevel`. If it returns the worktree's toplevel, the patch is safe. If it errors with "not a git repository", the dir is a stale copy.
      4. **Post-patch verify:** `git -C <parent> status --short` lists the file as `M` or `??`. If the parent shows nothing, the patch leaked.
      **Why this is a data-loss class:** the writes are NOT in git's working tree, so a `git stash`, `git checkout`, or `git worktree remove` later can destroy them silently. The agent has no warning. Detection in this session: I patched `src/ui/palette.ts` in the deleted `.wt/atlas/keyboard-first/` after the worktree had been removed (only the empty dir remained). The patch tool reported success; `git status` in the parent showed nothing. Cost of detection: 1 round-trip to re-apply in the parent. **Rule:** after every michi cycle that removes its worktree, the next cycle's first patch must be in the parent checkout, not in the worktree dir. The session-scoped worktree pattern ends the moment `git worktree remove` runs.
  - **`Worktree trap` — stale/prunable recovery (michi 2026-09-04, atlas polish-A cycle).** A worktree can show up as `prunable` in `git worktree list --porcelain` with the message `gitdir file points to non-existent location` — even when the on-disk directory still contains the uncommitted work, the node_modules, and the .lighthouse/.axe/.screens gate artifacts. The `.git` pointer file inside the worktree dir is missing, but the rest is intact. This happens when a previous session was interrupted mid-DA without committing. **Recipe to recover without losing on-disk work:**
    1. `git worktree list --porcelain` — confirm the path is `prunable` and the `.git` pointer is gone.
    2. `git worktree prune` — clears the prunable registration. The on-disk dir is untouched.
    3. `git worktree add <path> <existing-branch>` (NO `-b`) — re-registers the existing dir against the existing branch. This restores the `.git` pointer without `git checkout`-ing the files, so the uncommitted work survives.
    4. Verify: `git -C <path> status --short` lists the uncommitted files; `git -C <path> rev-parse --abbrev-ref HEAD` returns the branch.
    **Anti-recipe:** `git worktree remove --force` + `git branch -D` + re-add with `-b` — this deletes the on-disk work. The "remove" verb is literal. `git worktree prune` is the non-destructive verb. When the dir is intact and the work is on disk, prune + re-add is the only safe path. **Detection that you already lost the work:** the worktree dir was deleted, the branch was force-deleted, and `git fsck` cannot recover uncommitted files (committed history is recoverable, untracked is not). Recovery from that state = redo. **Companion rule (atlas 2026-09-04):** if the previous session's work has both an uncommitted-tree portion AND a stashed portion (`git stash list` non-empty), treat them as a single recovery decision. Popping the stash into the recovered worktree conflates two sessions' scopes — leave the stash alone until the user has reviewed the on-disk state, then surface the stash as a separate decision in the same clarify round.
  - **`git checkout <other-branch>` aborts on uncommitted changes** (michi
    2026-09-03, master-merge cycle). When a session leaves edits on disk
    (e.g. another agent's wezterm work) and you need to switch branches to
    ff-merge dev→master, `git checkout master` will fail with
    "Your local changes would be overwritten by checkout". **Recipe:**
    `git stash push -m "ponytail: pre-<branch>-merge stash"` → checkout
    → ff-merge → push → checkout back to original branch →
    `git stash pop`. If `stash pop` reports conflicts, decide file-by-file
    whether the stashed or the fresh checkout is correct; never blind-pop
    on a worktree.

  - **Working tree not yours (parallel agent, michi cycle 2026-09-04).**
    Symptom: 20+ files dirty with 0 real content diff, stashes named
    `wip-other-agent-*` or `other-agent-wip`. Cause: another agent/editor
    session touched the shared dev branch in parallel. **Before michi DA:**
    run `git worktree list` + `git status --short | wc -l` +
    `git stash list | grep -i other-agent`. If signal matches, **isolate
    in `feature/<slug>` branch from current HEAD** (carry dirty mods
    into the new branch with `git checkout -b` — they come with you;
    do NOT stash first, you'll lose them). Stash only the *other agent's*
    dirty mods pre-merge to keep your work separated, ff-merge your
    feature, then `stash pop` restores the parallel work.
    Skipping this = a recover cycle ("I edited, the work vanished").

## 7. "Bug report" ≠ "the thing to fix". Ask for the actual error string before DR/DA (Atlas michi cycle, 2026-09-03

- **"Bug report" ≠ "the thing to fix". Ask for the actual error string before DR/DA (Atlas michi cycle, 2026-09-03, Phase 1).** User said "click Aprovar, nada acontece em nehpzsd7". I assumed the agent handler was wrong, wrote 5.3KB of test for it, all 16 asserts green — handler was already correct. The real bug surfaced only AFTER the user pushed the actual error message: `CI gate falhou (typecheck): 'npm.cmd' is not recognized`. Real fix was 2 lines in `server/api.ts` (cherry-pick of `f0e0e39` from an unmerged branch). Cost of the missed ask: 1 wasted test file, 1 wasted "report" round, the user's "faz um DR antes de mexer" got short-circuited by me diving into the wrong layer. **Rule:** when the user reports a "X doesn't work" symptom, the FIRST response is one free-text question for the actual error string (or the .log tail, or the failing command + its stdout/stderr), NOT a "let me trace the code" reflex. The error string tells you which of 3-5 plausible layers is actually broken; without it you're guessing. Cheaper to ask 1 question than to write 1 test for the wrong layer. **Trigger phrases that warrant the ask:** "X não funciona", "Y está partido", "Z não avança", "click faz nada", "stuck em doing/review". Skip the ask only when the user has ALREADY pasted the error in the same turn.

## 8. When michi is loaded but the cycle is hijacked mid-stream by an ops request, Reflect still owes the user a fri

- **When michi is loaded but the cycle is hijacked mid-stream by an ops request, Reflect still owes the user a friction report (Atlas 2026-09-02).** If user invokes `/michi` and then immediately asks for a quick task ("roda os testes", "faz commits para os changes do dev") that bypasses grill/DR/DP/DA, do NOT skip Reflect at session end. The ops request itself is a data point — what worked, what didn't, what new tool pattern surfaced (e.g. the `M ` stat-cache gotcha, the untracked-debug classification, the `git checkout <ref> -- <file>` EOL non-normalization). Reflect at the end of the *session* even if no michi phase ran. One-line "Nothing to evolve" is fine when truly nothing surprising happened.

## 9. Reflect is a stop point, not a segue (atlas backend refactor, 2026-09-02)

- **Reflect is a stop point, not a segue (atlas backend refactor, 2026-09-02).** After surfacing friction, do NOT chain the response with "next phase preview" or "ready to do X?". The Reflect template's three exit paths (patch michi / new helper skill / backlog bullet) all require the user to weigh in. Output Reflect, then a single line: "your call" or "wait for go". The michi Quick reference table implies a single flow per cycle; in practice, multi-phase refactors need Reflect-after-each-phase AND explicit user continuation. When in doubt, default to stopping.

## 10. Per-phase commit cadence in a multi-phase DA is a real workflow (atlas backend refactor, 2026-09-02)

- **Per-phase commit cadence in a multi-phase DA is a real workflow (atlas backend refactor, 2026-09-02).** When the plan has ≥3 DA phases, ask the user **at plan sign-off** whether to commit per phase. Two valid cadences: (a) "one commit per phase after gates" — safest, bisect-friendly, user reviews each commit; (b) "one big commit at the end" — fewer ceremony interruptions, but a broken mid-cycle means re-doing all of it. The default for big refactors is (a). Honour "one commit only por phase" as a hard cap — do not split a single phase into multiple commits unless the user asks. **Do not auto-commit even with a cadence approved** — michi's "user owns git operations" rule still stands. After gates RC=0 for a phase, **show the proposed commit message and wait**. `git add` is fine to stage, but the actual `git commit` runs only after the user says go.

## 11. Refactor clusters: commit EACH new file before moving to the next, not at end-of-DA (atlas wrapper-replacement

- **Refactor clusters: commit EACH new file before moving to the next, not at end-of-DA (atlas wrapper-replacement cycle 2026-09-03).** A refactor that creates N new files (e.g. extracting a `server/lib/<name>.mjs` + `.d.mts`, refactoring M call-sites in `api.ts`, patching K tests) is a "refactor cluster" — the natural unit of commit is "one module + the call-sites that use it + the tests that protect it", not "all M+K+N files at the end". **Why:** between michi phases, ANY process that mutates the working tree (atlas worker running `git worktree add`/`worktree remove` on a card, a parallel agent's auto-commit, a Vite dev server restart that re-touches files) can clobber untracked work. In this session, I created `server/lib/run-card.mjs` + `run-card.d.mts` + patched `api.ts` (5 call-sites) + 3 tests in one DA, all untracked. The next atlas card ran a worktree that `git checkout`-reset `api.ts` and removed the untracked `lib/` files — I lost an entire refactor and had to redo it. **Recipe:** after creating the first new file, propose "module scaffolded, commit now?" (1 commit per cluster); after the first call-site swap, propose "1 of 5 done, commit now?"; etc. The "one commit per phase" rule covers phase boundaries; this rule covers the **intra-phase** case where one phase creates N files that may be co-clobbered. The cost of "commit now" is one user approval; the cost of "wait until end of phase" is the entire phase if anything in the same working tree mutates between. **Detection that you already lost work (the post-mortem signal, 2026-09-04):** the moment you come back to a session and find your previously-working tree has "fewer files" than you left it with, do this **before** assuming the files are still there: (1) `git status --short` — if files you authored aren't in the `??` list anymore, they're gone, not hidden. (2) `git status --short` for any `M ` line on a file you also touched — the diff is a reset if the file is "wholesale" replaced (huge `+N/-N` block). (3) `git ls-files <path>` for the canonical file list — if a file you wrote isn't there, it's actually gone. Recovery: redo. The **cheapest insurance** is the cluster-commit recipe above, applied proactively. If you find the loss post-hoc, do **not** try to recover via `git fsck` / reflog — those are for committed history; untracked files are gone, period.

## 14. Post-child work (cleanup, merge, push) must be detached from the orchestrator's event loop (atlas wrapper-repl

- **Post-child work (cleanup, merge, push) must be detached from the orchestrator's event loop (atlas wrapper-replacement 2026-09-03).** When a dev-server process (Vite plugin, watch-mode CLI, long-lived daemon) spawns a child AND needs to do post-processing after the child exits (auto-merge, file cleanup, push, status report), do NOT chain the post-processing in a `.then()` on the child's exit promise. The `.then()` runs in the orchestrator's event loop; if the orchestrator restarts between child-exit and post-processing-finish, the post-processing dies mid-flight, leaving the system in a half-done state (card marked "running" forever, no merge, no cleanup). **Pattern (atlas 2026-09-03):** extract the post-processing to its own file and spawn it as a **detached** sub-process from the orchestrator:
  ```js
  // in the orchestrator (Vite plugin)
  if (childExited === 0) {
    spawn(process.execPath, [postProcessFile, ...args], {
      detached: true, stdio: 'ignore', windowsHide: true,
    }).unref()
  }
  // orchestrator returns / moves on. The detached sub-process keeps running
  // even if Vite restarts.
  ```
  The detached sub-process must write its own status to disk (e.g. `state: 'merge-failed'`) so the orchestrator's next read (after restart) sees the result. **Diagnostic that you have this problem:** a successful child exit + a `.status` file that still says `state: 'running'` + commits that landed in a worktree but were never merged = the orchestrator died before the `.then()` finished. **Trade-off:** detached sub-processes can't propagate errors back via promise rejection; you must rely on the status-file contract. That's why the status file is the source of truth, not the return value of the spawn. **Trigger phrase:** "after the child exits, do X" — if X is anything more than "log a line", extract it.

## 15. "Faz um ajuste" to a signed-off plan means: respect the why, not just the what (atlas backend refactor, 2026-0

- **"Faz um ajuste" to a signed-off plan means: respect the why, not just the what (atlas backend refactor, 2026-09-02).** When the user adjusts a plan mid-DA ("separate into files earlier", "do this phase first", "skip this part"), they are not adding work — they are re-weighting the plan. The michi rule "do not re-ask facts the user already stated" applies: do not push back with "but the plan said X". Instead: (1) re-state the *why* the user gave ("so I can debug later"); (2) propose a concrete reshuffle that respects it; (3) wait for go. If the user's adjustment makes the current in-progress phase wrong, restart that phase with the new shape — the other phases' validity is unchanged unless the user says so. Do not silently fold the adjustment into the running phase; that hides the contract change.

## 16. Post-DA correction list is a phase, not a restart (atlas main-chat michi, 2026-09-04)

- **Post-DA correction list is a phase, not a restart (atlas main-chat michi, 2026-09-04).** When DA has shipped + report done + commit done, and the user replies with a numbered list of corrections (mix of bug fixes + new features), this is **NOT** the "Review restart on user pushback" rule (that rule is for "it's wrong/broken" — a *quality* signal). A correction list is a *delta* signal: the work is accepted, the contract is changing. **Recipe:**
  1. Read the entire numbered list before acting on item 1. The list itself is the alignment; do not interleave clarifying questions.
  2. Classify each item: **bug** (broken behaviour, same scope) vs **feature** (adds new scope). Bugs stay in DA. Features need a new DP or a clear "YAGNI-skip" call.
  3. Apply each as a single fold-in DA pass: code + tests + re-run gates in one batch. Do NOT split into per-item commits unless the user asks (overhead without value at this size).
  4. Do NOT re-run grill/DR/DP from scratch. The user already saw and approved the shape. The corrections are deltas to that shape.
  5. After all items land, re-run the full report with a 1-line "Δ" section showing what changed since the previous commit. **Diagnostic signal** that you got this wrong: the user replies with "também:" / "outra coisa:" / "mais:" — meaning the first round of fold-in did not capture everything, and you should be in this pattern again, not restart from Phase 1.

## 17. Numbered-correction list is a contract, parse it as one (atlas main-chat michi, 2026-09-04)

- **Numbered-correction list is a contract, parse it as one (atlas main-chat michi, 2026-09-04).** Mirror of the "User responds with item-list" Style rule, but in the reverse direction. When the user gives a numbered list of corrections ("1. ... 2. ... 3. ..."), each item IS the requirement — do not re-ask, do not multi-choice clarify, do not batch into one. Honour each as accepted. The first response after the list should be a **summary table** of all items (item | classification | change), THEN start applying. Without the summary, you risk: reordering items, dropping an item, or splitting a "feature + its test" into two separate DA passes the user did not ask for. **Forbidden follow-ups** after a numbered-correction list: "want me to also..." / "should I refactor X while I'm there?" — these are scope creep. Apply what was listed; surface YAGNI skips in the report, not the conversation.

## 20. Pre-DA state gate: snapshot `git status` + `git branch --show-current` + `git log -1` before any edit (hermes-

- **Pre-DA state gate: snapshot `git status` + `git branch --show-current` + `git log -1` before any edit (hermes-agent 2026-09-04, michi cycle).** Even with a Super Prompt that names branch + last commit + worktree state, **those facts drift** between SP write and michi exec. In one cycle the SP said "clean working tree, branch main, last commit 5bca0e345" — reality was `wip/main-features` with 7 files dirty from a parallel session. **Recipe:** before DA, run a 3-line state snapshot:
  ```bash
  git -C <repo> status --short | head -20
  git -C <repo> branch --show-current
  git -C <repo> log -1 --oneline
  ```
  Compare each to the SP's claims. If ANY fact disagrees, surface the divergence in **one** free-text ask before touching the tree (e.g. "SP says clean + main; reality is dirty + wip/main-features with 7 modified files from a parallel session. OK to write into the dirty tree?"). **Cost of skipping the gate:** 2-5 min of confusion mid-DA when `git diff` shows the whole file as removed+added because the working tree's HEAD ≠ your expected base, or you accidentally branch off the wrong commit. **Why free-text, not multi-choice:** the user already knows what they have on disk; ask "still on wip/main-features? / still want feature branch from HEAD?" — the answer is one word.

## 21. `git checkout <other-branch>` aborts on uncommitted changes

- **`git checkout <other-branch>` aborts on uncommitted changes** (michi
    2026-09-03, master-merge cycle). When a session leaves edits on disk
    (e.g. another agent's wezterm work) and you need to switch branches to
    ff-merge dev→master, `git checkout master` will fail with
    "Your local changes would be overwritten by checkout". **Recipe:**
    `git stash push -m "ponytail: pre-<branch>-merge stash"` → checkout
    → ff-merge → push → checkout back to original branch →
    `git stash pop`. If `stash pop` reports conflicts, decide file-by-file
    whether the stashed or the fresh checkout is correct; never blind-pop
    on a worktree.

  - **Working tree not yours (parallel agent, michi cycle 2026-09-04).**
    Symptom: 20+ files dirty with 0 real content diff, stashes named
    `wip-other-agent-*` or `other-agent-wip`. Cause: another agent/editor
    session touched the shared dev branch in parallel. **Before michi DA:**
    run `git worktree list` + `git status --short | wc -l` +
    `git stash list | grep -i other-agent`. If signal matches, **isolate
    in `feature/<slug>` branch from current HEAD** (carry dirty mods
    into the new branch with `git checkout -b` — they come with you;
    do NOT stash first, you'll lose them). Stash only the *other agent's*
    dirty mods pre-merge to keep your work separated, ff-merge your
    feature, then `stash pop` restores the parallel work.
    Skipping this = a recover cycle ("I edited, the work vanished").

## 22. Junctions/symlinks do NOT auto-propagate from parent to worktree (atlas strip-kanban cycle, 2026-09-05)

- **Junctions/symlinks do NOT auto-propagate from parent to worktree (atlas strip-kanban cycle, 2026-09-05).** When the parent checkout has a reparse point (NTFS junction, symlink) at a path that is gitignored (e.g. `code/data/` → `vault/live-data/`), the worktree gets a NORMAL empty directory at the same path. The worktree does NOT inherit the reparse. **Symptom:** parent has the canonical data on disk (junction target intact, 633KB of `kanban.json` across 5 mundos), but the worktree has a plain empty directory, so any smoke test reads `{"ver":0,"items":[]}` (zero state) instead of real data. The integrity check `git status` reports nothing (file is gitignored) so the violation is invisible to git-only verification. **Recipe:** before trusting a worktree smoke result, verify the runtime data dir is the SAME source as parent. On Windows, `is_reparse_point` via `ctypes.windll.kernel32.GetFileAttributesW(<path>) & 0x400` (or `fsutil reparsepoint query <path>`); on POSIX, `path.is_symlink()`. If parent has a reparse and worktree does not, recreate it: `cmd /c mklink /J <worktree-path> <target>` (Windows junction — survives `shutil.rmtree`, unlike symlinks). Apply the most conservative default (recreate the link) rather than asking, when the SP invariant says "data preserved". **Why this matters for michi:** the cycle shipped with "git diff --short data/ = clean" and "vite dev returns 200" — both true — but the 5173 smoke returned empty data because the junction was missing. Without checking the reparse, the cycle would have committed with a hidden SP §4 violation. **Companion rule:** SP invariants that touch gitignored paths must be verified with filesystem tools, not git.

## 23. Fast-forward merge when the WT is 1 commit ahead of dev and parent is clean (atlas strip-kanban cycle, 2026-09

- **Fast-forward merge when the WT is 1 commit ahead of dev and parent is clean (atlas strip-kanban cycle, 2026-09-05).** When the WT's branch has exactly one commit on top of `dev` (the typical michi flow), `dev` has no commits not on the WT, and the parent checkout of `dev` is clean (no dirty mods blocking `checkout`), the shortest merge path is NOT a GitHub PR and NOT a `git checkout dev; git merge; git push` round-trip. It is a local ref move + push:
  ```bash
  sha=$(git -C <wt> rev-parse HEAD)                    # FULL SHA, not abbreviated
  git -C <parent> update-ref refs/heads/dev "$sha"    # moves local dev without touching working tree
  git -C <parent> push origin dev                      # fast-forward on remote
  ```
  **Why full SHA matters:** `git update-ref` rejects abbreviated refs (this session tried `06db44e06db44e` and got `fatal: not a valid SHA1`). Always pull the full 40-char SHA from `rev-parse` and pass it verbatim. **Why this beats `git checkout dev; merge; push`:** avoids stashing the parent's clean-but-untracked files (e.g. `plans/dp-saizwkm9-deadcode.md`), avoids touching the WT (which keeps serving the smoke port), and one operation on each side. **Pre-flight check:** `git fetch origin dev` BEFORE comparing refs — local `dev` can be stale and the merge calculation wrong. Recipe in order: fetch → `rev-parse origin/dev HEAD` → if WT is ahead and origin/dev == WT-base, use the `update-ref` recipe. If origin/dev has commits the WT does not, you have a real divergence, fall through to a normal merge or PR.

## 25. Worktree → dev: pull first, merge INTO the worktree, resolve there, THEN merge to dev

- **Worktree → dev: pull first, merge INTO the worktree, resolve there, THEN merge to dev** (michi 2026-09-05, atlas strip-kanban-ui-2 cycle). Reflex after worktree commit+push accepted: "merge to dev and push". Don't — dev may have moved since the worktree was cut, and conflict markers on dev are a 3am page. Recipe: (1) `git fetch origin dev` BEFORE the final merge. (2) If origin/dev is ahead of the worktree's merge-base: `git -C <wt> merge origin/dev` (resolve in the worktree, NOT on dev — the worktree has your full feature + tests + gate output; dev has stale state from other features and you'll be debugging blind). (3) Re-run gates in the worktree. (4) `git -C <parent> merge <wt-branch>` → push. Cost of skipping: a merge commit on dev with conflict markers you debug at 3am because you don't remember which feature conflicted with which. Cost of the protocol: 2 extra git commands when dev is stale, 0 when dev hasn't moved. Default to the protocol; skip only when you just verified origin/dev == local dev == worktree-merge-base.

## 26. Fecho com push + merge: fast-forward quando `origin/<ramo>` == base (portfolio-docs-audit, 2026-10-17)

- **Fecho com push + merge: fast-forward quando `origin/<ramo>` == base (portfolio-docs-audit, 2026-10-17).** `git fetch` → comparar `rev-parse origin/<ramo>` com a base; se iguais, `git checkout <ramo> && git merge --ff-only <feature> && git push origin <ramo> <feature>`. Só com "push e merge" explícito do user. **Scripts Python no Git Bash:** não passar caminhos `/tmp` (o Python do Windows não os vê); usar o scratchpad ou ler do pipe (`git ... | python -I -c`).

## 27. Python em modo texto no Windows: CRLF e `\n` escapado (dev-workflow-escalar-programas, 2026-10-18)

- **Python em modo texto no Windows: CRLF e `\n` escapado (dev-workflow-escalar-programas, 2026-10-18).** `open(p).read()` + `write()` converte um ficheiro LF em CRLF (diff total, ruído em `git diff`); usar `open(p, encoding="utf-8", newline="")` ou editar com `Edit`. Num heredoc a escrever código Python, `"\n"` chega ao ficheiro como quebra de linha real e dá `SyntaxError: unterminated string literal`: para strings com `\n` ou `\r\n` usar `Edit`. Verificar com `git diff --stat` (tamanho plausível) e `git ls-files --eol <ficheiro>` (`i/lf w/lf`).

Reincidência (sp-programa-avancar-fechar, 2026-10-18): um patch Python com `\n` dentro de `'''...'''` partiu o `.py` (string partida, 2 vezes). Para inserir `\n` literal em código, usar `Edit`, nunca um script Python gerado.

## 28. "Duplicada" num SP de inventário: ler o corpo antes de remover (dev-workflow-refactorizar-inventario, 2026-10-18)

- **"Duplicada" num SP de inventário: ler o corpo antes de remover (dev-workflow-refactorizar-inventario, 2026-10-18).** O SP dizia que `grilling` duplicava `grill-me` (ambas v1.2.0), mas `grill-me` era só um ponto de entrada que carregava `grilling`; remover à letra deixava `grill-me` sem protocolo. Antes de mover/apagar uma skill marcada como duplicada, ler o corpo das duas e fazer `Grep` pelo nome (`related_skills`, "load X"). Se uma depende da outra, não são duplicadas: perguntar uma vez (fundir / manter / literal) com a recomendação. `skill-version demote` recusa se a cópia primária difere da de referência; usar `archive` e copiar a versão primária para `inactive/`.
