---
name: dp
description: "Use when starting any Deep-Planning (DP) session or COMPLEX task requiring structured planning before execution. Produces _PLAN_*.md with phases, risks, verification criteria, and time-boxed deliverables."
version: 2.1.0
---
# Deep Planning (DP) — Skill

> Adapted from obra/superpowers for pi coding agent + the agent.

## Overview

DP is the **structured planning phase** that sits between Deep-Research (DR) and Deep-Acting (DA). No code is written here — only decisions, phases, risks, and verification criteria. The plan is a contract between research and execution.

**Core principle:** A plan without verification criteria is a wish, not a plan.

## When to Use

| Scenario | Apply? |
|----------|--------|
| COMPLEX task (multi-step, code, debugging, architecture) | **MANDATORY** |
| User says "plan this first" | **MANDATORY** |
| User says "just do it" | Skip — document bypass in session note |
| STANDARD task with known solution | Recommended — use lightweight plan |
| TRIVIAL one-liner | Never — execute directly |

## Pre-Condition: DR Completion Gate

Before DP can begin, verify the DR (Deep-Research) handoff:

1. **Research Brief exists** at `knowledge/projects/<project>/research/YYYY-MM-DD-<topic>-brief.md`
2. **Brief is not empty** — all sections populated (or gaps documented)
3. **Confidence Assessment** reviewed — low-confidence sections flagged as risks
4. **Scope Gate decision** recorded (Full/Delta/Skipped)

**If DR is missing:** Run `deep-research` skill first. Do not skip.
**Exception:** Context fully known (same task continued within minutes, trivial task) → document skip reason, proceed.

## Workflow

```
Task received
  → TRIVIAL? → Execute directly (document bypass)
  → COMPLEX?
      → Pre-Condition: DR Research Brief validated (gate above)
      → Phase 1: Analyze (read Brief, restate, identify constraints)
      → Phase 2: Plan (write plan with phases, risks, verification)
      → Quality Gate: self-review before presenting
      → Phase 3: Present & Iterate (max 2 rounds)
      → User approves → Execute via DA
      → User rejects → Return to Phase 1 or Abort
```

---

## Phase 0 — Scope Gate (Pre-DP)

Before investing in planning, confirm the task warrants it:

| Decision | Condition | Action |
|----------|-----------|--------|
| **Skip entirely** | TRIVIAL, context known, one-liner | Execute directly, log bypass |
| **Delta-only** | Same task <24h, known context | Lightweight plan (2-3 phases) |
| **Full DP** | COMPLEX, new context, multi-system | Full 7-phase plan |

Record Scope Gate decision in plan's `## Executive Summary` section.

---

## Phase 1 — Analyze (10 min max)

Read the Research Brief. Do NOT re-research.

1. **Restate problem** in one sentence.
2. **Identify constraints** — technical, temporal, resource.
3. **Identify actors** — what/who is affected.
4. **Identify dependencies** — what must exist before this.
5. **Cross-reference Brief's low-confidence sections** → convert to risks.
6. **Supplement Brief** only if gaps found — do not start from scratch.
7. **Check MISTAKE_LOG** for patterns matching this domain.

**Time-box:** 10 minutes. If not done, proceed with what you have and flag time pressure as a risk.

---

## Phase 2 — Write Plan (15 min max)

Write to `knowledge/projects/<project>/plans/_draft/_PLAN_YYYYMMDD_HHMMSS.md`.
Include `status: DRAFT` in YAML frontmatter.

### Required Sections

```markdown
---
status: DRAFT
project: <name>
scope-gate: Full/Delta/Skipped
research-brief: <path-to-brief>
created: YYYY-MM-DDTHH:MM:SS
---

# Plan: <goal>

## Executive Summary
{Scope Gate decision, 2-3 sentences on approach}

## Problem Statement
{Restated from Phase 1}

## Context & Analysis
<Reference Research Brief. Key constraints, actors, dependencies>

## Assumptions
- {Explicit assumptions, load-bearing ones flagged ⚠️}

## Phases
### 1. <phase name>
- **What:** 1-2 lines
- **Scope:** paths or systems touched
- **Done when:** observable/testable criterion
- **Time-box:** X min max
- **Parallel:** [list independent phases that can run concurrently]

## Risks
- {Top 3 risks, each with mitigation and trigger condition}

## Out of Scope
- {Explicit exclusion list — lazy scope kills plans}

## Verification Criteria
- {Per-phase acceptance tests}

## Rollback Plan
- {How to undo each phase if needed}

## Open Questions
- {Anything unresolved — must be addressed or accepted as risk}
```

### Plan Quality Rules
- **3-7 phases** (minimum 2, maximum 7 — if more, split or simplify)
- **Every phase** has a "Done when" test/observable
- **No code** in the plan body — implementation lives in `/da`
- **Every risk** has a mitigation AND a trigger condition
- **Time-box** on every phase
- **Parallel flags** on phases that can run concurrently

