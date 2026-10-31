---
name: michi
description: Project workflow with self-evolution. Reflect, then commit.
version: 2.4
author: user
license: MIT
---
## michi — full project workflow

**Fluxo:** dr → grill → dp → da → gates → report → reflect → commit. **Regras duras:** sem auto-commit/push; prova e reflect por fase. **Detalhe:** `references/`.
## Help

`/michi help|--help|-h|?`: responder só com a Usage e parar. Uso: `/michi [--auto] [<idea>|<SP>]`, `skip <fase>`, `go to DA`. Skills suplementares: `references/michi-help.md`.

**Estado do SP:** no arranque `python -I scripts/sp-estado.py <SP>` (≤30 linhas: fase, passos, gates, deps, ramo, ficheiros) em vez de ler SP, lista e git à parte.
**Perfil do SP:** ler `perfil`/`max_tentativas`/`parar_se` no arranque e na paragem (`references/michi-perfis.md`).
**Worktree:** no arranque `python -I scripts/sb-worktree.py ensure <slug-do-SP>` e editar pelo caminho absoluto da worktree (o guard bloqueia escrita no checkout principal); `sp-move`/`sp-fechar` saltam sozinhos para a worktree; commits por fase lá; `merge` (recusa SP fora de Done, `--force` explícito) + `clean` só no fecho.
**Tab:** no arranque `python -I scripts/tab-title.py <slug-do-SP>` (best-effort, rc 0; renomeia a tab do WezTerm e imprime `/rename <slug>` para a sessão). Vale também para a sessão nova do `/sp-handoff`, que arranca com `/michi`.

**Checkpoint/rollback:** `scripts/michi-checkpoint.py save|restore` antes da DA e na paragem por gate (`references/michi-modo-auto.md` §Paragem).

O user pode parar após qualquer passo (`/stop`) e retomar (`/resume` ou novo `/michi` no mesmo contexto).

## Phases

Hooks (`kaizen-hooks.json`, ref. `knowledge/infra/reference/kaizen-hooks.md`): em cada início/fim de fase, gate falhado, commit e fecho correr `python -I scripts/kaizen_hooks.py fire michi.<phase.start|phase.end|gate.failed|commit|closed> --slug <SP> --project <p>` (rc≠0 de bloqueante = parar e reportar). Sem config é no-op.

1. **Grill me.** `/grill-me <projeto + ideia>` até alinhar o quê, porquê e forma. Por defeito DR corre antes do grill; **Super Prompt de 8 secções como input: saltar fases 1-2 e começar no DP (ou DA se pedido), sem repetir factos das secções 2/3/4/5.** Detalhe (ordem DR/grill, min-DR gate): `references/michi-fases-detalhe.md` §Fase 1.
2. **Deep Research.** Run `/dr <project> <area touched>`. Goal: surface the
   real code paths, constraints, prior art, and integration points. Cite
   primary sources (files in the repo, official docs). End with a 1-screen
   synthesis: *where the change lands, what it must respect, what's risky*.
3. **Deep Planning (TDD-shaped).** `/dp <objetivo + achados do DR>`: assunções, 3-7 fases (o quê / âmbito / done-when), riscos, fora de âmbito; cada fase é um ciclo TDD (Seams confirmados → Red → Green → tautology check; refactor fica na review). **Antes do sign-off: tabela de auditoria por fase `phase | existe hoje | muda depois | redundant?` (redundant=yes sai do plano) e pattern-fit check (`references/michi-patterns.md`).** Detalhe: `references/michi-fases-detalhe.md` §Fase 3.
4. **Deep Acting.** Run `/da <the signed-off plan>`. Implement phase by
   phase following the TDD plan agreed in step 3, surfacing blockers early.
   Track with `todo`. No "done" without evidence (RC, test output, lint).
   - **Prova por fase (2026-10-20).** Gate de saída de cada fase de entrega (código/UI): antes de a dar por fechada (e do handoff), apresentar uma prova observável como o cliente final (UI = print/`run`; backend = chamada real/output/benchmark), guardada em `proofs/` junto do SP e referenciada em `## Prova`. Dizer sempre o caminho absoluto das provas na resposta. Sem prova: bloquear e perguntar ao user; one-shot: prova alternativa e registar «sem prova». Tabela e regras: `references/michi-prova.md`.
   - **Reflect por fase (2026-10-20).** No fim de cada fase (qualquer fase michi, não só DA), antes do handoff: correr `/reflect fase <SP>` (skill `reflect`; a linha fica em `## Reflect` do SP e sobrevive ao handoff).
   - **Modo auto (2026-10-21).** `/michi --auto <SP>` ou `modo: auto` no frontmatter: sem `AskUserQuestion`, commit local e `sp-move done` sozinho, nunca push (`modo: manual` = sem auto, sem pergunta). Sem nenhum dos três, o arranque pergunta «com/sem auto». Regras, pergunta e report: `references/michi-modo-auto.md`.
   - **Handoff por fase:** ver tabela «Quem dispara o handoff» em `## Contexto`.
