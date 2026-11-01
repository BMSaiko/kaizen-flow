# SWOT — modo Otimização (pontos de alavanca)

Pergunta: «como melhorar isto?». Saída com pontuação, análise cruzada e alvos ordenados, com evidência.

1. **Âmbito** — uma frase específica («o fluxo de auth em `packages/server/auth/`», não «o backend»).
2. **Investigar, não adivinhar** — `Read` código/config/docs, `Grep`/`Glob` por TODO, FIXME e padrões de erro, logs, métricas, git history. Cada item tem ≥ 1 evidência (ficheiro, log, métrica).
3. **Quadrantes** (3-5 itens): S o que funciona e é reutilizável; W onde se perde energia; O o que o investimento certo melhora; T o que é frágil ou pode descarrilar.
4. **Pontuar** cada item: Impact (1-5) e Effort (1 trivial … 5 refactor grande). Prioridade = Impact / Effort.
5. **Cruzar:** SO (Atacar), WO (Corrigir: a fraqueza que bloqueia a maior oportunidade), ST (Proteger), WT (Sobreviver: corrigir já).
6. **Priorizar** as células cruzadas; os 2 primeiros são os alvos.
7. **Veredito** — «O maior ponto de alavanca é X porque Y (score Z/5).» Próximo passo: `eisenhower-matrix` ou `/dp`.

Saída: `# SWOT Optimization: <âmbito>`, 2x2 pontuado (`S1: <item> (Impact: 4, Effort: 2)`), `## Cross-Analysis` (4 células), `## Prioritized Targets`, `**Verdict:**`.

## Porta de verificação
Completo só se: todos os itens têm evidência e as duas pontuações; as 4 células cruzadas têm achado concreto; o veredito diz o ponto de alavanca com score; ≥ 1 alvo mapeia para uma ação concreta.

Modelos completos e exemplos: `examples.md`.
