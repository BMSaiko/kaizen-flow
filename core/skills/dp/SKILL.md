---
name: dp
description: "Escreve o plano (_PLAN_*.md) com fases TDD, gates executáveis, riscos e critérios de done. Usar depois do DR, antes de executar uma tarefa complexa (fase 3 do michi)."
version: 3.0.0
---
# Deep Planning (DP)

Entre DR e DA. Só decisões, fases, riscos e critérios de verificação, sem código. Um plano sem gate executável é um desejo.

| Cenário | Aplicar? |
|---|---|
| COMPLEX (multi-passo, código, arquitetura) / «plan this first» | Sim |
| STANDARD com solução conhecida | Plano leve (2-3 fases) |
| «just do it» / TRIVIAL | Saltar; registar o bypass na nota de sessão |

## Pré-condição (gate do DR)

Research Brief em `knowledge/projects/<projeto>/research/` não vazio, com baixa confiança convertida em riscos; Scope Gate do DR (Full/Delta/Skipped) registado em `## Executive Summary`. Sem DR: `/dr` primeiro; exceção só com contexto conhecido, e dizer a razão.

## Fluxo

1. **Analyze.** Ler o Brief, não repetir a pesquisa; acaba quando o problema cabe numa frase. Problema numa frase, constrangimentos, dependências, MISTAKE_LOG do domínio.
2. **Escrever.** Template e anti-padrões em `references/plano-template.md`. Regras:
   - 2-7 fases (3-7 em DP completo), cada uma um ciclo TDD (Seams → Red → Green → tautologia).
   - Cada fase tem **Done when** (observável), **Gate** (comando copiável para `gates:` do SP) e **Risco** (com mitigação e gatilho).
   - Tabela de auditoria `phase | existe hoje | muda depois | redundant?`; `redundant=yes` sai do plano.
   - SP de código (Scope fora de `knowledge/`): a fase 1 é o **walking skeleton**, o fluxo mais fino ponta a ponta; vault/docs dispensados. `plan-validate.py` avisa (rc inalterado).
   - Mudar a semântica de uma flag/guarda: `Grep` dos testes e chamadores afetados antes da fase TDD e listá-los no plano.
   - Sem código no corpo; `Out of Scope` explícito.
3. **Quality Gate.** `python -I scripts/plan-validate.py <plano>` tem de dar rc 0; depois rever Brief referenciado, assunções críticas ⚠️, rollback, Open Questions. Falha: corrigir antes de apresentar.
4. **Apresentar (≤2 rondas).** ≤5 bullets: objetivo, fases, riscos, fora de âmbito, estimativa. Ronda 3 = abortar e escalar («Plan rejected after 2 iterations»).
   - **Aprovado:** `status: APPROVED`, `approved: <data>`, mover para `plans/_approved/`, executar via DA. `python -I scripts/plan-validate.py <plano> --gates` dá o bloco `gates:` do SP.
   - **Rejeitado:** `status: REJECTED`, razão na nota de sessão, não executar.

## Abortar e escalar

Âmbito pouco claro após 2 rondas; lacunas críticas no Brief; 2 rejeições; fases ou passos estimados muito acima do que o SP prevê; dependências irresolúveis.

## Notas

- Planos nunca se commitam (são de trabalho; o que fica é o SP).
- Código dos projetos em `<code_root>/<projeto>`; execução: skill DA.
- Mapa de ferramentas em `references/plano-template.md`.