5. **Gates.** Correr build/tests/lint/typecheck/e2e aplicáveis; cada comando e RC vão para o report; falha = corrigir a causa e repetir todos, sem `|| true`. Inclui o gate `/harden` (skip: `skip harden`). SP com `gates:` no frontmatter: `python -I scripts/sp-gates.py <SP>` (rc≠0 = não fecha); sem `gates:`, como antes. **Fecho num só passo:** `python -I scripts/sp-fechar.py <slug> [--next]` = gates + context-budget + `done` + `COMMIT_*.md` (pára sem mover se falhar). **Antes de `sp-move.py ... done` e do `COMMIT_*.md`: prova de done** como cliente final, registada em `## Prova de done` no SP (se falhar, o SP não passa a Done); E2E de fecho de árvore só quando este SP fecha mãe+filhos+netos (`sp-list.py --tree-closed <slug>`). Detalhe: `references/michi-fases-detalhe.md` §Fase 5.
6. **Report.** Output: what changed (paths + brief diff), what was verified
   (commands + RC/output), difficulties encountered (real, not sanitised),
   what is still open. No commit. No push.
7. **Reflect (final = consolidação).** Correr `/reflect final <SP>` antes de propor o commit (skill `reflect`: lê `## Reflect`, propõe A/B/C, o user aplica).
8. **Review restart on user pushback.** When the user says there's
   something wrong, broken, missing, or erroneous in the work
   (trigger phrases: "está errado", "está partido", "tem erros",
   "isso não está certo", "isso está mal", "wrong", "broken",
   "has bugs"), the michi cycle restarts at the most relevant
   earlier phase — not just DA. The agent asks which phase the user
   thinks went wrong, then re-runs from there with the new input.
   Default restart point: Phase 1 (Grill). If the user signals
   "scope changed" or "we're solving the wrong problem", restart
   at Phase 1. If they signal "implementation is wrong but the plan
   is right", restart at Phase 4 (DA). Honour the signal — don't
   default to "just patch DA" when the root cause is upstream.
9. **Autorizações do SP:** `commit`/`push`/`pr`/`restricoes` do frontmatter mandam no fecho (auto ou manual); regras em `references/michi-modo-auto.md` §Autorizações do SP.
10. **Commit proposal.** *Only after the user explicitly approves the report
   (and has had the chance to act on Reflect).* Suggest a single
   conventional commit message (one line subject ≤72 chars, body explaining
   *why*). Show the message; the user types "commit" / "ok" before any
   `git commit` runs. Push + merge are a separate user-confirmed step
   (suggest target branch, default = main). **If the repo has more than
   one long-lived default branch (e.g. `master` AND `main` AND `dev`),
   ask which one before pushing — guessing wastes a "enganei-me, era
   suposto X" round-trip** (michi 2026-09-03).

   **Worktree → dev:** `fetch`, merge de `origin/dev` NO worktree, resolver e correr os gates lá, só depois merge no pai (`references/michi-worktree-merge.md`).

## Document Lifecycle

DR/DP/SP movem-se TODO → Doing → Done com `sp-move.py`/`doc-move.py`; `/michi status` lista o estado. Scripts, tabela de eventos e `status`: `references/michi-lifecycle.md`.

## Style

16 entradas numeradas em `references/michi-style.md` (ex.: pergunta em texto livre por defeito, não repetir factos do user, honrar «skip fase X», respostas curtas). Ler só a entrada relevante.

## Contexto (context-guard)

Se aparecer `[context-guard] Contexto … >= limite`: acabar o passo em curso (nunca a meio de uma edição ou teste) e correr em modo automático (sem perguntar, `--launch --auto`) o handoff que o aviso nomear: `/sp-handoff` se a sessão correu `/michi <SP>` (o guard liga a sessão ao SP ao ver o prompt), `/handoff` se é conversa livre. Sem o aviso, nada muda.

**Quem dispara o handoff**

| Gatilho | Modo | Regras |
|---|---|---|
| Fim de fase com verificação verde, SP em Doing (`/michi <SP>`) | `/sp-handoff` manual: regista `## Progresso`, pergunta sim/não | um por fase, não por passo; nunca a meio de edição/teste; não repetir se o guard já o fez nessa fase |
| `[context-guard]` ≥ limite | `--launch --auto`, sem perguntar | acabar o passo em curso primeiro |
| Modo auto (`--auto`) | `--launch --auto` por fase | sem `AskUserQuestion` |
| Sem SP em Doing | nada (`/handoff` só em conversa livre) | |

**Arranque `/michi <SP>` com sessão suja:** se o contexto já tem conversa anterior (não veio de `/clear` nem de handoff), um só AskUserQuestion: "Limpar e iniciar o SP em sessão nova?" + modo (§Pergunta de arranque); com «sim», `python -I scripts/sp-handoff.py --launch <caminho>` (`--auto` se escolhido) e terminar o turno.

## Pitfalls

30 entradas numeradas em `references/michi-pitfalls.md` (índice: `references/michi-pitfalls-index.md`). Ler só a relevante.

## See also

- `.claude/skills/reflect/` — Reflect (`/reflect fase|final`)
- `references/michi-skip-grill-play.md` — skip-grill recipe
- `knowledge/infra/skills/self-improvement-loop/SKILL.md` — daily SIL
- `knowledge/infra/skills/learn-from-session/SKILL.md` — LFS at session close
- `scripts/skill-cut.py` — encolher uma secção de SKILL.md para `references/` com contagem verificada (Reflect 2026-10-18)
