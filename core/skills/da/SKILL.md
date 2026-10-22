---
name: da
description: "Use when executing an approved Deep-Planning (DP) plan or any COMPLEX standalone task. Provides per-step verification, failure escalation with time-boxing, checkpoint/resume, and structured rollback."
version: 2.1.0
---
# Deep Acting (DA) — Skill

> Adapted from obra/superpowers for pi coding agent + the agent.

## Overview

DA is the **execution phase** that follows an approved DP plan. It runs phase-by-phase with verification at each step, structured escalation on failure, checkpoint persistence for resume, and automatic rollback triggers.

**Core principle:** Evidence before assertion. No "done" without verification. Every step is auditable.

## When to Use

| Scenario | Apply? |
|----------|--------|
| Executing approved DP plan | **MANDATORY** |
| COMPLEX standalone task | **MANDATORY** |
| STANDARD multi-step | Recommended |
| TRIVIAL one-liner | Never — execute directly |

## Pre-Execution Checklist

Before starting the execution loop, verify:

- [ ] Plan document exists and is `status: APPROVED`
- [ ] All files/systems identified in plan are accessible
- [ ] Dependencies available (from plan's assumptions)
- [ ] MISTAKE_LOG.md checked — prevention steps applied
- [ ] Rollback plan reviewed and backup created if needed
- [ ] **Checkpoint saved** (see Checkpoint/Resume below)

**If any checkbox fails → resolve before starting execution loop.**

---

## Checkpoint/Resume System

DA persists progress after every completed step. This enables resume after interruption.

### Checkpoint File

Create/update `knowledge/projects/<project>/plans/_checkpoints/<plan-name>_checkpoint.md`:

```markdown
---
plan: <plan-file-path>
status: IN_PROGRESS
started: YYYY-MM-DDTHH:MM:SS
last-update: YYYY-MM-DDTHH:MM:SS
current-phase: N
current-step: "step description"
completed-steps:
  - step: "1.1"
    status: OK
    evidence: <brief evidence>
  - step: "1.2"
    status: OK
    evidence: <brief evidence>
failed-steps: []
aborted: false
---

# Checkpoint: <plan-name>

## Completed
- [Step N.M] <description> — <evidence>

## Failed
- None

## Blockers
- None

## Next Step
- [Step N.M+1] <description>
```

### Resume Protocol

If DA is interrupted (crash, timeout, manual stop):
1. Read checkpoint file
2. Identify `current-phase` and `current-step`
3. Verify state of completed steps (read back files)
4. Resume from last verified step
5. **Never re-execute a step marked [OK]** — verify instead

---

## Execution Loop (per step)

```
Announce → Select Tool → Execute → Checkpoint
  → OK: Check off → Verify → Report → Next step
  → FAIL: Escalation (see below)
```

**Report format:** `[OK] Step N.M — <description> | Evidence: <RC/output>`

### Progress Cadence

| Plan Length | Report Cadence |
|-------------|---------------|
| ≤5 steps | Report each step |
| 6-15 steps | Report every 3 steps + at phase boundaries |
| >15 steps | Report every 5 steps + at phase boundaries + every 5 min |

**Always report at phase boundaries.**

---

## Failure Escalation

| Level | Trigger | Action | Time-box |
|-------|---------|--------|----------|
| **L1** | Tool fails | Retry same action | 2 retries max |
| **L2** | Retry fails | Debug | 3 min |
| **L3** | Debug unresolved | Switch tool/approach | 3 min |
| **L4** | All approaches failed | Ask user (skip/change/abort) | — |
| **L5** | Multi-step blocker | Update plan to BLOCKED + mistake log | — |

**Time-box is strict.** If the time-box expires at any level → escalate to next level automatically.

### Automatic Escalation Rules

- L1 exhausted (2 retries) → auto L2
- L2 exhausted (3 min) → auto L3
- L3 exhausted (3 min) → auto L4
- L4: User decides within 2 min → if no response, plan step → BLOCKED

---

## Phase Integration Verification

After completing all steps in a phase, before starting the next:

1. **Integration check** — do the completed phase outputs integrate correctly?
2. **Cross-reference verification** — do files from previous phases still reference correctly?
3. **Build/test** — run the smallest integration test that covers multiple phases

**This is NOT optional.** Skipping integration verification is the #1 cause of late-stage failures.

---

## Verification Rules

**Per step:**
- Read back modified files
- Check encoding (UTF-8, no BOM on config files)
- Check side effects (new files, modified dependencies)
- Run smallest relevant test/build

**Per phase:**
- Integration check (see above)
- Phase-specific test run
- Evidence recorded in checkpoint

**Final test report:**
```markdown
## Test Report — <plan-name>
- [OK/FAIL] Build: <command> → RC <code>
- [OK/FAIL] Tests: <N> run, <N> failures
- [OK/FAIL] Lint: <command> → RC <code>
- [OK/FAIL] Manual: <check description>
- [OK/FAIL] Integration: <phase integration check>
```

---

## Context Refresh Protocol

Long-running executions (>10 steps or >15 min) must refresh context:

**Trigger:**
- Every 10 completed steps
- Every 15 minutes elapsed
- Before starting a new phase
- After any L2+ escalation

**Action:**
1. Re-read plan document (disk, not context snapshot)
2. Re-read Research Brief (if referenced)
3. Check `git status` for unexpected changes
4. Re-read any files modified by previous steps

**Rationale:** A skill body loaded into context is a snapshot, not live state. The on-disk file may have been edited by a parallel turn. One `read` is cheaper than three failed patches.

---

## Automatic Rollback Triggers

Rollback is triggered automatically when:

| Condition | Rollback Scope | Action |
|-----------|---------------|--------|
| Build fails after 2+ steps | All changes in current phase | `git checkout -- .` for modified files |
| Test failures >50% | All changes since last checkpoint | Revert to last checkpoint state |
| Critical error (data loss, corruption) | All changes in this execution | Full rollback + mistake log |
| User requests abort | All changes since plan start | Rollback per plan's Rollback Plan |

**Rollback rules:**
- New file → Delete
- Modified file → `git checkout -- <file>` (must have git backup)
- Multiple files → `git checkout -- .`
- **Document rollback plan BEFORE making changes** (it's in the plan)

**Rollback verification:** After rollback, run `git status --short` to confirm clean working tree.

---

## Parallel Step Execution

Independent steps within a phase can run concurrently:

**Condition for parallelism:**
- Steps do not modify the same files
- Steps do not depend on each other's output
- Steps do not share state

**Execution:**
- Independent steps → run in parallel (subagents or parallel tool calls)
- Dependent steps → sequential, in plan order
- **Verify parallel results** before marking phase complete

**Flag in plan:** `[PARALLEL]` on phases with independent steps.

---

## Post-Execution — LFS (MANDATORY)

1. **Session Note** — `knowledge/projects/<proj>/sessions/YYYY-MM-DD.md`
2. **Mistakes** — Log errors with YAML schema
3. **Daily Note** — Append summary in `knowledge/periodic/daily/YYYY/MM/W{1-5}/YYYY-MM-DD.md`
4. **Pattern Scan** — Recurrent pattern? → update MISTAKE_LOG.md
5. **Checkpoint cleanup** — Delete checkpoint file after successful completion
6. **Plan status** — Update to `status: DONE`, move to `_done/`

---

## Done Criteria

A DA execution is **done** when ALL of:
- [ ] Every phase has `[OK]` for every step
- [ ] Final test report generated (all sections passed)
- [ ] Integration verification passed
- [ ] Checkpoint file deleted (or marked `status: DONE`)
- [ ] Plan status updated to `DONE`
- [ ] LFS executed (session note, mistakes, daily note)
- [ ] No open blockers

**If any of these fail → execution is NOT done.** Report what's missing.

---

## Failure Modes & Anti-Patterns

| Anti-Pattern | Fix |
|-------------|-----|
| "Done" without evidence | Run test/build, report RC/output |
| Skipping integration verification | Phase boundary check is mandatory |
| Blind retry after 2 failures | Escalate: L1→L2→L3→L4 |
| Ignoring checkpoint | Always save checkpoint after each step |
| No context refresh | Refresh every 10 steps / 15 min |
| Papering over blockers | Surface early, escalate L4 |
| Skipping rollback plan | Document BEFORE changes |
| Executing without APPROVED plan | Check plan status first |
| Re-executing [OK] steps on resume | Verify, don't re-run |
| Running dependent steps in parallel | Check file/state dependencies |

---

## Observability

- [ ] Pre-Execution Checklist passed
- [ ] Checkpoint created before execution
- [ ] Each step has `[OK]` or `[!]` reported
- [ ] Progress cadence followed
- [ ] Context refreshed at triggers
- [ ] Integration verification at each phase boundary
- [ ] Test report generated with all sections
- [ ] No file modified without verification (read back)
- [ ] Automatic rollback triggers evaluated
- [ ] Parallel steps verified independently
- [ ] LFS executed
- [ ] Session Close executed
- [ ] Checkpoint cleaned up (or marked DONE)

---

## Quick Reference

| Aspect | Rule |
|--------|------|
| **Pre-Condition** | Plan APPROVED, checklist passed, checkpoint created |
| **Loop** | Announce → Select → Execute → Checkpoint → Verify → Report |
| **Time-box** | L1: 2 retries, L2: 3 min, L3: 3 min, L4: 2 min user response |
| **Context Refresh** | Every 10 steps / 15 min / phase boundary |
| **Parallel** | Only independent steps (no shared files/state) |
| **Checkpoint** | After every step; resume from last verified step |
| **Rollback** | Automatic on build fail, test fail >50%, critical error |
| **Integration** | Mandatory at every phase boundary |
| **Done** | All phases OK, test report passed, LFS done, checkpoint cleaned |
| **Code path** | `~\Documents\projetcs\<project>\` |
| **Cleanup** | Update plan to DONE, checkpoint deleted, LFS executed |

---

#da #deep-acting #execution #workflow #verification #checkpoint #rollback

## Adaptação Claude Code (the agent)

Ferramentas Pi → Claude Code. Sem sub-agentes (sequencial; ver CLAUDE.md).

| Pi | Claude Code |
|----|-------------|
| `sb_search` | `Grep` (conteúdo) / `Glob` (nomes) |
| `sb_read` | `Read` (usar `offset`/`limit`) |
| `sb_list` | `Glob` (ordenar por data) |
| `sb_resolve` | `Glob` por `**/<nome>.md` (wikilink → caminho) |
| `bash` + `find`/`grep` | Proibido; usar `Glob`/`Grep` |
| `subagents` / paralelo | Chamadas de ferramentas paralelas na mesma resposta; nunca `Agent` salvo pedido do user |
| `sync_daily_notes` | Ler/editar a daily note à mão |
