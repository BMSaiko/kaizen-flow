# SWOT — modelos de saída e exemplos

Movido de `SKILL.md` (encolher skills, 2026-10-18).

### Output format

```
# SWOT Optimization: <scope>

| Strengths | Weaknesses |
|---|---|
| S1: <item> (Impact: 4, Effort: 2) | W1: <item> (Impact: 3, Effort: 4) |
| S2: <item> (Impact: 5, Effort: 1) | W2: <item> (Impact: 2, Effort: 3) |
| ... | ... |
| **Opportunities** | **Threats** |
| O1: <item> (Impact: 4, Effort: 3) | T1: <item> (Impact: 3, Effort: 2) |
| O2: <item> (Impact: 3, Effort: 1) | T2: <item> (Impact: 4, Effort: 4) |
| ... | ... |

## Cross-Analysis
**SO (Attack):** <highest priority combo — how to multiply effort>
**WO (Fix):** <weakness that blocks the biggest opportunity — fix first>
**ST (Shield):** <strength that protects against key threat>
**WT (Survive):** <danger zone — what must be fixed now>

## Prioritized Targets (by priority score = Impact/Effort)
1. <target> — score X/5 (Impact: Y, Effort: Z) — why this is #1
2. <target> — score X/5 — why this is #2

**Verdict:** The biggest leverage point is <X> because <Y> (score <Z>/5).
**Next step:** Feed top 2 targets into `eisenhower-matrix` or `/dp` for execution planning.
```

### Execution checklist

```
[ ] Scope defined with specific path/domain?
[ ] Each quadrant has 3-5 items?
[ ] Each item has at least one piece of evidence?
[ ] Each item scored on Impact (1-5) and Effort (1-5)?
[ ] All 4 cross-analysis cells populated?
[ ] Top 2 targets ranked by priority score?
[ ] Verdict states the leverage point with a score?
```

### Verification gate

Before declaring the SWOT complete, pass ALL of these:

- [ ] **Evidence check**: Every quadrant item can be traced to at least one file, log, or metric
- [ ] **Scoring check**: Impact and Effort scores are present for every item
- [ ] **Cross-analysis**: All 4 cells (SO, WO, ST, WT) have at least one concrete finding
- [ ] **Actionable**: At least one target maps to a concrete action
- [ ] **Not just opinion**: No item in the output is purely "I feel" or "I think" — all are evidence-based

---

## Examples

### Standard example

**Subject:** "Should we migrate from PostgreSQL 14 to 16?"

```
| Strengths | Weaknesses |
|---|---|
| New version has parallel query support | Migration requires 2 weeks of downtime |
| Our team has PG 16 experience | Existing extension `pg_cron` not yet supported |

| Opportunities | Threats |
|---|---|
| Parallel queries could cut report times by 40% | Extension ecosystem needs validation |
| Better JSONB performance for our use case | Risk of data loss during migration |

**SO (do):** Migrate to leverage parallel query gains.
**WT (avoid):** Extension compatibility must be validated before any migration.
**Verdict:** Migrate, but only after validating `pg_cron` replacement in a staging environment.
```

### Optimization example

**Scope:** `packages/server/api/` authentication endpoints

```
| Strengths | Weaknesses |
|---|---|
| S1: JWT refresh works reliably (Impact: 5, Effort: 1) | W1: /login has N+1 query on user role lookup (Impact: 4, Effort: 3) |
| S2: Rate limiting in place (Impact: 4, Effort: 1) | W2: No caching layer for role permissions (Impact: 3, Effort: 2) |

| Opportunities | Threats |
|---|---|
| O1: Add Redis cache for roles (Impact: 5, Effort: 2) — Redis already in infra | T1: Role permissions table grows 10%/month (Impact: 3, Effort: 4) |
| O2: Batch role lookup (Impact: 4, Effort: 1) — pattern exists in other services | T2: Auth service depends on deprecated JWT lib v1 (Impact: 4, Effort: 5) |

**SO (Attack):** Add Redis caching — unlocks 5× impact with existing infra.
**WO (Fix):** N+1 query blocks Redis caching — fix the query first.
**ST (Shield):** Rate limiting protects against the deprecated lib's performance issues.
**WT (Survive):** N+1 + deprecated lib = compounding risk. Fix both.

**Verdict:** The biggest leverage point is adding Redis caching (score 2.5/5) because it unlocks 5× impact with minimal effort. Fix the N+1 query first (WO).
```
