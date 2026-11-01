---
name: michi
description: Project workflow with self-evolution. Reflect, then commit.
version: 2.6
author: user
license: MIT
---
## michi — orquestrador do ciclo de projeto

**Fluxo:** dr → grill → dp → da → gates → pentest → review → pr → report → reflect → commit. **Regras duras:** sem auto-commit/push; prova e reflect por fase. O detalhe vive nas skills de fase e em `references/` (índice: `michi-orquestracao.md`).

**Help:** `/michi help|--help|-h|?` responde só com a Usage e pára. Uso: `/michi [--auto] [<idea>|<SP>]`, `skip <fase>`, `go to DA`. Suplementar: `references/michi-help.md`.

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
| 9 | Report | `/report` | 5 secções, «Dificuldades» não vazia | agente |
| 10 | Reflect | `/reflect final` | A/B/C proposto; o user aplica | user |
| 11 | Commit | `/commit-msg` → `/commit` | `COMMIT_*.md` aprovado | user |

`skip <fase>` salta só essa fase (`skip harden|pentest|review`; nunca os gates). SP completo: `sp-fechar.py <slug>` faz gates + context-budget + `done` + `COMMIT_*.md`, antes com `## Prova de done`. Linha `PRÓXIMO FILHO`/`ÚLTIMO FILHO` no output: manual = `AskUserQuestion` «abrir o próximo?»/«fechar a mãe?»; auto = `--next` e fechar a mãe sozinho. Nunca omitir.

## Arranque

1. `python -I scripts/sp-estado.py <slug>` (fase, passos, gates, ramo) e ler `perfil`/`max_tentativas`/`parar_se`.
2. SP em TODO (p.ex. vindo de `/sp-handoff`): `python -I scripts/sp-move.py <slug> doing`. `python -I scripts/sb-worktree.py ensure <slug>`; editar pelo caminho absoluto da worktree; `merge` + `clean` só no fecho com o SP em Done.
3. `python -I scripts/tab-title.py <slug>`.
4. Modo: `--auto` ou `modo: auto` no frontmatter = sem `AskUserQuestion` (`modo: manual` = sem auto, sem pergunta); sem nenhum, perguntar «com/sem auto» (`michi-modo-auto.md`).
   Se o `sp-estado` diz «perguntar concorrência» (SP com filhos), mesmo em `modo: manual`, `AskUserQuestion` «com ou sem concorrência?» (defeito: sem; com → N): sem = fila em série; com = `/sp-fila --programa <slug> --concorrencia N`.
5. Checkpoint: `scripts/michi-checkpoint.py save|restore` antes da DA e na paragem por gate.

Hooks (`michi.<phase.start|phase.end|gate.failed|commit|closed>`), sessão suja, handoff por fase e `[context-guard]`: `references/michi-orquestracao.md`.

## Regras transversais

- **Prova por fase** de entrega (código/UI) antes de fechar e do handoff, em `proofs/` com caminho absoluto na resposta: `references/michi-prova.md`.
- **Reflect por fase** em `## Reflect` do SP; **final** antes de propor o commit (skill `reflect`).
- **Pushback do user** («está errado», «wrong»…): recomeçar na fase a montante certa, por defeito Grill; ver `michi-orquestracao.md` §Review restart.
- **Commit/push/merge**: só com confirmação do user (ou `commit|push|pr: auto` no SP); mais de um ramo longo = perguntar qual; worktree → dev em `michi-worktree-merge.md`.
- **Ciclo de vida** TODO → Doing → Done com `sp-move.py`/`doc-move.py`; `/michi status` lista o estado (`michi-lifecycle.md`).

## Style e Pitfalls

- 16 entradas em `references/michi-style.md` (pergunta em texto livre por defeito, honrar «skip fase X», respostas curtas). Ler só a relevante.
- 30 entradas em `references/michi-pitfalls.md` (índice `michi-pitfalls-index.md`). Ler só a relevante.

## See also

`.claude/skills/reflect/` · `references/michi-skip-grill-play.md` · `knowledge/infra/skills/self-improvement-loop/SKILL.md` · `knowledge/infra/skills/learn-from-session/SKILL.md` · `scripts/skill-cut.py`
