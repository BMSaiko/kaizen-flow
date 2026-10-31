---
name: super-prompt
description: Build Super Prompt — chains brainstorm+swot+grill-me+dr
version: 1.1.0
author: Hermes Agent (user)
license: MIT
triggers:
- super-prompt
- super prompt
- /super-prompt
metadata:
  hermes:
    tags:
    - prompt
    - planning
    - michi
    - orchestration
    - super-prompt
    category: workflow
    related_skills:
    - michi
    - brainstorm
    - swot
    - grill-me
    - dr
    - five-whys
    - swot
    - eisenhower-matrix
    - ooda-loop
changelog:
- '1.1.0: Added `validateSuperPrompt()` auto-validation in `savePrompt()`, `--quick`
  flag for trivial goals (skips brainstorm + DR), and grill-me templates
  by domain (codigo, design, infra, docs). Updated verification checklist.
  Lesson: 2026-09-10 super-prompt self-optimization cycle.'
- '1.0.9: Updated save location to per-project structure knowledge/projects/kaizen/<project>/sp/TODO/.
  Added project field to frontmatter. Updated savePrompt() and transitionStatus()
  helpers to handle per-project dirs. Discovered structure: atlas, kaizen, kaizen-core,
  michi, hermes, pi-agent, wezterm, docs-auto-update each have their own SP dir. Lesson:
  2026-09-06 atlas SP creation session.'
- '1.0.8: Added frontmatter (status, created, updated, phase), savePrompt() and transitionStatus()
  helpers, new default path knowledge/projects/kaizen/sp/TODO/. Lesson: 2026-09-10
  super-prompt persistence refactor.'
- '1.0.7: Pitfall #12 (anchor strings must be copied from file, not from memory) +
  Pitfall #13 (DR mini must cite live infra only — strip-kanban cycle proved the previous
  ''atlas-kanban-card-driven-loop'' SP listed dead seams). Lesson: 2026-09-05 atlas-mundo-workflow-michi
  session.'
- '1.0.6: Pitfall #11 (clarify time-out = silent confirmation). Lesson: 2026-09-05
  atlas-strip-kanban session.'
- '1.0.2: Pitfall #8 (one-round grill-me, no second clarify for defaults) + Pitfall
  #9 (write_file fails on shell-hostile content; use execute_code+pathlib). Save-location
  section now names the default write tool for Windows. Lesson: 2026-09-04 atlas-design-polish
  session.'
- '1.0.4: Extended Pitfall #9 to cover the ''A = body.append; A("...")'' trap — unbalanced
  '')'' inside one fragment breaks the parser before the write runs. Canonical fix:
  build a plain list of string literals, no aliased appender. Lesson: 2026-09-05 atlas-strip-kanban
  super-prompt session.'
- '1.0.3: Merged pitfalls #9+#10 into one body-fragment-list pattern — ''body = "..."''
  inside execute_code also crashes on shell-hostile content, so the recipe (fragment
  list + join) is the single correct save path. Lesson: 2026-09-05 hermes-done-bell
  session.'
- '1.0.1: Added pitfall #7 (user pivot mid-pipeline) + style rule for clean abort.
  Lesson: 2026-09-04 session pivoted from super-prompt to ''update skills'' mid-grill-me.'
- '1.0.0: Initial 4-phase pipeline + 8-section template.'
---
# Super Prompt

Build a **Super Prompt** — a paste-ready, self-contained instruction set for
any goal. Uses `brainstorm` -> `swot` -> `grill-me` -> `dr` as a 4-phase funnel
and then assembles the result into a single, high-fidelity prompt you can
feed into a fresh session (e.g. `/michi <super-prompt content>`).

Runs **outside** the michi cycle. The Super Prompt is the artefact, not
implementation.

## When to use

- You have a goal, bug, refactor, feature, or project idea and want the
  *best possible prompt* to hand to another agent/session/model.
- You want the prompt to be self-contained: no follow-up questions, no
  "could you clarify...", no missing context.
- You want the result to survive a session boundary (you'll come back
  tomorrow and run the prompt cold).

## When NOT to use

- You're already inside a michi cycle and just want a better next-step
  prompt — use `/dp` or `/dr` directly.
- You want a *tiny* prompt for a *trivial* task. Super Prompt is overkill
  for one-line asks.
- You want execution now, not a reusable prompt. Use `/michi <idea>`
  instead.

## Invocation

```
/super-prompt <your goal here>
/super-prompt --quick <trivial-goal>
```

If the user typed only `/super-prompt` (no goal), ask once for the goal
(free-text), then start the funnel.

