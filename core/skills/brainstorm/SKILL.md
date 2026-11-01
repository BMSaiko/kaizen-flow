---
name: brainstorm
description: 'Brainstorm + SWOT: gerar ideias, depois testá-las. Saída fixa e curta.'
version: 2.0.0
author: user
license: MIT
changelog:
- '2.0.0: Formato fixo (≤10 ideias de 1 linha), modos standalone/encadeado, saída pronta para --decisao.'
- '1: Versão inicial.'
metadata:
  hermes:
    tags:
    - workflow
    - brainstorm
    category: brainstorm
---
# Brainstorm

Tema dado após `/brainstorm`. Gerar, agrupar, filtrar. Sem prosa de enchimento.

## Modos
- **Standalone:** resposta completa no formato abaixo; terminar com os Picks.
- **Encadeado** (`super-prompt` fase 1): só `## Ideias` e `## Picks`, para `## Brainstorm` do SP; o `swot` corre a seguir sobre o top 1.

## Passos
1. **Gerar** 8-10 ideias, sem filtro; 1 linha cada.
2. **Agrupar** em 2-5 temas (só se ajudar).
3. **Filtrar** com um SWOT de 1 linha por ideia candidata (detalhe: `swot`).
4. **Escolher** 1-3 Picks; justificar em 1 linha; dar o Next (menor ação concreta).

## Formato (fixo)

```
# Brainstorm: <tema>

## Ideias
- <ideia> — <1 linha>          (≤ 10)

## Picks
1. <ideia> — <porquê, 1 linha>
   - Next: <ação>
```

Limites: ≤ 10 ideias, ≤ 3 Picks, 1 linha por item.

## Para o Super Prompt
Cada Pick, numa frase, serve de `--decisao "<ideia>: <porquê>"` do `sp-new.py`.

Exemplo e variante com clusters: `references/formato.md`.
