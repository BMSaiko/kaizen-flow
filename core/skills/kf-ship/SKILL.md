---
name: kf-ship
description: Leva o ramo atual até ao merge: abre ou reutiliza o PR com o contexto de desenvolvimento do projeto, corre o ciclo `/auditar`, garante que os testes do {{userName}} não foram enfraquecidos, vigia o CI e faz merge só com verde e o método a permitir. Usar com «/kf-ship» quando o código está pronto para entregar.
version: 1.0.0
---
# kf-ship

Os testes são o contrato: o {{userName}} escreve os testes, o agente faz o código passar. Orquestra skills e scripts existentes; não reimplementa nenhum.

## Pré-condições

- Ramo de trabalho (nunca o `ramo_principal`, `main` ou `master`): no principal, parar e dizer porquê.
- Método do projeto em `kaizen.config.json` → `desenvolvimento`. Só `worktree-pr` permite merge autónomo (`pr_merge: auto-se-verde`); `direto`, `worktree-merge` ou sem método = abrir o PR e reportar `bloqueado: método não permite merge`.
- Árvore limpa (commits feitos pelo fluxo normal, sem atribuição a agentes).

## Fluxo

1. **Contrato**: `python -I scripts/kf_ship_testes_guard.py <base>..HEAD --repo <repo>` (base = `origin/<ramo_principal>`). rc 1 = teste apagado ou com menos asserts: repor os testes e corrigir o código, nunca o contrário; rc 3 = sem testes: parar e pedir testes ao {{userName}}.
2. **Gates locais**: os testes do projeto (`npm test`, `pytest`, …) verdes antes do push.
3. **Review**: `/auditar` e o ciclo (`auditar.py ciclo`) até APROVADO (ESCALAR = parar e perguntar). Cada correção volta ao passo 1.
4. **PR**: se o ramo já tem PR (`gh pr view --json number`), reutilizar; senão `/pr-fase` (respeita `pr:` e a template). Base = `ramo_principal` do método.
5. **Vigia e merge**: `python -I scripts/pr_fechar.py <nº> --repo <repo>` (vigia com `pr_watch.py` e faz merge só com checks verdes e permissão do método; nunca `--admin`, nunca force).
6. **Report** numa linha por desfecho:

| rc `pr_fechar` | Desfecho | Próximo passo |
|---|---|---|
| 0 | merged | limpar o ramo/worktree |
| 10 | pronto, sem permissão de merge | pedir merge ao {{userName}} |
| 11 | bloqueado (checks vermelhos, review pedida, fechado) | corrigir e repetir do passo 1 |
| 12 | conflito | rebase sobre a base e repetir do passo 1 |
| 3, 4 | vigia parou | relançar o passo 5 |

Merge negado pelo harness (classificador do modo auto ou permissão recusada), mesmo com `merge: auto` e rc 0 esperado: tratar como rc 10, pedir o «sim» do {{userName}} e só então repetir o passo 5; nunca contornar a negação.

## Proibições

- Nunca alterar branch protection, nunca `--admin`, nunca force push.
- Nunca editar testes existentes para remover asserts ou apagar testes (a guarda falha).
- Nunca `Co-Authored-By` nem «Generated with» em commits ou PRs.

Testes: `python -m pytest scripts/test_kf_ship_testes_guard.py scripts/test_pr_fechar.py -q`.