---

## Phase 3 — Quality Gate (Self-Review, 3 min)

Before presenting, validate the plan against this checklist:

- [ ] Research Brief referenced (path correct, file exists)
- [ ] All phases have "Done when" criterion
- [ ] All phases have time-box
- [ ] Risks have mitigation + trigger
- [ ] Out of Scope is explicit (not implied)
- [ ] Assumptions are stated, load-bearing ones flagged
- [ ] Verification Criteria exist per phase
- [ ] Rollback Plan exists
- [ ] No code in plan body
- [ ] Scope Gate decision recorded
- [ ] Open Questions listed (or "None — all resolved")
- [ ] Parallel phases flagged

**If any checkbox fails → fix before presenting. No exceptions.**

---

## Phase 4 — Present & Iterate (Max 2 rounds)

1. **Present** concise summary (5 bullets max): goal, phases, key risks, out-of-scope, time estimate.
2. **User adjusts** → iterate. **Max 2 rounds.**
3. **Round 3 rejection** → Abort. Log in session note: "Plan rejected after 2 iterations."

### Iteration Rules
- Round 1: User adjusts scope, phases, or risks → update plan → re-present
- Round 2: Final adjustments only → present for approval
- Round 3: **Abort** — plan is not converging. Escalate to user.

### Approval → DA Handoff
When user approves:
1. Update plan frontmatter: `status: APPROVED`
2. Move to `knowledge/projects/<project>/plans/_approved/`
3. Record `approved: YYYY-MM-DDTHH:MM:SS`
4. Execute via **Deep Acting (DA)** skill

### Rejection → Abort
When user rejects after 2 rounds:
1. Update plan: `status: REJECTED`
2. Log in session note with reason
3. **Do not execute.** Report findings to user.
4. Optional: suggest `deep-research` revisit if fundamental assumptions were wrong

---

## Time Budget Summary

| Phase | Max Time | Override |
|-------|----------|----------|
| Phase 1 — Analyze | 10 min | `--deep` flag |
| Phase 2 — Write Plan | 15 min | `--deep` flag |
| Phase 3 — Quality Gate | 3 min | Fixed |
| Phase 4 — Present & Iterate | 5 min per round | Max 2 rounds |
| **Total** | **~45 min** | `--deep` adds +15 min per phase |

---

## Abort Criteria

Stop planning and escalate to user when:
- Task scope is fundamentally unclear after 2 rounds of clarification
- Research Brief has critical gaps that block planning
- User rejects plan 2 times
- Estimated effort exceeds available time by >50%
- Dependencies are unknown and cannot be resolved

---

## Failure Modes & Anti-Patterns

| Anti-Pattern | Fix |
|-------------|-----|
| Planning without DR Brief | Run `deep-research` first |
| No "Done when" per phase | Add verification criterion |
| Too many phases (>7) | Consolidate or split into sub-plans |
| Code in plan body | Move to DA; plan is decisions only |
| Infinite iteration | Max 2 rounds, then abort |
| Ignoring low-confidence Brief sections | Flag as risks |
| Skipping Quality Gate | Mandatory self-review before presenting |
| Hardcoding paths | Resolve dynamically via `sb_resolve` |
| No time-boxes | Add per-phase time limit |
| Assuming parallelism without checking | Only flag truly independent phases |

---

## Observability

- [ ] Research Brief exists and is validated (Pre-Condition)
- [ ] Scope Gate decision recorded
- [ ] Plan document exists in `knowledge/projects/<proj>/plans/_draft/`
- [ ] Plan references Research Brief file path
- [ ] Quality Gate checklist passed (all items)
- [ ] Status is APPROVED before execution
- [ ] Iteration count ≤2
- [ ] MISTAKE_LOG checked via DR
- [ ] Time-budgets present on every phase
- [ ] Parallel phases flagged

---

## Quick Reference

| Aspect | Rule |
|--------|------|
| **Pre-Condition** | DR Research Brief validated (or documented skip) |
| **When** | COMPLEX or user requests |
| **Phases** | Scope Gate → Analyze → Write → Quality Gate → Present (max 2 rounds) |
| **Plan location** | `knowledge/projects/<project>/plans/_draft/_PLAN_*.md` |
| **Approved location** | `knowledge/projects/<project>/plans/_approved/` |
| **Code location** | `~\Documents\projetcs\<project>\` |
| **Approval** | Required (max 2 iteration rounds) |
| **Execution** | Deep Acting (DA) skill |
| **Time-box** | ~45 min total (per phase: Analyze 10min, Plan 15min, Quality 3min, Present 5min) |
| **Commit plans** | Never |
| **Abort** | After 2 rejections, critical gaps, or scope unclear |

---

#dp #deep-planning #architecture #planning #quality-gate #time-boxed

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