If `--quick` is present, the goal must be trivial (≤ 3 lines).
Skip Phase 1 (brainstorm) and Phase 4 (dr), going directly to
Phase 3 (grill-me) + DP. The resulting Super Prompt has fewer
sections populated — Role, Context, Objective, Success, Constraints,
Seams, Steps, Done-when — but each is concise. See `## Quick mode`.

## Pipeline (4 phases, then assemble)

Run the four skills **in order**, each as a stop point that writes to the
in-progress Super Prompt draft. Do not skip phases — each one tightens
the next.

### Phase 1 — brainstorm

Load `brainstorm` skill. Goal: surface 8-15 raw ideas around the user's
objective, cluster them (2-5 clusters), pick top 1-3. Output goes into the
draft's `## Brainstorm` section. If `brainstorm` is unavailable, do a
free-text 60s brainstorm yourself; never block on a missing skill.

### Phase 2 — swot

Load `swot` skill. Goal: stress-test the top pick from Phase 1. Populate
the 2x2 matrix, name the dominant constraint + most leveraged move.
Output goes into `## SWOT` section. Same fallback: if `swot` is not
loadable, build the matrix inline.

### Phase 3 — grill-me

Load `grill-me`. Goal: relentlessly
interview the user until the goal, scope, success criteria, constraints,
and non-goals are unambiguous. This is the longest phase. Loop until the
user signals alignment ("ok", "basta", "go", "continua", or similar). On
alignment, write the consolidated answers into `## Spec
(grill-me output)`.

**Priority:** include one question in the batch — "Prioridade? P1 (urgente) /
P2 / P3 (default)". Save the answer as `priority:` in the frontmatter; if
the user doesn't answer, write `P3`.

**Modo do michi:** inclui também «Modo do michi? auto / manual (default manual)». Guarda a resposta como `modo:` no frontmatter (`sp-new.py --modo`); sem resposta, `manual`. Com `modo: manual` ou `auto` o michi não repete a pergunta de arranque.

**Autorizações:** no mesmo lote, UMA pergunta agrupada: commit, push, PR (`auto|pergunta|nunca`; defaults conservadores: `pergunta`, e `nunca` para push/PR se `modo: auto`) e restrições extra (pastas intocáveis, repos, ações externas). Grava em `commit:`/`push:`/`pr:`/`restricoes:` (`sp-new.py --commit/--push/--pr/--restricoes`); o michi cumpre-as (`michi-modo-auto.md` §Autorizações do SP). Comandos pré-aprovados (`--permitir`, repetível) e decisões do grill (`--decisao`, repetível): `michi-modo-auto.md` §Autorizações do SP. Na mesma pergunta, o **perfil** (`cauteloso|normal|autonomo`, recomendado `normal`; `autonomo` só com gates): `sp-new.py --perfil` (+ `--max-tentativas/--max-requests/--parar-se`), semântica em `michi/references/michi-perfis.md`.
**Escalão:** propõe-no com `python -I scripts/sp-escalao.py` (pequena = 1 SP; média = pai+filhos; grande = árvore) e aceita override numa linha; critérios no playbook `kaizen-flow` §Escalões.

**Escopo:** deriva `escopo:` (globs) da secção «Relevant files» e `fora_de_escopo:` do que é intocável: `sp-new.py --escopo a/**,b.py --fora-de-escopo x/**`; sem `escopo` o hook não guarda nada.

**Gates:** no mesmo lote, pergunta «Como se verifica que está certo?». Propõe gates a partir do projeto (`package.json` → `npm test`/`vitest`/lint/build; `scripts/test_*.py` → `python -I scripts/test_sp_list.py`) e confirma com o user. Grava em `gates:` (um `- cmd:` por gate, `cwd`/`timeout` opcionais) e `prova:` (`sp-new.py --gate` repetível, `--prova`). Comandos proibidos (`--force`, `reset --hard`, `git add -A`, `.env*`) são recusados por `sp-validate.py`.

**Rule:** grill-me's blocker rule applies — if the goal is empty /
placeholder, do NOT interview. Write a blocker note in the draft and
exit. The user must re-invoke with a real goal.

**Templates:** When the goal's domain matches a known category
(codigo, design, infra, docs), use the matching template from
`## Grill-me Templates` as a starting point. The template provides
default questions — the executor may adapt them. See `## Grill-me
Templates` below.

### Phase 4 — dr (mini)

Load `dr` (Deep Research). Goal: list the **minimum** code paths /
context / integration points the new session will need to know. This is
a mini-DR, not the full michi DR — keep it <= 1 screen. Anchor every
claim to a primary source (file path, doc URL, error string). Write into
`## DR (mini)`.

**Skip rule:** if the goal is non-code (e.g. "draft a marketing email"),
skip Phase 4 entirely and note "DR skipped: non-code goal" in the draft.

