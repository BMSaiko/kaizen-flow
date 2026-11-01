---
name: swot
description: SWOT rápido — modo decisão (go/no-go) ou otimização (pontos de alavanca)
version: 3.0.0
author: user
license: MIT
triggers:
- swot
- swot analysis
- decision frame
- optimization analysis
- leverage points
metadata:
  hermes:
    tags:
    - workflow
    - analysis
    - decision
    category: analysis
    related_skills:
    - brainstorm
    - grill-me
    - michi
changelog:
- '3.0.0: Formato fixo (≤4 linhas por quadrante, 1 recomendação), modos standalone/encadeado; modo otimização movido para references/optimization.md.'
- '2.1.0: Encolhida; modelos e exemplos em references/examples.md.'
- '2.0.0: Modo de otimização fundido no /swot.'
---
# SWOT

Assunto dado após `/swot`. Por defeito modo **Decisão** («devemos fazer isto?»). Se o pedido for melhorar algo existente («está lento», «processo partido») → modo **Otimização**: `references/optimization.md`.

## Modos de uso
- **Standalone:** formato completo abaixo.
- **Encadeado** (`super-prompt` fase 2, sobre o top do `brainstorm`): só o constrangimento dominante e a recomendação, para `## SWOT` do SP.

## Passos
1. **Enquadrar** numa frase: o que se decide e em que contexto.
2. **Quadrantes:** ≤ 4 linhas cada, específicas e com evidência («entregou 2 projetos com esta stack», não «boa equipa»). S e W internos; O e T externos.
3. **Cruzar:** SO (força agarra oportunidade) e WT (fraqueza + ameaça = o que mata).
4. **Recomendar:** 1 recomendação — constrangimento dominante + movimento mais alavancado.

## Formato (fixo)

```
# SWOT: <assunto>

| S | W |
|---|---|
| ... (≤4) | ... (≤4) |
| **O** | **T** |
| ... (≤4) | ... (≤4) |

**SO (fazer):** <1 linha>
**WT (evitar):** <1 linha>
**Recomendação:** <1-2 frases>
```

Parar nos 4 quadrantes: é um quadro de decisão, não um tratado.

## Para o Super Prompt
A Recomendação, numa frase, serve de `--decisao "<recomendação>"` do `sp-new.py`.

## Quando não usar
- Faltam ideias → `brainstorm`. Causa raiz → `five-whys`. Ambiente muda mais depressa que a análise → `ooda-loop`.

Exemplos: `references/examples.md`.
