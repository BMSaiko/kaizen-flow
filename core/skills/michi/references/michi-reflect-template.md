# michi — Reflect template (Phase 7)

> Use this at the end of every michi cycle, **after Report, before
> commit-suggest**. Michi proposes; you apply. This file is the recipe —
> copy, fill, propose, wait for "ok", then run the appropriate
> `skill_manage` / `write_file` / vault edit.

## Reflect por fase (2026-10-20)

No fim de **cada fase**, antes do handoff. Três linhas, só sobre essa fase:

```
Reflect <fase>: correu mal: <1 frase> · patch: <1 frase> · onde: <ficheiro>
Reflect <fase>: sem patch
```

- O patch é aplicado já ao ficheiro da fase e entra no CHANGELOG (sem commit).
- Custo: ≤3 linhas e 1 `Edit` por fase; sem `Read` extra além do ficheiro a editar.
- O reflect final (Phase 7) consolida só gaps transversais e padrões repetidos; não repete linhas de fase.

## When to skip

- User said `/michi skip reflect` → skip.
- The cycle was trivial (single-line fix, no friction, no surprises) →
  still run Reflect, but keep it to 2 lines: "Nothing to evolve." Done.

## The four questions

Answer each in **one line** (≤120 chars). Friction is anything that
slowed the cycle, not only errors.

```
1. What slowed this cycle?
2. How did I work around it?
3. Where should that workaround live next time?
4. Is the same friction likely in other cycles? (yes/no/maybe)
```

## The three exit paths

Pick **exactly one** (or split into one of each if the cycle produced
multiple gaps). Default: one path per cycle.

### Path A — patch michi itself

Use when the friction is **inside the michi workflow** (a phase was
unclear, a pitfall was missed, a stop point wasn't honoured). The
patch is small enough that one cycle of evidence justifies it.

Format:

```
PROPOSAL (Path A — patch michi):
File:    ~\AppData\Local\hermes\skills\michi\SKILL.md
Section: ## Pitfalls  (or whichever section)
Before:  <one-line current text>
After:   <one-line proposed text>
Why:     <the cycle's friction, in one sentence>
```

Apply (only after user says ok):

```python
skill_manage(
    action="patch",
    name="michi",
    old_string="<exact before text>",
    new_string="<exact after text>",
)
# Then bump version 1.x → 1.(x+1) in frontmatter and description if changed.
```

### Path B — new helper skill

Use when the same friction has shown up in **≥3 cycles** and the fix
lives outside michi (a new mini-skill, a TDD helper, a verification
script). Do **not** propose this on the first occurrence.

Format:

```
PROPOSAL (Path B — new skill):
Name:        michi-<short-name>
Trigger:     <slash command or natural phrase>
Purpose:     <one-line>
Inputs:      <what it takes>
Outputs:     <what it returns>
Replaces:    <which step of the michi cycle this lives at>
```

Apply (only after user says ok): use `skill_manage(action="create",
...)` with a proper frontmatter + body. The skill must reference michi
in `metadata.hermes.related_skills`.

> **ponytail:** the helper skill is almost always smaller than you
> think. If it would be >100 lines, it's a `references/` file under
> michi, not a new skill.

### Path C — log a gap, do not act

Use when the friction is real but **not actionable in this cycle**
(would need a bigger conversation, or it's the first occurrence, or
the fix is a debate not a patch). The gap goes to the vault backlog
where SIL picks it up later.

Format:

```
PROPOSAL (Path C — backlog):
File:    knowledge/infra/improvement-backlog.md
Section: <existing section or "## Michi pipeline">
Bullet:  - [ ] <one-line gap> `[YYYY-MM-DD]` <why-now>
```

Apply (only after user says ok):

```python
# Use a vault edit; on Windows, use execute_code with pathlib
# (terminal sandboxes do not see C:\). Atomic append.
```

## Hard rules

- **Never** auto-apply any of the three paths. Reflect ends with the
  proposal text + "Apply which? (A/B/C/none)" and stops.
- **Never** invent new path letters. If none of A/B/C fits, the answer
  is C with a note in the bullet ("needs bigger discussion").
- **Never** modify the report to hide friction. The report is the data
  Reflect operates on. Sanitised reports produce sanitised evolution.
- **Never** skip Reflect because michi is being run from a cron or a
  delegate. Reflect runs at the *calling* agent's level — subagents do
  not own michi, the orchestrator does.

## Worked example (from real cycle: 2026-09-02 michi self-evolution)

```
1. What slowed this cycle?
   DR phase listed too many `node_modules/` paths in vault scan output.
2. How did I work around it?
   I filtered the rglob results by `node_modules` exclusion inline.
3. Where should that workaround live next time?
   Add a pitfall in SI's gap-scanner SKILL.md.
4. Likely elsewhere? maybe.

PROPOSAL (Path C — backlog):
File:    knowledge/infra/improvement-backlog.md
Section: ## Self-Improvement
Bullet:  - [ ] SI gap scanner excludes node_modules by default `[2026-09-02]` DR over-reported false positives
```

(No Path A — the fix is not in michi. No Path B — only one cycle of
evidence, gate is ≥3.)
