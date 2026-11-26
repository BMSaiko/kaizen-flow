---
name: preflight
description: Pré-voo de git, worktree e ferramentas antes de correr um SP; lista cada problema com a correção segura. Usar com «/preflight», antes de arrancar ou retomar um SP, ou quando um arranque falha por ramo, worktree suja ou órfão.
version: 1.0.0
---
# preflight

Verifica o ambiente antes de um SP. Script: `kaizen preflight` (`core/scripts/sp-preflight.py`); só lê, a menos que se peça `--fix`. Alvo: menos de 2 s.

## Fluxo

| Passo | Comando | Resultado |
|---|---|---|
| 1. Ler | `kaizen preflight [slug] [--repo DIR] [--ramo B]` | lista problemas, cada um com `EC-NNN`, nível e correção segura |
| 2. Perceber | ler cada `EC-NNN` em `docs/error-log.md#preflight` | causa e próximo passo |
| 3. Corrigir | `kaizen preflight <slug> --fix` | corre as correções seguras uma a uma, **com confirmação por comando** |
| 4. Repetir | passo 1 | rc 0 antes de arrancar |

Opções úteis: `--json` (saída para máquinas), `--sem-orfao` (não contar o próprio SP como órfão; usado pelo `resume`).

## Níveis e códigos de saída

- `erro`: pára um michi em auto. `aviso`: informa.
- rc 0 limpo · rc 1 há problemas · rc 2 uso inválido.

## Correções seguras (as únicas do `--fix`)

`git stash push -u -m <tag>`, `git worktree prune`, `git checkout <ramo>`. Confirmação no terminal; EOF vale como «não».

## Proibições

- Nunca apagar ficheiros, ramos ou worktrees: o preflight não apaga.
- Nunca `--fix` sem mostrar ao {{userName}} cada comando que vai correr.
