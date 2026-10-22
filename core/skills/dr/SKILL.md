---
name: dr
description: 'Use when starting any Deep-Planning (DP) session or COMPLEX task requiring structured context gathering — performs systematic research across vault, codebase, and mistake logs before planning begins. Trigger: start of DP, ''research this first'', ''gather context for'', or any multi-step task where context is incomplete.'
version: 2.0.0
---
# Deep-Research (DR) — Skill

> Structured research phase that feeds into Deep-Planning. Evidence before assumptions.

## Overview

DR is **Phase 0** — runs before DP's "Analyze" to gather all context systematically. No planning without evidence.

**Core principle:** Research before analysis. Analysis before design. Design before code.

## When to Use

| Scenario | Apply? |
|----------|--------|
| Start of Deep-Planning (DP) | **MANDATORY** |
| COMPLEX task with unknown context | **MANDATORY** |
| User says "research this first" | **MANDATORY** |
| Multi-step task where context is incomplete | Recommended |
| TRIVIAL task or context already known | Skip |
| Quick question / one-liner | Never |

## DR vs Session Start vs Brainstorming

| Skill | Scope | Direction | When |
|-------|-------|-----------|------|
| **Session Start** | Session-wide (inbox, mistakes, daily note) | Horizontal | Every session |
| **Deep-Research** | Project/task-specific (vault + codebase + patterns) | Vertical deep-dive | Start of DP or COMPLEX tasks |
| **Brainstorming** | Design exploration (approaches, trade-offs) | Creative | After DR, before writing-plans |

Session Start sets the **session** context. DR sets the **project** context.

## The Iron Law

```
NO PLANNING WITHOUT RESEARCH FIRST
```

If Research Brief isn't complete, DP's Analyze cannot start.

## Scope Gate (Phase 0.5)

Before launching full DR, verify the task actually warrants deep research. This prevents over-researching simple tasks.

**Decision tree:**
1. Is the task TRIVIAL or context already known? → **Skip DR entirely**
2. Is it a quick question answerable with one `sb_search`? → **Run sb_search only**, skip formal DR
3. Does the task span multiple subsystems or have unknown dependencies? → **Full DR**
4. Uncertain? → Run Phase 1 only; if target is clear and narrow, scale down to delta-only

**Output:** Scope Gate decision recorded in Research Brief under `## Executive Summary` as `Scope Gate: Full/Delta/Skipped`.

---

## Research Phases

Execute in order, with parallelism where phases are independent. Each phase: input → tools → output → verify.

### Execution Strategy

- **Sequential:** Phase 1 → Phase 2 (Phase 2 depends on target clarity from Phase 1)
- **Parallel:** Phases 2–5 are independent of each other; run simultaneously when possible
- **Merge:** Phase 6 consolidates all outputs

```
Phase 1 ──→ Phase 2 ─┐
         ├──→ Phase 3 ─┤
         ├──→ Phase 4 ─┤──→ Phase 6 (Compile)
         └──→ Phase 5 ─┘
```

### Time Budget

| Phase | Max Time | Notes |
|-------|----------|-------|
| Phase 1 — Identify Target | 2 min | Fast-path check |
| Phase 2 — Vault Research | 5 min | Use sb tools exclusively |
| Phase 3 — Codebase Research | 5 min | Use bash + git |
| Phase 4 — Mistake Pattern | 3 min | Search MISTAKE_LOG |
| Phase 5 — Temporal Context | 3 min | Sync + read notes |
| Phase 6 — Compile Brief | 3 min | Write file |
| **Total** | **~21 min** | Override with `/dr <topic> --deep` for extended |

---

### Phase 1 — Identify Target

Identify project, task scope, key entities. **Fast-path:** worked on this project in last 24h? → delta-only (new commits, new files, updated notes). Output: target statement.

**Tools:**
- `sb_resolve` — resolve project wikilink → derive code path
- `sb_search` — verify project exists in vault
- `project_detect` — if cwd matches a known project

**Output:** Target statement (project name, scope, key entities).

**Fast-Path Check:**
1. `sb_list` recent sessions for this project
2. If last session within 24h → mark Fast-Path: **Delta-Only**
3. If no recent session → mark Fast-Path: **Full**

---

### Phase 2 — Vault Research

Read project MOC. Search related content. Check link health. Gather vault stats.

**Tools:**
- `sb_read` — read project MOC (`knowledge/projects/<project>/MOC.md`)
- `sb_search` — related content by keyword and tags
- `sb_list` — recent sessions in project directory
- `sb_resolve` — validate wikilinks in MOC
- `maintenance_link_audit` — if broken links detected
- `dashboard_status` — vault stats (file count, size, active skills)

