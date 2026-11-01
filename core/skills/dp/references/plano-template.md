# Template do `_PLAN_*.md` (contrato DP → DA)

Caminho: `knowledge/projects/<projeto>/plans/_draft/_PLAN_YYYYMMDD_HHMMSS.md`. Validar: `python -I scripts/plan-validate.py <plano>`; `--gates` imprime o bloco `gates:` para o SP.

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
{Scope Gate, 2-3 frases}

## Problem Statement
## Context & Analysis
## Assumptions
- {as críticas marcadas ⚠️}

## Phases
### 1. <nome>
- **What:** 1-2 linhas
- **Scope:** caminhos ou sistemas tocados
- **Done when:** critério observável
- **Gate:** `<comando copiável para gates: do SP>`
- **Risco:** <risco> | mitigação: <m> | gatilho: <g>
- **Time-box:** X min
- **Parallel:** [fases independentes]

## Risks
- {top 3, com mitigação e gatilho}

## Out of Scope
## Rollback Plan
## Open Questions
```

Cada fase é um ciclo TDD (Seams → Red → Green → tautologia). Sem código no corpo.

## Anti-padrões
Planear sem Brief do DR; fase sem Done when/Gate; >7 fases (dividir em sub-planos); código no corpo; iteração infinita; ignorar baixa confiança do Brief; saltar o Quality Gate; caminhos hardcoded (`sb_resolve`); assumir paralelismo sem verificar.

## Adaptação Claude Code
`sb_search` → `Grep`/`Glob`; `sb_read` → `Read` (`offset`/`limit`); `sb_resolve` → `Glob **/<nome>.md`; `bash find/grep` proibido; paralelo = chamadas de ferramentas paralelas, nunca `Agent` salvo pedido do user.
