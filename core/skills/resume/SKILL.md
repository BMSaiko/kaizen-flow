---
name: resume
description: Retoma um SP interrompido a partir do journal e do checkpoint (órfão, pausa por quota, sessão perdida). Usar com «/resume», quando um SP ficou em Doing sem painel vivo ou depois de um erro de sessão.
version: 1.0.0
---
# resume

Retoma um SP onde parou, sem refazer fases já provadas. Script: `kaizen resume` (`core/scripts/sp-resume.py`); estado em `.kaizen/estado/<slug>.json` e `.journal.jsonl`.

## Fluxo

| Passo | Comando | Resultado |
|---|---|---|
| 1. Escolher | `kaizen resume` (sem slug) | um só órfão: é esse; vários: lista e rc 2, escolher e repetir com o slug |
| 2. Retomar | `kaizen resume <slug>` | lê o journal, corre o preflight (só avisos) e continua na fase seguinte à última concluída |
| 3. Forçar fase | `kaizen resume <slug> --from <fase>` | recomeça nessa fase (`grill dr dp da gates pentest review docs pr report reflect commit`) |
| 4. Recomeçar | `kaizen resume <slug> --restart` | arquiva o estado e volta ao grill; **só com confirmação do {{userName}}** |

## Códigos de saída

- rc 0: retomado, ou nada a retomar.
- rc 1: recusado. Causas: lock vivo noutro painel (EC-043), pausa por quota antes de `retoma_em` (EC-016/017), `--restart` sem confirmação.
- rc 2: uso inválido (slug ou fase desconhecidos, `--restart` com `--from`, vários órfãos sem slug).

## Regras

- Segundo painel no mesmo SP é recusado de propósito: esperar, ou `--unlock` só se o painel já não existe.
- Pausa por quota: esperar por `retoma_em`; nunca contornar.
- Sem estado (EC-050): não há o que retomar, arrancar o SP do início.
- `--restart` apaga o ponto de retoma (arquiva): perguntar antes, nunca por defeito.

## Proibições

- Nunca `--restart` nem `--sim` sem o «sim» explícito do {{userName}}.
- Nunca editar à mão o journal nem o checkpoint.
