---
name: da
description: "Executa um plano DP aprovado passo a passo, com evidência por passo, escalada de falhas por tentativas e rc, checkpoint e rollback. Usar na fase 4 do michi ou numa tarefa complexa."
version: 3.0.0
---
# Deep Acting (DA)

Executa um plano DP aprovado fase a fase. **Sem «feito» sem evidência (RC/output).** Detalhe (checkpoint em ficheiro, retoma, rollback, LFS, anti-padrões, mapa de ferramentas): `references/da-detalhe.md`.

| Cenário | Aplicar? |
|---|---|
| Plano DP aprovado, tarefa COMPLEX avulsa | Sim |
| STANDARD multi-passo | Recomendado |
| TRIVIAL | Não; executar |

## Arranque

1. Plano com `status: APPROVED` e fases com `Done when`/`Gate`/`Risco` (`python -I scripts/plan-validate.py <plano>`, formato do `dp`).
2. Ler do SP `perfil`, `max_tentativas`, `parar_se` (regras em `.claude/skills/michi/references/michi-perfis.md`; não copiar). Sem campos: `normal`.
3. Worktree do SP e `python -I scripts/michi-checkpoint.py save --slug <SP>` **antes de cada fase com escrita**.

## Loop por passo

Anunciar → executar → verificar (reler o ficheiro alterado, menor teste) → `[OK] Step N.M — <o quê> | Evidence: <RC/output>`. Reportar nas fronteiras de fase. Cada fase fecha com o seu `Gate` e um teste de integração que cubra as fases anteriores (sem ele, as falhas entre fases só aparecem no fim), prova (`michi-prova.md`) e `/reflect fase`.

## Falha de gate

`python -I scripts/da-stop.py <SP> --passo N.M --tentativas K --causa "<texto>" --proximo "<texto>"`:

- rc 0: nova tentativa com outra hipótese, registada na `--causa`; repetir o mesmo comando sem mudar nada não conta como tentativa.
- rc 1: **parar**. O relatório fixo `## Paragem DA` (Passo, Tentativas, Causa, Próximo passo) vai para `## Report modo auto` do SP. Reverter: `michi-checkpoint.py restore` (`michi-modo-auto.md` §Paragem). Não commita nem move para Done (`michi-modo-auto.md` §Paragem).

Outros `parar_se` do perfil (ambiguidade, ficheiro fora de escopo, custo) também param, com o mesmo relatório.

## Refresh de contexto

Antes de nova fase, após uma paragem e sempre que o plano possa ter mudado: reler o plano do disco, `git status` e os ficheiros alterados (o contexto é um snapshot).

## Feito quando

Todas as fases `[OK]` com evidência, gates e integração verdes, prova e reflect registados, sem bloqueios abertos, LFS (`references/da-detalhe.md`). Faltando algo: não está feito; reportar o que falta.
