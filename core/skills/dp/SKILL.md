---
name: dp
description: "Use when starting any Deep-Planning (DP) session or COMPLEX task requiring structured planning before execution. Produces _PLAN_*.md with phases, risks, verification criteria, and time-boxed deliverables."
version: 2.2.0
---
# Deep Planning (DP)

> Adaptado de obra/superpowers para pi coding agent + the agent.

Fase de planeamento entre Deep-Research (DR) e Deep-Acting (DA). Aqui não se escreve código, só decisões, fases, riscos e critérios de verificação: o plano é o contrato entre pesquisa e execução. **Um plano sem critérios de verificação é um desejo, não um plano.**

| Cenário | Aplicar? |
|---|---|
| COMPLEX (multi-passo, código, debugging, arquitetura) | **OBRIGATÓRIO** |
| «plan this first» | **OBRIGATÓRIO** |
| «just do it» | Saltar; registar o bypass na nota de sessão |
| STANDARD com solução conhecida | Recomendado (plano leve) |
| TRIVIAL one-liner | Nunca; executar |

## Pré-condição: gate de conclusão do DR

Antes do DP: (1) o Research Brief existe em `knowledge/projects/<projeto>/research/YYYY-MM-DD-<tópico>-brief.md`; (2) não está vazio (secções preenchidas ou lacunas documentadas); (3) a Confidence Assessment foi revista e as secções de baixa confiança viram riscos; (4) a decisão do Scope Gate (Full/Delta/Skipped) está registada. Sem DR: correr a skill `deep-research` primeiro. Exceção: contexto totalmente conhecido (mesma tarefa há minutos, trivial): documentar a razão e seguir.

Fluxo: TRIVIAL → executar (registar bypass). COMPLEX → gate do DR → Analyze → Plan → Quality Gate → Present & Iterate (máx. 2 rondas) → aprovado: DA; rejeitado: voltar ao Analyze ou abortar.

## Fase 0 — Scope Gate

| Decisão | Condição | Ação |
|---|---|---|
| **Saltar** | TRIVIAL, contexto conhecido, one-liner | Executar, registar bypass |
| **Delta-only** | Mesma tarefa <24 h, contexto conhecido | Plano leve (2-3 fases) |
| **DP completo** | COMPLEX, contexto novo, multi-sistema | Plano de 7 fases |

Registar em `## Executive Summary` do plano.

## Fase 1 — Analyze (máx. 10 min)

Ler o Brief; **não repetir a pesquisa**. (1) Reformular o problema numa frase; (2) constrangimentos (técnicos, temporais, recursos); (3) atores afetados; (4) dependências prévias; (5) secções de baixa confiança do Brief → riscos; (6) completar o Brief só se houver lacunas; (7) MISTAKE_LOG do domínio. Sem tempo: seguir com o que há e sinalizar a pressão como risco.

## Fase 2 — Escrever o plano (máx. 15 min)

Em `knowledge/projects/<projeto>/plans/_draft/_PLAN_YYYYMMDD_HHMMSS.md` com `status: DRAFT`:

```markdown
---
status: DRAFT
project: <name>
scope-gate: Full/Delta/Skipped
research-brief: <path-to-brief>
created: YYYY-MM-DDTHH:MM:SS
---

# Plan: <goal>

## Executive Summary
{Scope Gate, 2-3 frases sobre a abordagem}

## Problem Statement
{reformulado na Fase 1}

## Context & Analysis
{Brief referenciado; constrangimentos, atores, dependências}

## Assumptions
- {explícitas; as de que o plano depende marcadas ⚠️}

## Phases
### 1. <nome>
- **What:** 1-2 linhas
- **Scope:** caminhos ou sistemas tocados
- **Done when:** critério observável/testável
- **Time-box:** X min máx.
- **Parallel:** [fases independentes que correm em simultâneo]

## Risks
- {top 3, cada um com mitigação e condição-gatilho}

## Out of Scope
- {exclusões explícitas; âmbito preguiçoso mata planos}

## Verification Criteria
- {testes de aceitação por fase}

## Rollback Plan
- {como desfazer cada fase}

## Open Questions
- {o que ficou por resolver: endereçar ou aceitar como risco}
```

