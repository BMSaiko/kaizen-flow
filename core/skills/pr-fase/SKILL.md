---
name: pr-fase
description: Fase final do kaizen flow - abre o PR com template padrão (feito, decisões, por fazer, prova) a partir do SP, pen test e review
version: 1.1.0
---
# pr-fase

Só depois do `review-ciclo` APROVADO.

`python -I scripts/pr_corpo.py <SP.md> --review <estado.json> [--pentest <relatorio>] [--repo R] [--titulo T] [--base B] [--criar] [--dry-run]`

Sem `--criar` (ou com `--dry-run`, que nunca cria) imprime o corpo (template `PR_TEMPLATE.md`: O que foi feito, Decisões tomadas, O que ficou por fazer, Prova). O corpo vem do SP (Objective, Progresso, Decisões, Por fazer, Prova de done) mais o relatório do pen test e o veredicto do review.

| `pr:` do SP | Com `--criar` |
|---|---|
| auto | `gh pr create` (rc 0) |
| pergunta | rc 3: pedir confirmação ao user com AskUserQuestion |
| nunca / em falta | rc 4, não cria |

`--repo` é o caminho local do repo (cwd do `gh`), não `owner/nome`; o SP precisa de `pr:` no frontmatter. Provado com PR real (#1, repo de teste, fechado).

Outros rc: 2 review não aprovado; 5 corpo sem «feito» ou sem «prova»; 6 base ambígua.

A «Prova» inclui os paths `proofs/...` citados no SP, os comandos das `gates:` e o veredicto do review. Base: `--base` manda; senão a única entre `origin/main|master|dev`; mais de uma = rc 6, perguntar ao user. O corpo é limpo de linhas `Co-Authored-By`/`Generated with` (regra em AGENTS.md).

Testes: `python scripts/test_pr_corpo.py`.
