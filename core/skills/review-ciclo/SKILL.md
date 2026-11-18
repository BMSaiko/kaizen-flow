---
name: review-ciclo
description: Revê o diff em ciclo corrigir e rever até aprovação, com limite de iterações e escalada ao user. Usar na fase 7 do michi, depois do pentest.
version: 1.2.0
---
# review-ciclo

Depois do `pentest`, antes do PR. Quem implementou não se revê: um painel `revisor` (só leitura, modelo ≠ executor, critérios de `code-review`) escreve os achados, uma linha cada: `[bloqueante|menor] ficheiro:linha descrição | verificar: como confirmar`.

1. `python -I scripts/sp-revisor.py --sp <SP> --base <ref> --achados <f> [--checklist codigo|ui|docs] [--rever-so F...]`
2. `sp-revisor.py --sp <SP> --esperar [--timeout 900]` (rc 0 done, 1 falhou, 2 sem vaga; 3 timeout, a mensagem traz o último estado: reesperar uma vez, depois `--inline` e registar «review não independente» em `## Review` e no Report)
3. `python -I scripts/review_ciclo.py <estado.json> --achados <f> [--max 3] [--ficheiros F... --raiz <d>] [--criar-sps --project <p>]`

`--inline` (automático com `michi_modelo: simples` ou sem painéis): review na própria sessão, registar no Report «review não independente».

| Veredicto | rc | Que fazer |
|---|---|---|
| APROVADO | 0 | segue para PR |
| CORRIGIR | 1 | `--criar-sps` cria um SP P1 por bloqueante; o executor corrige e repete |
| ESCALAR | 2 | limite de iterações com bloqueantes: pedir decisão ao {{userName}} |

Bloqueante = bug, regressão, falha de segurança ou teste em falta; menor = estilo (não bloqueia). O revisor nunca corrige nem commita. Re-review: «Rever só: …» da saída vai para `--rever-so`. O estado fica em `<estado.json>`; apagá-lo recomeça. `skip review` = decisão do {{userName}}.

Testes: `python -m pytest scripts/test_sp_revisor.py scripts/test_review_ciclo.py -q`.
