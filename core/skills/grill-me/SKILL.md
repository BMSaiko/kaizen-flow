---
name: grill-me
description: Entrevista implacável para afinar um plano ou design até haver entendimento partilhado; sai com a lista de decisões. Trigger: grill me, grill this, stress test this, afina o plano, fase 1 do michi.
version: 2.0.0
author: Matt Pocock (adapted for Hermes)
license: MIT
platforms:
- linux
- macos
- windows
triggers:
- grill me
- grill-me
- grill this
- stress test this
- stress-test this
metadata:
  hermes:
    tags:
    - interview
    - design
    - plan
    - decision
    - productivity
    category: productivity
---
# Grill-me

Entrevista inline (sem skill separada): mapear o plano como **árvore de decisão**, perguntar por **rondas**, sair com **decisões** prontas para o SP. Casos, cenários, Atlas e pitfalls: `references/casos.md`, `references/atlas.md`.

## 1. Semente (antes da 1ª ronda)

A semente (mensagem do user, descrição do card, bloco do plano) é pré-requisito. Vazia, só espaços, `TBD`, `???`, `...`, `<descreve ...>` ou só o esqueleto do template: **parar**, sem ronda nem bloco Q1/Q2. Uma linha com o bloqueio exato e o que colar (2-5 linhas). No chat: plano na mesma mensagem = semente real, avançar. No Atlas: nota de bloqueio (`references/atlas.md`). Construir perguntas sobre intenção assumida é alucinação com verniz socrático.

## 2. Factos são teus

Antes de perguntar, resolver com `Read`/`Grep`/`Glob`/`Bash`/`WebSearch` o que o código, o vault ou a web dizem. Só vão ao user as **decisões** e o contexto que não observas («tens acesso a X?»). Exploração em curso só atrasa as perguntas a jusante: perguntar já o resto.

## 3. Rondas

- **Fronteira** = decisões cujos pré-requisitos estão fechados. Perguntar a fronteira numa ronda, máx. 4 perguntas (as que mais desbloqueiam); sem fronteira limpa, 1 pergunta só.
- Chat interativo: **uma** chamada `AskUserQuestion` por ronda. `header` ≤12 car.; `question` autossuficiente; 2-4 opções com a recomendada **primeiro** e «(Recommended)»; `description` com a razão; resposta livre via «Other» (nunca criar opção «Outro»). Pergunta aberta: propor 2-3 candidatos concretos. Sem a ferramenta (headless/Atlas): formato de texto de `references/atlas.md`.
- Toda a pergunta leva recomendação. Nunca «o que achas?».
- As respostas remodelam a árvore: recalcular a fronteira. Pergunta que depende de outra ainda aberta nesta ronda pertence à seguinte; pergunta já feita ou fechada: largar.
- Mudança em bloco (rename/refactor/rebrand): a Ronda 1 é o **âmbito** (`references/casos.md`).
- Não propor UI **nova** que o user não pediu: se um campo ou fluxo existente cobre o caso, apontá-lo.
- Mínimo de rondas e `skip grill`: `michi/references/michi-skip-grill-play.md` (skip) e `michi-pitfalls.md` §3; honrar, não reescrever aqui.

## 4. Paragem: «alinhado»

Parar quando a fronteira está vazia **e** estão fechados os cinco pontos: **quê** (resultado), **porquê** (motivo), **forma** (abordagem), **limites** (âmbito, fora de âmbito, invariantes) e **prova** (como se verifica). Sinal do user («ok», «basta», «go») também pára, mas o que ficou aberto vai para `Assunções`. Nada assumido em silêncio; não agir antes de o user confirmar.

## 5. Saída: decisões

Terminar com a lista de decisões, uma linha cada, afirmativas e com o porquê, pronta para colar em `## Decisões` do SP ou para o `sp-new.py --decisao "<texto>"` (repetível; o script gera `- <texto>`):

```
- Flag `--json` em `sp-list.py`: só leitura, sem alterar o formato de texto (retrocompatível)
- Fora de âmbito: ordenação nova; prova: output parseável por `python -m json.tool`
- Assunção: sem dependências novas
```

Sem pergunta pendente na lista; o que ficou por decidir fica como `Assunção:` ou `Fora de âmbito:`.
