# Fase 2b — Spike (opcional, com timebox)

Corre **só** se o grill marcou `spike: incerto` no frontmatter do SP (viabilidade técnica incerta). Sem o campo, a fase não existe; SPs de vault/docs nunca a usam. `sp-estado.py` mostra a linha `spike: incerto · max_requests N`.

1. **Timebox:** `max_requests` no SP (defeito 15). Ao esgotar, parar e decidir com o que há.
2. **Código descartável:** experimentar fora da worktree do SP (diretório temporário/scratchpad); nada do spike entra no diff nem é commitado.
3. **Saída:** `Spike: GO|NO-GO — <porquê em 1-2 linhas>` em `## Decisões`, mais o que se aprendeu que muda o plano.
4. **GO** segue para o DP; **NO-GO** volta ao Grill (mudar abordagem) ou fecha o SP; decide o user.
5. Remover `spike: incerto` do frontmatter (ou passar a `spike: feito`) ao fechar a fase.