## Assembly (the Super Prompt)

After Phase 4, assemble the Super Prompt. **Always use this exact
8-section template** — it's the contract. The receiving session / model
must be able to execute from the template alone.

```markdown
# Super Prompt - <slug> (<YYYY-MM-DD>)

> Generated by `/super-prompt`. Execute with `/michi <paste this file's body>`.

## 1. Role
You are <role>. You operate with <constraints on style, scope, decision authority>.

## 2. Context
- Project: <name + 1-line description>
- Repo: <path or URL>
- State: <branch, last commit, key facts the executor must know>
- Relevant files: <paths the executor will touch>

## 3. Objective (single sentence)
<One sentence. If you cannot write it in one sentence, the goal is not clear enough — restart grill-me.>

## 4. Success criteria (verifiable)
- [ ] <observable thing 1>
- [ ] <observable thing 2>
- [ ] <observable thing N>

## 5. Constraints / invariants
- Must keep: <X, Y, Z — anything that must NOT change>
- Must avoid: <A, B, C — anti-patterns the executor must not introduce>
- Performance / size / scope limits: <if any>

## 6. Seams (public interfaces to test / change)
- `<Module.func>` — <what it does today, what changes>
- `<API.route>` — <request/response shape, validation rules>

## 7. Steps (numbered, ordered)
1. <Step 1 — concrete action, file path or command>
2. <Step 2>
3. <...>

## 8. Done-when
<The single observable signal that means "ship it". No "looks good".>
```

**Required sections:** all 8. If a section is empty, the goal is
under-specified — re-run grill-me for that section, do not publish an
incomplete Super Prompt.

## Save location

Caminho único, sem resolução livre: criar sempre com

```
python -I scripts/sp-new.py --project <projeto> --slug <slug> --priority P1|P2|P3 --modo auto|manual [--commit C] [--push P] [--pr R] [--restricoes "..."] [--perfil P]
```

Devolve `knowledge/projects/kaizen/<projeto>/sp/TODO/<slug>-<YYYY-MM-DD>.md` (frontmatter + 8 secções vazias). Preencher as secções nesse ficheiro e validar com `python -I scripts/sp-validate.py <ficheiro>`. `<slug>`: minúsculas ascii, hífens, ≤48 caracteres.

Projeto não inferível da pasta de trabalho ou inexistente (sp-new recusa): `AskUserQuestion`; nunca inventar pasta, nem usar `kaizen/sp/` global nem `./super-prompts/`. SPs fora do padrão: `python -I scripts/sp-organize.py` (dry-run; `--apply` só com aprovação do user).

## File frontmatter

Every saved Super Prompt includes YAML frontmatter:

```yaml
---
status: TODO          # TODO | Doing | Done
created: <ISO8601>    # e.g. 2026-09-10T14:32:00Z
updated: <ISO8601>    # updated on status change
phase: SP             # constant, marks Super Prompt artefacts
slug: <slug>
date: <YYYY-MM-DD>
project: <project>    # project name (atlas, kaizen, michi, etc.)
priority: P2          # P1 | P2 | P3 — optional, default P3 (used by /sp-list)
modo: manual          # auto | manual — modo do michi; default manual (sem pergunta de arranque)
commit: pergunta      # auto | pergunta | nunca (idem push, pr); restricoes: texto opcional
perfil: normal        # cauteloso | normal | autonomo (opcional)
---
```

On creation, `status: TODO`, `created` = `updated` = now, `phase: SP`. The `project` field enables cross-project queries and correct status transitions.

## Re-using the Super Prompt in a new session

The user opens a new Hermes / agent session and pastes the Super Prompt
body (or uses a tool to feed it as the goal of `/michi`). The new session
should:

- Skip grill + DR (already consumed by the Super Prompt).
- Start at DP (plan), or DA if the user wants to skip planning.
- Treat sections 1-8 as a signed contract — only deviate with explicit
  user signal.

**The new session must NOT re-ask facts already in sections 2 / 3 / 4
/ 5.** If it does, the Super Prompt was incomplete — note it in the
post-mortem.

## Mais

Templates do grill (code/design/infra/docs), skills suplementares, helpers de persistência, regras de estilo, checklist de verificação e pitfalls: `references/super-prompt-extra.md` e `references/super-prompt-pitfalls.md`. Ler a pedido.

## Output to user (always)

After the Super Prompt is saved and verified, output exactly:

```
Super Prompt saved: <abs path>
Sections: 1.Role 2.Context 3.Objective 4.Success 5.Constraints 6.Seams 7.Steps 8.Done-when
Reuse:    /michi <paste body of this file> in a new session
```

No commit. No push. No DA. The user's job is now to open a new session
and feed the Super Prompt to `/michi`.
