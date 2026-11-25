---
description: Correr a factory de um projeto (VISION.md até ao merge, com orçamento e gates), ver o estado ou parar
version: 1.0.0
---
Passos (português europeu). `$ARGUMENTS` = `run|status|stop|step|approve|pause|resume|skip|takeover <projeto>` (+ `--visao`, `--repo`, `--release-feito`, `--manual`, `--so`, `<sp>`).

1. `status`: `kaizen factory status <projeto>` e relato ≤3 linhas (marco, fila, gasto, próxima paragem).
2. `stop`: `kaizen factory stop <projeto>` (pausa limpa no fim da volta em curso).
3. `run`: ler o `VISION.md` com `kaizen vision resumo`; se não validar, parar e dizer o que falta. Senão `kaizen factory run <projeto>`: decompõe se faltar backlog, lança a fila, vigia gates, PR e merge (só com CI verde, via `pr_fechar`), corre o reflect por marco.
4. rc 3 = pausa: `orcamento` (subir o teto), `gate-bloqueado` (corrigir), `release` (humano faz o release; depois `run --release-feito`), `visao-invalida`, `parado`. Nunca tag nem publish.
5. Modo manual (receitas em `docs/factory-manual.md`): `run --manual` pára em `aguarda-aprovacao`; `approve [--so a,b]` liberta; `step` corre um SP e pára; `pause|resume|skip|takeover <sp>`. Gates e orçamento mantêm-se.

Uma factory por projeto (lock); retoma sozinha após crash. Detalhe: `scripts/kf_factory.py`.
