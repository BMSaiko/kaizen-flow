---
name: review-ciclo
description: Fase de review com ciclo corrigir e rever até aprovação, com limite de iterações e escalada ao user
version: 1.1.0
---
# review-ciclo

Depois do `pentest`, antes do PR. Um agente de review (só leitura, critérios da skill `code-review`) lista achados em ficheiro, uma linha cada: `[bloqueante|menor] ficheiro:linha descrição | verificar: como confirmar a correção` (o `verificar` é o comando ou passo que prova o conserto). Usar a checklist do tipo da mudança (`--checklist codigo|ui|docs`). Depois:

`python -I scripts/review_ciclo.py <estado.json> --achados <ficheiro> [--max 3] [--ficheiros F... --raiz <dir>] [--checklist codigo|ui|docs] [--criar-sps --project <p>]`

| Veredicto | rc | Que fazer |
|---|---|---|
| APROVADO | 0 | sem bloqueantes: segue para PR |
| CORRIGIR | 1 | com `--criar-sps` cria um SP P1 por bloqueante; executar com prova e repetir o review |
| ESCALAR | 2 | limite de iterações (defeito 3) com bloqueantes: parar e pedir decisão ao user |

Critérios: bloqueante = bug, regressão, falha de segurança ou teste em falta; menor = estilo e nomes (não bloqueia). Re-review incremental: com `--ficheiros` o estado guarda o hash de cada um e a saída «Rever só: …» lista apenas os alterados desde a iteração anterior. A saída termina com a tabela de iterações (bloqueantes, menores, a rever) para colar no report. O estado (`iteracao`, `historico`, `veredicto`) fica em `<estado.json>`; apagá-lo recomeça o ciclo. `skip review` salta a fase (decisão do user).

Testes: `python scripts/test_review_ciclo.py`.