Regras: **3-7 fases** (mínimo 2; mais = dividir ou simplificar); toda a fase com «Done when» e time-box; **sem código** no corpo (a implementação vive no `/da`); todo o risco com mitigação E gatilho; flags de paralelismo só em fases realmente independentes.

## Fase 3 — Quality Gate (autorevisão, 3 min)

Antes de apresentar: Brief referenciado (caminho certo, ficheiro existe); todas as fases com «Done when» e time-box; riscos com mitigação + gatilho; Out of Scope explícito; assunções declaradas (as críticas marcadas); critérios de verificação por fase; rollback; sem código; Scope Gate registado; Open Questions listadas (ou «None — all resolved»); fases paralelas assinaladas. **Qualquer falha: corrigir antes de apresentar, sem exceções.**

## Fase 4 — Apresentar e iterar (máx. 2 rondas)

Resumo conciso (≤5 bullets: objetivo, fases, riscos-chave, fora de âmbito, estimativa). Ronda 1: o user ajusta âmbito/fases/riscos → atualizar e reapresentar. Ronda 2: só ajustes finais. **Ronda 3: abortar** (o plano não converge; escalar ao user) e registar na nota de sessão «Plan rejected after 2 iterations».
- **Aprovado:** `status: APPROVED`, mover para `plans/_approved/`, registar `approved: YYYY-MM-DDTHH:MM:SS`, executar via **DA**.
- **Rejeitado:** `status: REJECTED`, registar a razão na nota de sessão, **não executar**, reportar ao user; opcionalmente sugerir novo `deep-research` se as assunções de base estavam erradas.

## Orçamento de tempo

Analyze 10 min · Plan 15 · Quality Gate 3 · Present 5 por ronda (máx. 2) · **~45 min**; `--deep` soma +15 min por fase.

## Critérios de abortar

Parar e escalar quando: âmbito fundamentalmente pouco claro após 2 rondas de clarificação; lacunas críticas no Brief que bloqueiam; 2 rejeições; esforço estimado excede o tempo disponível em >50%; dependências desconhecidas e irresolúveis.

## Anti-padrões

Planear sem Brief do DR (correr `deep-research`); fase sem «Done when» (acrescentar critério); >7 fases (consolidar ou dividir em sub-planos); código no corpo (vai para o DA); iteração infinita (máx. 2 rondas, depois abortar); ignorar secções de baixa confiança (riscos); saltar o Quality Gate; caminhos hardcoded (`sb_resolve`); fases sem time-box; assumir paralelismo sem verificar.

## Observabilidade

- [ ] Brief validado (pré-condição) e Scope Gate registado
- [ ] Plano em `plans/_draft/` referencia o caminho do Brief; Quality Gate passou em todos os itens
- [ ] `status: APPROVED` antes de executar; iterações ≤2
- [ ] MISTAKE_LOG verificado via DR; time-box em todas as fases; fases paralelas assinaladas

## Referência rápida

Planos em `plans/_draft/_PLAN_*.md`, aprovados em `plans/_approved/`; código em `~\Documents\projetcs\<projeto>\`; execução: skill DA; ~45 min no total; **planos nunca se commitam**.

## Adaptação Claude Code (the agent)

Ferramentas Pi → Claude Code. Sem sub-agentes (sequencial; ver CLAUDE.md).

| Pi | Claude Code |
|----|-------------|
| `sb_search` | `Grep` (conteúdo) / `Glob` (nomes) |
| `sb_read` | `Read` (usar `offset`/`limit`) |
| `sb_list` | `Glob` (ordenar por data) |
| `sb_resolve` | `Glob` por `**/<nome>.md` (wikilink → caminho) |
| `bash` + `find`/`grep` | Proibido; usar `Glob`/`Grep` |
| `subagents` / paralelo | Chamadas de ferramentas paralelas na mesma resposta; nunca `Agent` salvo pedido do user |
| `sync_daily_notes` | Ler/editar a daily note à mão |
