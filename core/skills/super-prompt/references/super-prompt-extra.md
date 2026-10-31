# super-prompt — secções movidas (2026-10-20)

## Supplemental analysis skills

The following skills can be invoked *before* or *during* the pipeline
to sharpen the output:

- **`five-whys`** — If the goal is vague or the problem is unclear, run
  Five Whys first to nail the root cause before brainstorming.
- **`swot`** — If the goal involves a system/process to
  improve, run this SWOT variant to map the situation before grilling.
- **`ooda-loop`** — If the environment is volatile (competitive, fast-moving),
  use OODA to keep the Super Prompt aligned with reality.
- **`eisenhower-matrix`** — After the Super Prompt is saved and actions
  are identified, use this to prioritize the Steps (§7) into a kanban board.

These are optional — the 4-phase pipeline (brainstorm → swot → grill-me → dr)
works without them, but they tighten the result when the situation warrants it.

## Grill-me Templates

Domain-specific question batches for Phase 3. Use when the goal's
domain is identifiable. Each template is a batch of 2-3 questions
with defaults baked in (bake-defaults-into-question-text pattern,
Pitfall #8).

### Code template

```
Qual a linguagem/framework? Por defeito: Python + FastAPI se
backend, TypeScript + React se frontend. O projeto ja tem
testes? Por defeito: sim, cobertura >= 80%. Algum constraint
de performance? Por defeito: não, otimizar depois se necessario.
```

### Design template

```
O output e UI (figma, codigo CSS) ou conceptual (design system
tokens)? Por defeito: tokens + componentes. Tem design-system
existente? Por defeito: reutilizar tokens existentes do projeto.
Precisa de responsivo/acessibilidade? Por defeito: sim, WCAG AA.
```

### Infra template

```
O scope e infra existente ou novo? Por defeito: provisionar
em infra existente. Cloud provider? Por defeito: o atual do
projeto. Precisa de monitorizacao/alerting? Por defeito: sim,
basic (health + logs).
```

### Docs template

```
O output e API docs, README, ou tutorial? Por defeito: o que
o projeto mais precisa. Tem docs generator configurado?
Por defeito: sim (mkdocs, sphinx, etc.). Audience?
Por defeito: desenvolvedores internos.
```

## Persistence helpers

Sem código de referência: usar os scripts do repo (`python -I scripts/...`).
- `sp-new.py --project P --slug S --priority P2 [--parent X] [--depends-on Y]` — cria `sp/TODO/<slug>-<data>.md` com frontmatter e as 8 secções vazias; preencher a seguir.
- `sp-validate.py <ficheiro>` — valida frontmatter e as 8 secções (obrigatório antes de entregar).
- `sp-move.py [--project P] <slug> todo|doing|done` — transição de estado (atualiza `status`/`updated`).
- `sp-list.py` — listar pendentes por prioridade.
- `sp-organize.py [--project P] [--apply]` — deteta SPs fora do padrão (pasta, estado, nome, projeto); dry-run por defeito.

## Style rules (this skill)

- **Default to free-text questions, not multi-choice `clarify`.** During
  grill-me, batch 2-3 questions into one free-text ask when they're in
  the same domain. (michi Style rule.)
- **Honour user list-compression.** "1+2+3, quero X" is the answer -
  stop clarifying. (michi 2026-09-03 lesson.)
- **No filler.** The Super Prompt is paste-ready; bloat is debt.
- **Cite primary sources in DR mini.** File paths, doc URLs, error
  strings - not vibes.
- **If the goal changes mid-pipeline, restart from Phase 1** (grill-me
  is the alignment gate). Do not silently fold changes into later
  phases. (michi 2026-09-02 lesson: "faz um ajuste" to a signed-off
  plan means respect the why.)
- **If the user pivots mid-pipeline to an unrelated meta-task** (e.g.
  "review the conversation and update skills", "forget that, do X
  instead", or pivots to housekeeping), **abort cleanly**. Do NOT
  invent a Super Prompt for the new task, do NOT skip to Phase 4/5 to
  "close the loop". Acknowledge the pivot in one line, hand off to
  the new task. The user can re-invoke `/super-prompt` when ready.
  Pitfall #7 below.

## Verification checklist (after save)

- [ ] File exists at the resolved path (tier 1, 2, or 3).
- [ ] All 8 sections present and non-empty.
- [ ] Section 3 (Objective) is exactly one sentence.
- [ ] Section 4 (Success criteria) items are all observable.
- [ ] Section 5 (Constraints) names at least one "must keep" and one
      "must avoid".
- [ ] Section 8 (Done-when) names a single concrete signal.
- [ ] DR mini (if applicable) cites at least one file path or doc URL.
- [ ] Path printed to the user with the "Next:" hint.
- [ ] **`python -I scripts/sp-validate.py <ficheiro>` devolve ok** (rc=0).
- [ ] **If `--quick` was used**, the resulting SP has all 8 sections
      but is concise (each section <= 3 lines).
- [ ] **If a grill-me template was applied**, the template questions
      appear in the Spec or are noted as defaults used.

## Common pitfalls

Texto integral em `references/super-prompt-pitfalls.md` (10 entradas, numeradas como abaixo). Ler só a entrada relevante.

1. Empty goal
2. Skipping phases "to save time"
3. Multi-choice `clarify` for already-stated facts
4. Incomplete sections 4 / 5 / 8
5. Saving to the wrong path
6. Auto-executing the Super Prompt in the same session
7. User pivots mid-pipeline to an unrelated task
8. Multi-round grill-me when one round + defaults suffices
9. Saving the Super Prompt with shell-hostile content
10. `clarify` tool shape is fragile; failures are opaque