**Pre-requisite:** Ensure vault is synced. Run `sync_daily_notes(dryRun=true)` first — if significant changes pending, run `sync_daily_notes()` before reading notes.

**Output:**
- MOC path and status (found/new/missing)
- Related docs list
- Link health status
- Vault stats snapshot

---

### Phase 3 — Codebase Research

Map structure, search patterns, check recent commits, find TODOs.

**Tools:**
- `bash` — `ls`, `rg` (ripgrep), `git log`
- `win_git` — for git operations on Windows repos (path resolution fallback)
- `git_status` — current working tree state

**Path Resolution:**
- Resolve code path dynamically via `sb_resolve` from project MOC
- **Never hardcode** — derive from project configuration
- Fallback: `sb_search` for project directory reference

**Checks:**
1. **Structure:** `ls` key directories (`src/`, `lib/`, `config/`, `docs/`)
2. **Recent commits:** `git log --oneline -10`
3. **Open TODOs:** `rg "TODO|FIXME|HACK|XXX"`
4. **Branch state:** `git status --short`

**Error Handling:**
- If git unavailable → mark as "not checked", note in Research Gaps
- If project path not found → mark as "path unresolved", skip to Phase 6

**Output:** Codebase structure, recent changes, open TODOs.

---

### Phase 4 — Mistake Pattern Check

Search MISTAKE_LOG for patterns matching this project's domain, tech stack, and task type.

**Tools:**
- `sb_search` — search for `MISTAKE_LOG` in project scope and `knowledge/infra/`
- `bash` — fallback `find` for MISTAKE_LOG files if sb_search misses

**Filter Strategy:**
1. Match by project name (3+ char substring)
2. Match by tech stack keywords (e.g., "Next.js", "Supabase", "Python")
3. Match by task type keywords (e.g., "deployment", "RLS", "migration")

**Output:** Matching patterns with prevention steps, or `_None relevant_`.

**Error Handling:**
- If MISTAKE_LOG not found → record `_MISTAKE_LOG not found_` in Research Gaps
- Never let this phase block the entire DR

---

### Phase 5 — Temporal Context

Read today's + yesterday's daily notes. Check last 3 days of session notes. Extract: what's done, in progress, blocked.

**Pre-requisite:** Run `sync_daily_notes(dryRun=true)` first. If dryRun shows pending changes, execute `sync_daily_notes()` to ensure freshness.

**Tools:**
- `sync_daily_notes` (dryRun then actual if needed)
- `sync_sessions` — refresh session note timestamps
- `sb_read` — daily notes (`knowledge/YYYY-MM-DD.md`), session notes
- `sb_list` — last 3 days of session files

**Extract:**
- Today's work items
- Yesterday's completed/in-progress
- Blockers and pending decisions
- Any flags from session notes (wIP, abandoned, escalated)

**Output:** Temporal snapshot with dates and status.

---

### Phase 6 — Compile Research Brief

Write findings to `knowledge/projects/<project>/research/YYYY-MM-DD-<topic>-brief.md`. Use template below. All sections populated.

**Merge Strategy:** Combine outputs from parallel Phases 2–5. If any phase was skipped or errored, fill its section with the recorded gap/reason.

---

## Research Brief Template

```markdown
# Research Brief — {Topic}

> **Date:** YYYY-MM-DD
> **Project:** {project}
> **Scope:** {scope}
> **Fast-Path Applied:** {Full/Delta/Skipped}
> **Scope Gate:** {Full/Delta/Skipped}
> **Duration:** {total minutes}

## Executive Summary
{2-3 sentences: what was researched, key findings, overall confidence}

## Vault Findings
- **MOC:** {path} — {status: found/new/missing}
- **Related Docs:** {list}
- **Link Health:** {healthy / N broken links}
- **Vault Stats:** {files, size, active skills from Dashboard}

## Codebase State
- **Location:** {resolved absolute path}
- **Structure:** {key dirs}
- **Recent Changes:** {last N commits or "no git"}
- **Open TODOs:** {count + key items}

## Mistake Patterns
- **[{category}]** {pattern} → Prevention: {step}
- _None relevant_ (if applicable)
- _MISTAKE_LOG not found_ (if applicable)

## Temporal Context
- **Today:** {what's being worked on}
- **Yesterday:** {recent work}
- **Blockers:** {any}

## Open Questions
1. {question 1}
2. {question 2}

## Research Gaps
- {what couldn't be determined}
- {phases that errored or were skipped, with reason}

## Confidence Assessment
| Section | Confidence | Basis |
|---------|------------|-------|
| Vault | high/medium/low | {reason: ≥3 sources / 1-2 sources / no sources} |
| Codebase | high/medium/low | {reason} |
| Mistakes | high/medium/low | {reason} |
| Temporal | high/medium/low | {reason} |
| **Overall** | **high/medium/low** | |

## Tool Audit
| Phase | Tools Used | Status |
|-------|-----------|--------|
| Phase 2 | sb_read, sb_search, ... | ✓/⚠/✗ |
| Phase 3 | bash, git, ... | ✓/⚠/✗ |
| Phase 4 | sb_search, ... | ✓/⚠/✗ |
| Phase 5 | sync_daily_notes, sb_read, ... | ✓/⚠/✗ |
```

