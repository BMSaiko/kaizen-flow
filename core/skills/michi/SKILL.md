---
name: michi
description: Project workflow with self-evolution. Reflect, then commit.
version: 2.6
author: user
license: MIT
---
## michi — orquestrador do ciclo de projeto

**Fluxo:** dr → grill → dp → da → gates → pentest → review → pr → report → reflect → commit. **Regras duras:** sem auto-commit/push; prova e reflect por fase. O detalhe vive nas skills de fase e em `references/` (índice: `michi-orquestracao.md`).

**Help:** `/michi help|-h|?` responde só com a Usage e pára. Uso: `/michi [--auto] [<idea>|<SP>]`, `skip <fase>`, `go to DA`. Suplementar: `references/michi-help.md`.

## Fases

| # | Fase | Skill / comando | Gate de saída | Decide |
|---|---|---|---|---|
| 1 | Grill (DR antes, por defeito) | `/grill-me` | decisões alinhadas; SP de 8 secções salta 1-2 | user |
| 2 | Deep Research | `/dr` | síntese de 1 ecrã | agente |
| 3 | Deep Planning (TDD) | `/dp` | auditoria por fase + pattern-fit; sign-off | user |
| 4 | Deep Acting | `/da` | prova por fase + `/reflect fase` | agente |
| 5 | Gates | `sp-gates.py` · `/harden` | cada comando com RC; falha = corrigir e repetir tudo | agente |
| 6 | Pentest | `/pentest` | sem achados abertos (ou decisão do user) | agente / user |
| 7 | Review | `/review-ciclo` | APROVADO; ESCALAR após 3 iterações | agente / user |
| 8 | PR | `/pr-fase` | corpo pela template, respeitando `pr:` | agente |
| 9 | Report | `/report` (`sp-report.py`) | 5 secções, «Dificuldades» não vazia | agente |
| 10 | Reflect | `/reflect final` | A/B/C proposto; o user aplica | user |
| 11 | Commit | `/commit-msg` → `/commit` | `COMMIT_*.md` aprovado | user |

Sem `Agent`: fases na sessão principal; outra sessão = painel WezTerm (`michi-orquestracao.md` §Painéis).

Fase **2b Spike** (opcional): só com `spike: incerto` no SP, timebox `max_requests`, go/no-go em Decisões; `references/michi-spike.md`.

`skip <fase>` salta só essa fase (`skip harden|pentest|review`; nunca os gates). SP completo: `sp-fechar.py <slug>` com `## Prova de done`; linha `PRÓXIMO FILHO`/`ÚLTIMO FILHO`: manual = `AskUserQuestion`, auto ou fila (`--programa`) = sem perguntar (`--seguinte` abre o próximo; `fechar-mae` no fim) e fechar a mãe numa worktree (`michi-lifecycle.md` §Fecho). Nunca omitir.

## Arranque

1. `python -I scripts/sp-estado.py <slug>` (fase, passos, gates, ramo) e ler `perfil`/`max_tentativas`/`parar_se`. SP vazio = Grill, não paragem; correr sempre o Arranque todo e a «sessão suja» (`michi-orquestracao.md`) antes da fase 1. «SP não encontrado»: ramo atrás de `master` → `git merge master` e repetir.
2. SP em TODO (p.ex. vindo de `/sp-handoff`): `python -I scripts/sp-move.py <slug> --start` (move o SP e as mães em TODO para Doing, idempotente). `python -I scripts/sb-worktree.py ensure <slug>`; editar pelo caminho absoluto da worktree; `merge` + `clean` só no fecho com o SP em Done.
3. `python -I scripts/tab-title.py <slug>` e seguir nesta sessão, sem `Agent`. Painel WezTerm só com `--painel` (`michi_handoff_auto.py decide --painel`, `go <slug>`). Já dentro de um painel ou `--handed`: seguir sem relançar.
4. Modo: `--auto` ou `modo: auto` no frontmatter = sem `AskUserQuestion` (`modo: manual` = sem auto, sem pergunta); sem nenhum, perguntar «com/sem auto» (`michi-modo-auto.md`).
   Se o `sp-estado` diz `execução: por escolher` (SP-mãe com filhos), mesmo em `modo: manual`, `AskUserQuestion` «sequencial ou paralelo?» (caso a caso, sem defeito) e gravar antes de lançar: `python -I scripts/sp-execucao.py <slug> sequencial|paralelo`; com `execucao:` preenchido não perguntar. Depois `/sp-fila --programa <slug>` (sequencial = um filho de cada vez; paralelo = até 3 painéis no total, com o vigia a fazer merge e avisos).
5. Checkpoint: `scripts/michi-checkpoint.py save|restore` antes da DA e na paragem por gate.

Hooks (`michi.<phase.start|phase.end|gate.failed|commit|closed>`), sessão suja, handoff, `[context-guard]`, painéis: `michi-orquestracao.md`.

## Regras transversais

- **Prova por fase** de entrega (código/UI) antes de fechar e do handoff, em `proofs/` (`sp-prova.py`) com caminho absoluto na resposta: `references/michi-prova.md`.
- **Reflect por fase** em `## Reflect` do SP; **final** antes de propor o commit (skill `reflect`).
- **Pushback do user** («está errado», «wrong»…): recomeçar na fase a montante certa, por defeito Grill; ver `michi-orquestracao.md` §Review restart.
- **Commit/push/merge**: só com confirmação do user (ou `commit|push|pr: auto` no SP); mais de um ramo longo = perguntar qual; worktree → dev em `michi-worktree-merge.md`.
- **Ciclo de vida** TODO → Doing → Done com `sp-move.py`/`doc-move.py`; `/michi status` lista o estado (`michi-lifecycle.md`).

## Style e Pitfalls

`references/michi-style.md` e `michi-pitfalls.md` (índice `michi-pitfalls-index.md`): ler só a relevante.

## See also

`reflect` · `references/michi-skip-grill-play.md` · `knowledge/infra/skills/{self-improvement-loop,learn-from-session}/` · `scripts/skill-cut.py`
