# michi — detalhe das fases 1, 3 e 5 (2026-10-22)

Texto integral movido de `SKILL.md` (otimização de custo, SP michi-otimizacao-continua). Ler a fase em que se está a entrar.

## Fase 1 — Grill

1. **Grill me.** Run `/grill-me <project name> + feature/change idea`. Goal:
   align on what is being built, why, and the rough shape. Loop until both
   sides agree the framing is solid. *Do not skip — every later step pays
   for getting this right.*
   - **Super Prompt input — skip Phase 1 + Phase 2 (michi 2026-09-04, super-prompt skill).**
     When the user hands you a pre-built Super Prompt (the 8-section artefact
     produced by the `super-prompt` skill — sections 1.Role, 2.Context, 3.Objective,
     4.Success, 5.Constraints, 6.Seams, 7.Steps, 8.Done-when), grill and DR are
     already consumed. **Start at Phase 3 (DP)**, or Phase 4 (DA) if the user
     says "go to DA". Treat the 8 sections as a signed contract — do NOT re-ask
     facts already in sections 2/3/4/5. If you find yourself asking one of
     those, the Super Prompt was incomplete and the user should know, not
     silently re-ground.
   **Ordering note (michi 2026-09-03, self-evolution):** DR runs BEFORE
   grill by default. The agent first reads the repo (`search_files`,
   `read_file`, route/symbol scans) so the grill questions are informed
   by what's actually in the project — not generic. To honour legacy
   ordering (grill first), say `/michi skip dr` or `/michi grill`.
   Without a DR artefact, grill may suspend with a minimum-DR gate
   (≥1 file read or ≥1 symbol mapped per touched area).

## Fase 3 — DP (TDD)

3. **Deep Planning (TDD-shaped).** Run `/dp <goal from phase 1 + findings from phase 2>`.
   Produce a plan with: assumptions, 3-7 phases (what / scope / done-when),
   risks, out-of-scope. Loop with the user until they sign off.
   Each phase must be a TDD cycle in plan form:
   - **Seams:** which public interfaces/seams the phase will test. Confirm
     with the user *before* writing the phase. No test at an unconfirmed seam.
   - **Red:** the failing test that proves the gap. Behaviour, not
     implementation; expected value from a literal/spec, never recomputed.
   - **Green:** the minimum code that makes the test pass. No anticipating
     future tests (YAGNI). Mock only at system boundaries (external APIs,
     time, FS, sometimes DB). Never mock your own classes.
   - **Tautology check:** the test must be able to fail for a user-visible
     reason. If it can't, rewrite it.
   - **Audit table gate (michi 2026-09-03, self-evolution).** Before
     sign-off, every DP must include a one-line audit table per phase:
     `phase | what exists today | what changes after | redundant?`.
     Any row marked `redundant=yes` is struck from the plan. Ladder
     rung 1 applies at DP-time, not just at DA-time — if a proposed
     change duplicates state that already lives somewhere else
     (e.g. `colId` already records move, server PUT already validates,
     enum already exists), it's either redundant or a bug-prone
     second source of truth. Strike it.
   - **Pattern-fit check:** antes do sign-off, nomear o padrão (catálogo em `references/michi-patterns.md`) com uma pergunta livre «que padrão encaixa e porquê?».
   - **Refactor** is *not* part of the cycle — it lives in review, not in
     step 4.

## Fase 5 — Gates e prova de done

5. **Gates.** Run the project's verification commands (build, tests, lint,
   typecheck, e2e — whatever applies). *Every command and its RC must
   appear in the report.* If any gate fails, fix root cause, re-run all
   gates. Do not paper over with `|| true`.
   **Gate `harden`** (após DA, antes do Report): `/harden vault` (ou o repo do SP) sobre o que a DA alterou; FAIL bloqueia o Report até corrigir a causa; o resultado vai para o Report. `skip harden` salta-o (one-shot: corre sempre, sem perguntar).
   **Prove it's done (antes de `sp-move.py ... done` e do `COMMIT_*.md`).**
   Agir como o cliente final da feature: executar o caminho real do
   utilizador (app/CLI/comando, skill `run` se aplicável; em docs/vault,
   ler o resultado como leitor: links resolvem, instruções reproduzem; em
   regras de agente, um cenário que a regra deve mudar). Não repetir
   testes/lint de `da`. Registar comando + output/caminho numa secção
   extra `## Prova de done` no SP (fora das 8; `sp-validate.py` tolera).
   Se a prova falhar, o SP não passa a Done: reportar a falha como é.

   **SP com `gates:` no frontmatter:** correr `python -I scripts/sp-gates.py <SP>` em vez de inferir os comandos; rc 0 = verde, 1 = gate vermelho (corrigir a causa e repetir), 2 = gate inválido/proibido (nada corre). O resumo (comando, rc, duração, últimas linhas) vai para o Report. Vermelho impede `sp-move.py ... done`. `prova:` (comando ou critério) é a prova de done. Sem `gates:`, mantém-se o comportamento acima.
   Consolida e referencia as provas por fase (`## Prova`, `references/michi-prova.md`).
   **E2E de fecho de árvore** (só quando este SP fecha uma árvore mãe+filhos+netos; não a cada filho): (a) mecânica, `python -I scripts/sp-list.py --tree-closed <slug>` (rc≠0 = filho/neto por fechar, status≠pasta, dependência por cumprir ou sem `COMMIT_*.md`); (b) código entregue em `code\<projeto>`: build/typecheck/testes e um cenário e2e dos casos de uso do SP-mãe. Resultado com output no Report; falha impede propor o commit e abre correção. Detalhe: `workflow-sp-michi.md`.
