---
name: dp
description: "Use when starting any Deep-Planning (DP) session or COMPLEX task requiring structured planning before execution. Produces _PLAN_*.md with phases, gates, risks and verification criteria."
version: 3.0.0
---
# Deep Planning (DP)

Entre DR e DA. Só decisões, fases, riscos e critérios de verificação, sem código. **Um plano sem gate executável é um desejo.**

| Cenário | Aplicar? |
|---|---|
| COMPLEX (multi-passo, código, arquitetura) / «plan this first» | **OBRIGATÓRIO** |
| STANDARD com solução conhecida | Plano leve (2-3 fases) |
| «just do it» / TRIVIAL | Saltar; registar o bypass na nota de sessão |

## Pré-condição (gate do DR)

Research Brief em `knowledge/projects/<projeto>/research/` não vazio, com baixa confiança convertida em riscos; Scope Gate do DR (Full/Delta/Skipped) registado em `## Executive Summary`. Sem DR: `/dr` primeiro; exceção só com contexto conhecido, e dizer a razão.

## Fluxo

1. **Analyze (≤10 min).** Ler o Brief, não repetir a pesquisa. Problema numa frase, constrangimentos, dependências, MISTAKE_LOG do domínio.
2. **Escrever (≤15 min).** Template e anti-padrões em `references/plano-template.md`. Regras:
   - 2-7 fases (3-7 em DP completo), cada uma um ciclo TDD (Seams → Red → Green → tautologia).
   - Cada fase tem **Done when** (observável), **Gate** (comando copiável para `gates:` do SP) e **Risco** (com mitigação e gatilho).
   - Tabela de auditoria `phase | existe hoje | muda depois | redundant?`; `redundant=yes` sai do plano.
   - Sem código no corpo; `Out of Scope` explícito.
3. **Quality Gate (3 min).** `python -I scripts/plan-validate.py <plano>` tem de dar rc 0; depois rever Brief referenciado, assunções críticas ⚠️, rollback, Open Questions. Falha: corrigir antes de apresentar.
4. **Apresentar (≤2 rondas).** ≤5 bullets: objetivo, fases, riscos, fora de âmbito, estimativa. Ronda 3 = abortar e escalar («Plan rejected after 2 iterations»).
   - **Aprovado:** `status: APPROVED`, `approved: <data>`, mover para `plans/_approved/`, executar via DA. `python -I scripts/plan-validate.py <plano> --gates` dá o bloco `gates:` do SP.
   - **Rejeitado:** `status: REJECTED`, razão na nota de sessão, não executar.

## Abortar e escalar

Âmbito pouco claro após 2 rondas; lacunas críticas no Brief; 2 rejeições; esforço >50% acima do tempo disponível; dependências irresolúveis.

## Notas

- Orçamento ~45 min (`--deep` +15 min por fase). Planos nunca se commitam.
- Código dos projetos em `~\Documents\code\<projeto>`; execução: skill DA.
- Sem sub-agentes (sequencial); mapa de ferramentas em `references/plano-template.md`.
