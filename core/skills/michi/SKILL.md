---
name: michi
description: Orquestra o ciclo de um projeto ou SP, do grill ao commit, com gates, prova e reflect por fase. Usar para executar um SP ou levar uma ideia até ao commit.
version: 2.7
---
## michi — orquestrador do ciclo de projeto

**Fluxo:** dr → grill → dp → da → gates → pentest → review → docs → pr → report → reflect → commit. **Regras duras:** prova e reflect por fase; commit, push e merge só com autorização (§Regras transversais). Detalhe nas skills de fase e em `references/` (índice `michi-orquestracao.md`).

**Help:** `/michi help|-h|?` responde só com a Usage e pára. Uso: `/michi [--auto] [<idea>|<SP>]`, `skip <fase>`, `go to DA` (`references/michi-help.md`).

## Fases

| # | Fase | Skill / comando | Gate de saída | Decide |
|---|---|---|---|---|
| 1 | Grill (DR antes, por defeito) | `/grill-me` | decisões alinhadas; SP de 8 secções salta 1-2 | user |
| 2 | Deep Research | `/dr` | síntese de 1 ecrã | agente |
| 3 | Deep Planning (TDD) | `/dp` | auditoria por fase + pattern-fit; sign-off | user |
| 4 | Deep Acting | `/da` | prova por fase + `/reflect fase` | agente |
| 5 | Gates | `sp-gates.py` · `/harden` | cada comando com RC; falha = corrigir e repetir tudo | agente |
| 6 | Pentest | `/pentest` | sem achados abertos (ou decisão do user) | agente / user |
| 7 | Review | `/review-ciclo` (`sp-revisor.py`, revisor independente) | APROVADO; ESCALAR após 3 iterações | agente / user |
| 8 | Docs | `references/michi-docs.md` | README/MOC/CHANGELOG atualizados ou skip justificado; prova em `## Docs` | agente |
| 9 | PR | `/pr-fase` | corpo pela template, respeitando `pr:` | agente |
| 10 | Report | `/report` (`sp-report.py`) | 5 secções, «Dificuldades» não vazia | agente |
| 11 | Reflect | `/reflect final` | A/B/C proposto; o user aplica | user |
| 12 | Commit | `/commit-msg` → `/commit` | `COMMIT_*.md` aprovado | user |

Sem as skills `/harden`, `/report`, `/reflect` ou `/commit` (vault), o passo faz-se à mão: gates com RC, `sp-report.py`, `## Reflect` do SP, commit com stage explícito.

Fase **2b Spike** (opcional): só com `spike: incerto` no SP, timebox `max_requests`, go/no-go em Decisões; `references/michi-spike.md`.

`skip <fase>` salta só essa fase (`skip harden|pentest|review`; nunca os gates). SP completo: `sp-fechar.py <slug>` com `## Prova de done`; linha `PRÓXIMO FILHO`/`ÚLTIMO FILHO`: manual = `AskUserQuestion`, auto ou fila (`--programa`) = sem perguntar (`--seguinte` abre o próximo; `fechar-mae` no fim) e fechar a mãe numa worktree (`michi-lifecycle.md` §Fecho). Nunca omitir.

## Arranque

1. `python -I scripts/sp-estado.py <slug>` (fase, passos, gates, ramo) e ler `perfil`/`max_tentativas`/`parar_se`. SP vazio = Grill; correr o Arranque todo e a «sessão suja» (`michi-orquestracao.md`) antes da fase 1. «SP não encontrado»: ramo atrás de `master` → `git merge master` e repetir.
2. SP em TODO: `python -I scripts/sp-move.py <slug> --start` (SP e mães para Doing, idempotente). `python -I scripts/sb-worktree.py ensure <slug>` se existir (senão `git worktree add`); editar pelo caminho absoluto da worktree; `merge` + `clean` só no fecho com o SP em Done.
3. `python -I scripts/tab-title.py <slug>` e seguir nesta sessão, sem `Agent`. Painel WezTerm só com `--painel` (`michi_handoff_auto.py decide --painel`, `go <slug>`). Já dentro de um painel ou `--handed`: seguir sem relançar.
3b. SP novo em auto: `python -I scripts/sp-aprovar.py <slug> --verificar`; rc 1 = por aprovar: recusar e dar a instrução (`sp-resumo.py`, «sim» do user, `sp-aprovar.py`).
4. Modo: `--auto` ou `modo: auto` no frontmatter = sem `AskUserQuestion` (`modo: manual` = sem auto, sem pergunta); sem nenhum, perguntar «com/sem auto».
   Se o `sp-estado` diz `execução: por escolher` (SP-mãe com filhos), mesmo em `modo: manual`, `AskUserQuestion` «sequencial ou paralelo?» (caso a caso, sem defeito) e gravar antes de lançar: `python -I scripts/sp-execucao.py <slug> sequencial|paralelo`; com `execucao:` preenchido não perguntar. Depois `/sp-fila --programa <slug>` (sequencial = um filho de cada vez; paralelo = até 3 painéis no total, com o vigia a fazer merge e avisos).
5. Checkpoint: `scripts/michi-checkpoint.py save|restore` antes da DA e na paragem por gate.

Hooks `michi.*`, sessão suja, handoff, `[context-guard]` e painéis: `michi-orquestracao.md`.

## Regras transversais

- **Prova por fase** de entrega antes de fechar e do handoff, em `proofs/` (`sp-prova.py`), caminho absoluto na resposta (`michi-prova.md`).
- **Reflect por fase** em `## Reflect` do SP; **final** antes de propor o commit (skill `reflect`).
- **Pushback do user** («está errado»): recomeçar na fase a montante, por defeito Grill (`michi-orquestracao.md` §Review restart).
- **Commit/push/merge**: regra única em `michi-modo-auto.md` §Proibições e §Autorizações; worktree para dev em `michi-worktree-merge.md`.
- **Ciclo de vida** TODO → Doing → Done com `sp-move.py`; `/michi status` (`michi-lifecycle.md`).

## Style e Pitfalls

`michi-style.md` e `michi-pitfalls.md` (índice `michi-pitfalls-index.md`): ler só a entrada relevante.

## See also

`reflect` · `michi-skip-grill-play.md` · `scripts/skill-cut.py`
