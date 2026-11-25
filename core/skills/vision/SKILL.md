---
name: vision
description: Escreve, valida e decompõe o VISION.md de um projeto (a entrada da factory) num programa de SPs. Usar ao arrancar um projeto novo na factory, com «/vision», ou quando a factory pára com `visao-invalida`.
version: 1.0.0
---
# vision

Um `VISION.md` por projeto-alvo: o {{userName}} decide o objetivo; o agente ajuda a escrevê-lo, valida-o e decompõe-o. Formato e regras: `../super-prompt/references/visao.md`; decomposição: `../super-prompt/references/decompor.md`.

## Fluxo

| Passo | Comando | Saída |
|---|---|---|
| 1. Criar | `kaizen vision init <projeto> [--dir D]` | `<projeto>/VISION.md` com `TBD` (nunca sobrescreve sem `--force`) |
| 2. Preencher | grill curto (skill `grill-me`) secção a secção | Goal, Users, Success criteria, Constraints, Non-goals, Milestones |
| 3. Validar | `kaizen vision validate <VISION.md>` | rc 0; rc 1 lista o que falta: voltar ao passo 2 |
| 4. Aprovar | `kaizen vision resumo <VISION.md>` | um ecrã mostrado ao {{userName}}; sem «sim» não se decompõe |
| 5. Decompor | `kaizen vision decompor <VISION.md> --dry-run`, depois sem `--dry-run` | mãe + um filho por milestone em `sp/TODO` (idempotente) |
| 6. Correr | `kaizen factory run <projeto>` (ou `--manual`) | ver `docs/factory.md` |

## Regras

- Critério de sucesso sem comando em `código` nem «Observação:» é rejeitado: reescrever, nunca apagar.
- `ui: sim` exige `design_system` (skill `design-system`, `kaizen ds init`).
- `orcamento` com números (teto por SP e por dia); a factory pára com `orcamento` ao passar.
- Factory parada com `visao-invalida`: corrigir o `VISION.md` (passos 2-3) e `kaizen factory run <projeto>` retoma.

## Proibições

- Nunca inventar objetivo, utilizadores ou orçamento: perguntar ao {{userName}}.
- Nunca decompor um `VISION.md` que não passa no `validate` nem sem o «sim» ao resumo.
