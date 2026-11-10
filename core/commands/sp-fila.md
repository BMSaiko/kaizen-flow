---
description: Executar em sequência os SPs elegíveis (modo auto, gates, dependências cumpridas), com limites e relatório final
version: 2.0.0
---
Passos (português europeu). `$ARGUMENTS` = flags de `scripts/sp-fila.py` (`--dry-run`, `--max N`, `--max-falhas N` (para ao fim de N falhas seguidas, defeito 2), `--ate HH:MM`, `--projeto P`, `--concorrencia N` (modo paralelo), `--orcamento N` (teto opcional de requests; sem ele não há limite), `--programa SLUG-MÃE`: só a árvore da mãe, com `orcamento_horas`/`orcamento_usd`/`orcamento_requests` do frontmatter dela; ao parar grava `## Progresso` na mãe).

1. Correr sempre primeiro `python -I scripts/sp-fila.py --dry-run $ARGUMENTS` e mostrar a ordem e os excluídos (modo ≠ auto, sem gates, dependência em falta, ciclo, autorização insuficiente).
2. Se `$ARGUMENTS` tem `--dry-run`, parar aqui.
3. Senão, AskUserQuestion sim/não «Arrancar a fila com estes SPs?» (a fila lança sessões que commitam localmente). Com «sim»: `python -I scripts/sp-fila.py $ARGUMENTS` (em série o script move o primeiro SP para Doing e lança `sp-handoff --launch --auto`).
   **Paralelo (`--concorrencia N`)**: o script move cada SP para Doing, cria a worktree (`sb-worktree.py ensure`) e imprime um plano JSON (`acao: lancar`, `itens` com `slug`, `worktree`, `prompt`, `description`). Por cada item, chamar `Agent` com `prompt` e `description` do item, `run_in_background: true`, modelo de `python -I scripts/modelos.py get michi-exec` e **sem** `isolation: "worktree"` (partiria de `main`); todos os itens na mesma resposta. Depois terminar o turno; não fazer polling.
4. Na notificação de fim de cada subagent, ler a última linha `ESTADO:` (`sp_fila_subagents.estado_final`):
   - `pergunta`: trazer a pergunta ao user com `AskUserQuestion` (cabeçalho «SP <slug>», recomendada primeiro; várias pendentes = um só pedido) e retomar o subagent com `SendMessage` e a resposta; nunca decidir pelo user.
   - `done`: propor ao user o merge (`python -I scripts/sb-worktree.py merge <slug>`, `AskUserQuestion` Sim/Não) e depois `python -I scripts/sp-fila.py --seguinte --slug <slug>`.
   - `bloqueado`/`falhou`/`desconhecido`: avisar o user com o resumo e `python -I scripts/sp-fila.py --seguinte --slug <slug>` (conta como falhado).
   Se o `--seguinte` devolver outro plano, lançar os itens novos como no passo 3. Pedidos de permissão dos subagents aparecem nesta sessão: só o user os aprova. Em série, a sessão michi lançada só reporta `python -I scripts/sp-fila.py --seguinte` e termina o turno; não corre `sp-list`, `sp-handoff --launch` nem `sp-fechar --next`. No fim escreve o relatório em `knowledge/infra/reports/sp-fila/` e apaga o estado.
5. `python -I scripts/sp-fila.py --parar` abandona a fila. A fila para sozinha (e diz o motivo no relatório, ≤ 30 linhas) ao atingir `--max`, `--max-falhas`, `--ate` ou um orçamento; só lança SPs com `modo: auto` + `gates:` e nunca executa o que `sp-new --permitir` recusa.

Reflect: cada sessão michi lançada pela fila corre `/reflect fase <SP>` por fase e `/reflect final <SP>` antes de fechar, sem perguntas (modo auto); as linhas ficam em `## Reflect` do SP e o relatório da fila resume os gaps repetidos.

Regras: em série, um SP por sessão limpa; paralelo só com `--concorrencia N` (N subagents `Agent` em background, máx. 20, uma worktree por SP, merge só pelo agente principal, só SPs sem dependência entre si, merge serializado pelo lock); push/PR só como cada SP autoriza (a fila nunca os faz); SP em Doing que não chega a Done conta como falhado e os dependentes ficam de fora (só continuam os independentes).