### Confidence Scoring Rubric

| Score | Criteria |
|-------|----------|
| **High** | ≥3 independent sources confirm; or primary source directly matches |
| **Medium** | 1–2 sources; or source is authoritative but singular |
| **Low** | No source found; or evidence contradicts the claim; or phase errored |

---

## External Integrations

| Integration | When | How |
|-------------|------|-----|
| `grounded-citations` | Phase 2 needs web-sourced claims | Invoke skill for verifiable citations |
| `link-audit` | Phase 2 finds broken wikilinks | Auto-invoke after `sb_resolve` detects broken links |
| `sb-sync` | Phase 5 pre-requisite | Always run `sync_daily_notes` before reading temporal notes |
| `project-setup` | Phase 1 finds project missing from vault | Flag as "project not initialized" — suggest `project-setup` |

---

## DR → DP Handoff

1. Research Brief file is saved.
2. DP's "Analyze" step **reads the Brief file** — does NOT re-research.
3. Plan document references Brief: `> Research: knowledge/projects/<project>/research/YYYY-MM-DD-<topic>-brief.md`.
4. Low-confidence sections in Brief → flagged as risks in plan.
5. **Phase 0.5 Scope Gate** → DP adjusts plan depth based on whether DR was Full, Delta, or Skipped.
6. **Research Gaps** → DP must address or explicitly accept each gap as a risk.

---

## Error Handling

| Failure | Action |
|---------|--------|
| Phase 1 fails | Report failure; skip DR; escalate to user |
| Phase 2 fails (Vault) | Continue with Phases 3–5; mark Vault as "unverified" in Research Gaps |
| Phase 3 fails (Codebase) | Continue; mark Codebase as "not checked"; note in Gaps |
| Phase 4 fails (Mistakes) | Continue; record `_MISTAKE_LOG not found_` in Gaps |
| Phase 5 fails (Temporal) | Continue; note "temporal context unavailable" |
| Phase 6 fails (Write) | Output Brief to terminal instead; notify user |

**Rule: Never abort entire DR for a single phase failure. Record the gap and continue.**

---

## Quick Reference

| Aspect | Rule |
|--------|------|
| When | Start of DP or COMPLEX task |
| Phases | 7 (Scope Gate → Identify → Vault → Codebase → Mistakes → Temporal → Compile) |
| Output | Research Brief file |
| Brief location | `knowledge/projects/<project>/research/` |
| Fast-path | Last 24h on same project → delta-only |
| Parallel | Phases 2–5 run concurrently |
| Time Budget | ~21 min (override with `--deep`) |
| Integration | DP reads Brief; doesn't re-research |
| Skip when | TRIVIAL, context known, quick task |
| Version | 2.0.0 |

---

## Red Flags

- Skipping phases to "save time" — shallow research = bad plans
- Confirmation bias — only searching for what supports your assumption
- Researching without writing the Brief — if it's not documented, it didn't happen
- Ignoring low-confidence sections — they're risks, not noise
- Re-researching in DP what DR already covered — read the Brief
- Hardcoding paths — always resolve dynamically via `sb_resolve`
- Skipping Scope Gate — over-researching trivial tasks wastes context
- Running Phases 2–5 sequentially when they're independent — parallelize

## Observability

- [ ] Scope Gate decision documented
- [ ] Research Brief file exists with all sections
- [ ] Fast-path decision documented
- [ ] MISTAKE_LOG checked (patterns listed or "not found")
- [ ] Temporal notes synced before reading
- [ ] Brief file path referenced in DP plan
- [ ] No phase skipped without justification
- [ ] Tool Audit table complete
- [ ] Confidence Assessment has objective basis for each rating
- [ ] Research Gaps section populated with any failures

---
#dr #deep-research #skill #phase-0 #planning #research v2

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
