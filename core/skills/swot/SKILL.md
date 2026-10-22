---
name: swot
description: Quick SWOT analysis — decision frame or optimization frame
version: 2.1.0
author: user
license: MIT
platforms:
- linux
- macos
- windows
triggers:
- swot
- swot analysis
- strengths weaknesses opportunities threats
- decision frame
- optimization analysis
- what can be improved
- leverage points
metadata:
  hermes:
    tags:
    - workflow
    - analysis
    - decision
    - optimization
    category: analysis
    related_skills:
    - brainstorm
    - five-whys
    - eisenhower-matrix
    - ooda-loop
    - michi
    - grill-me
changelog:
- '2.1.0: Encolhida; modelos de saída e exemplos movidos para references/examples.md.'
- '2.0.0: Modo de otimização (Impact/Effort, evidência, análise cruzada) fundido no /swot.'
---
# SWOT

User typed a subject after `/swot`. Two modes — pick based on the question being asked:

| Mode | Question | Output |
|---|---|---|
| **Standard** | *"Should we do this?"* — go/no-go | 2x2 + verdict, qualitative |
| **Optimization** | *"How do we make this better?"* — leverage points | Scored 2x2 + cross-analysis + ranked targets, evidence-backed |

Default to **Standard**. If the context suggests improvement ("this system is slow", "our process is broken"), use **Optimization**.

## Mode 1 — Standard (Decision Frame)

1. Frame the subject: one sentence — what is being decided, in what context.
2. Populate each quadrant with 3-5 specific items; "good team" is not SWOT, "team shipped 2 prior X with this stack" is.
3. S+W are internal, O+T external. The interesting cells are SO (strength grabs opportunity) and WT (weakness meets threat = what kills you).
4. Verdict: 1-2 sentences naming the dominant constraint and the most leveraged move.

Output: `# SWOT: <subject>`, the 2x2 table, then `**SO (do):**`, `**WT (avoid):**`, `**Verdict:**`. Stop at 4 quadrants: the user wants a decision frame, not a treatise.

## Mode 2 — Optimization (Improvement Frame)

1. **Scope** — one sentence, specific ("the auth flow in `packages/server/auth/`", not "the backend").
2. **Investigate, don't guess** — `Read` code/config/docs, `Grep`/`Glob` for TODOs, FIXMEs and error patterns, check logs, metrics and git history. Every item needs at least one piece of evidence (file, log or metric); no "feels slow".
3. **Populate** 3-5 items per quadrant:
   - **S** — what works, is optimal, can be reused.
   - **W** — where energy is wasted; what is broken, slow or missing.
   - **O** — what the right investment or available tool would improve.
   - **T** — what is fragile, deprecated or could derail progress.
4. **Score** each item: Impact (1-5) and Effort (1 = trivial, 5 = major refactor). Priority = Impact / Effort.
5. **Cross-analysis**:
   - **SO (Attack):** strengths seize opportunities.
   - **WO (Fix):** the weakness that blocks the biggest opportunity.
   - **ST (Shield):** strengths mitigate threats.
   - **WT (Survive):** weakness + threat = fix now.
6. **Prioritize** the cross-cells by priority score; the top 2 are the targets.
7. **Verdict** — *"The biggest leverage point is X because Y (score Z/5)."* Next step: feed the top 2 into `eisenhower-matrix` or `/dp`.

Output: `# SWOT Optimization: <scope>`, the scored 2x2 (`S1: <item> (Impact: 4, Effort: 2)`), `## Cross-Analysis` (4 cells), `## Prioritized Targets`, `**Verdict:**`.

### Verification gate

Complete only when all hold: every item has evidence and both scores; all 4 cross cells have a concrete finding; the verdict states the leverage point with a score; at least one target maps to a concrete action.

Full output templates and worked examples for both modes: `references/examples.md`.

## When NOT to use
- Raw ideas needed first → `brainstorm`.
- Broken system needing root cause → `five-whys` (or `systematic-debugging`).
- Environment changing faster than the analysis → `ooda-loop`.

## Integration
- After SWOT, `eisenhower-matrix` orders the actions; results feed `/dp` or `/michi`.
- Usable inside `grill-me` (Phase 1) when the project involves a decision or improvement.
