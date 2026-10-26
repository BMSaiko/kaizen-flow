---
description: Executar em sequência os SPs elegíveis (modo auto, gates, dependências cumpridas), com limites e relatório final
---
Passos (português europeu). `$ARGUMENTS` = flags de `scripts/sp-fila.py` (`--dry-run`, `--max N`, `--ate HH:MM`, `--projeto P`, `--orcamento N`, `--programa SLUG-MÃE`: só a árvore da mãe, com `orcamento_horas`/`orcamento_usd`/`orcamento_requests` do frontmatter dela; ao parar grava `## Progresso` na mãe).

1. Correr sempre primeiro `python -I scripts/sp-fila.py --dry-run $ARGUMENTS` e mostrar a ordem e os excluídos (modo ≠ auto, sem gates, dependência em falta, ciclo, autorização insuficiente).
2. Se `$ARGUMENTS` tem `--dry-run`, parar aqui.
3. Senão, AskUserQuestion sim/não «Arrancar a fila com estes SPs?» (a fila lança sessões que commitam localmente). Com «sim»: `python -I scripts/sp-fila.py $ARGUMENTS` (o script move o primeiro SP para Doing e lança `sp-handoff --launch --auto`) e **terminar o turno logo a seguir**, sem mais chamadas.
4. No fecho de cada SP lançado pela fila, a sessão michi corre `python -I scripts/sp-fila.py --seguinte` (regista feito/falhado, respeita os limites, lança o seguinte) e termina o turno. No fim escreve o relatório em `knowledge/infra/reports/sp-fila/` e apaga o estado.
5. `python -I scripts/sp-fila.py --parar` abandona a fila.

Regras: um SP por sessão limpa, sem paralelismo, sem sub-agentes; push/PR só como cada SP autoriza (a fila nunca os faz); SP em Doing que não chega a Done conta como falhado e os dependentes ficam de fora (só continuam os independentes).
