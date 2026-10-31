---
name: pr-fase
description: Fase final do kaizen flow - abre o PR com template padrão (feito, decisões, por fazer, prova) a partir do SP, pen test e review
version: 1.0.0
---
# pr-fase

Só depois do `review-ciclo` APROVADO.

`python -I scripts/pr_corpo.py <SP.md> --review <estado.json> [--pentest <relatorio>] [--repo R] [--titulo T] [--criar]`

Sem `--criar` imprime o corpo (template `PR_TEMPLATE.md`: O que foi feito, Decisões tomadas, O que ficou por fazer, Prova). O corpo vem do SP (Objective, Progresso, Decisões, Por fazer, Prova de done) mais o relatório do pen test e o veredicto do review.

| `pr:` do SP | Com `--criar` |
|---|---|
| auto | `gh pr create` (rc 0) |
| pergunta | rc 3: pedir confirmação ao user com AskUserQuestion |
| nunca / em falta | rc 4, não cria |

Outros rc: 2 review não aprovado; 5 corpo sem «feito» ou sem «prova». Nunca `Co-Authored-By` nem atribuição a agentes.

Testes: `python scripts/test_pr_corpo.py`.
