---
name: super-prompt
description: Build Super Prompt — chains brainstorm+swot+grill-me+dr
version: 2.0.0
author: Hermes Agent (user)
license: MIT
triggers:
- super-prompt
- super prompt
- /super-prompt
metadata:
  hermes:
    tags:
    - prompt
    - planning
    - michi
    - orchestration
    - super-prompt
    category: workflow
    related_skills:
    - michi
    - brainstorm
    - swot
    - grill-me
    - dr
    - five-whys
    - eisenhower-matrix
    - ooda-loop
changelog:
- '2.0.0: SKILL ≤5 KB; template, frontmatter e flags completas do sp-new.py movidos para references/super-prompt-detalhe.md.'
- '1.2.0: encolhida (changelog antigo no git, texto repetido passado a ligações); regras mantidas.'
- '1.1.0: validateSuperPrompt() no save, --quick, templates de grill por domínio.'
---
# Super Prompt

Constrói um **Super Prompt**: instruções autónomas, prontas a colar, para uma sessão nova (`/michi <conteúdo>`). Funil `brainstorm` → `swot` → `grill-me` → `dr` e montagem. Corre **fora** do ciclo michi; o SP é o artefacto, não a implementação.

## Quando usar / não usar
- Usar: objetivo, bug, refactor, feature ou projeto para outro agente/sessão; autónomo e a frio (sobrevive à fronteira de sessão).
- Não usar: já dentro de um ciclo michi (`/dp` ou `/dr`); tarefa trivial de uma linha; execução já (`/michi <ideia>`).

## Invocação
`/super-prompt <objetivo>` ou `--quick <objetivo ≤3 linhas>` (salta brainstorm e dr; vai a grill-me + DP; secções ≤3 linhas). Sem objetivo: perguntar uma vez e arrancar.

## Pipeline (por ordem; cada fase aperta a seguinte)
1. **brainstorm** — skill `brainstorm` (encadeado): Ideias + Picks para `## Brainstorm`. Sem a skill, 60 s inline; nunca bloquear.
2. **swot** — skill `swot` (encadeado) sobre o top 1: constrangimento dominante + recomendação para `## SWOT`. Mesmo fallback.
3. **grill-me** — skill `grill-me` até objetivo, âmbito, sucesso, constrangimentos e não-objetivos ficarem inequívocos; parar em «ok», «basta», «go»; respostas em `## Spec (grill-me output)`. Objetivo vazio/placeholder: nota de bloqueio e sair. Domínio conhecido: templates em `references/super-prompt-extra.md`. No mesmo lote de perguntas: prioridade, modo (auto/manual), autorizações (commit/push/PR/restrições, uma pergunta), perfil, escalão (`sp-escalao.py`), escopo, gates («como se verifica?») e `--decisao`. **Flag a flag: `references/super-prompt-detalhe.md`.**
4. **dr (mini)** — skill `dr`: o mínimo de caminhos/contexto/integração; ≤1 ecrã, cada afirmação ancorada em fonte primária, em `## DR (mini)`. Não-código: «DR skipped: non-code goal».

## Gerar o SP
1. Só com `python -I scripts/sp-new.py --project <p> --slug <slug> --priority P1|P2|P3 --modo auto|manual [flags]` (nunca criar o ficheiro à mão). Projeto não inferível ou inexistente: `AskUserQuestion`; nunca inventar pasta.
2. Preencher as **8 secções** (template: `super-prompt-detalhe.md`); §4 com critérios verificáveis, §7 com passos concretos, gates executáveis. Secção vazia = voltar ao grill-me; nunca publicar incompleto.
3. Validar: `python -I scripts/sp-validate.py <ficheiro>` sem avisos.

## Reutilizar
Colar o corpo no `/michi`: salta grill+DR, começa no DP e trata as secções 2/3/4/5 como contrato; re-perguntar esses factos = SP incompleto.

## Mais
Templates do grill, helpers e checklist: `references/super-prompt-extra.md`; pitfalls: `references/super-prompt-pitfalls.md`; frontmatter, template e flags: `references/super-prompt-detalhe.md`. Ler a pedido.

## Output ao user (sempre)
```
Super Prompt saved: <abs path>
Sections: 1.Role 2.Context 3.Objective 4.Success 5.Constraints 6.Seams 7.Steps 8.Done-when
Reuse:    /michi <paste body of this file> in a new session
```
Sem commit, push nem DA: o passo seguinte é uma sessão nova com o SP no `/michi`.
