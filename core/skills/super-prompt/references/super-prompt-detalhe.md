# super-prompt — detalhe (a pedido)

## Flags do `sp-new.py` (fonte: `scripts/sp-new.py --help`)

| Flag | Preenche | Pergunta do grill |
|---|---|---|
| `--project`, `--slug`, `--priority P1\|P2\|P3` | frontmatter | prioridade (default P3) |
| `--modo auto\|manual` | `modo:` (michi não repete a pergunta de arranque) | modo do michi (default manual) |
| `--commit`, `--push`, `--pr auto\|pergunta\|nunca` | `commit:`/`push:`/`pr:` | autorizações, uma pergunta agrupada (conservador: `pergunta`; `nunca` para push/PR; valores em `michi-modo-auto.md` §Autorizações do SP) |
| `--restricoes "<texto>"` | `restricoes:` | pastas intocáveis, repos, ações externas |
| `--perfil cauteloso\|normal\|autonomo` + `--max-tentativas/--max-requests/--parar-se` | perfil e limites | recomendado `normal`; `autonomo` só com gates (`michi/references/michi-perfis.md`) |
| `--escopo a/**,b.py`, `--fora-de-escopo x/**` | `escopo:`/`fora_de_escopo:` | derivar de «Relevant files»; sem `escopo` o hook não guarda nada |
| `--gate "<cmd>"` (repetível), `--prova "<cmd>"` | `gates:` (um `- cmd:` por gate), `prova:` | «Como se verifica que está certo?»; propor gates do projeto (`npm test`/`vitest`/lint/build; `scripts/test_*.py`) e confirmar |
| `--permitir "<cmd>"` (repetível) | comandos pré-aprovados | `michi-modo-auto.md` §Autorizações do SP |
| `--decisao "<texto>"` (repetível) | `## Decisões` | decisões do grill, uma por flag |
| `--parent <slug>`, `--depends-on <slug> ...` | `parent:`/`depends_on:` | só em SP filho |
| `--program <slug> --children a,b:a,c:a+b` | SP-mãe (`kind: program`) + filhos | escalão grande/médio; `b:a` = b depende de a |
| `--root` | raiz alternativa | testes |

`sp-validate.py` recusa comandos proibidos (`--force`, `reset --hard`, `git add -A`, `.env*`).

**Escalão:** `python -I scripts/sp-escalao.py` propõe (pequena = 1 SP; média = pai+filhos; grande = árvore); override numa linha; critérios no playbook `kaizen-flow` §Escalões.

## Template das 8 secções (contrato)

`sp-new.py` cria-as vazias; todas obrigatórias, secção vazia = voltar ao grill-me nessa secção.

```markdown
# Super Prompt - <slug> (<YYYY-MM-DD>)

## 1. Role
You are <role>. You operate with <constraints on style, scope, decision authority>.
## 2. Context
- Project / Repo / State (branch, last commit, key facts) / Relevant files
## 3. Objective (single sentence)
<One sentence. Se não cabe numa frase, restart grill-me.>
## 4. Success criteria (verifiable)
- [ ] <observable thing>
## 5. Constraints / invariants
- Must keep / Must avoid / Performance, size, scope limits
## 6. Seams (public interfaces to test / change)
- `<Module.func>` — <hoje, o que muda>
## 7. Steps (numbered, ordered)
1. <concrete action, file path or command>
## 8. Done-when
<The single observable signal. No "looks good".>
```

## Frontmatter

```yaml
status: TODO          # TODO | Doing | Done
created: <ISO8601>    # igual a updated na criação
updated: <ISO8601>
phase: SP
slug: <slug>
date: <YYYY-MM-DD>
project: <project>
priority: P2
modo: manual          # auto | manual
commit: pergunta      # auto | pergunta | nunca (idem push, pr); restricoes: opcional
perfil: normal        # opcional
```

## Reutilizar numa sessão nova

Colar o corpo (ou passar como objetivo do `/michi`). A sessão nova salta grill + DR, começa no DP (ou DA se pedido) e trata as secções 1-8 como contrato (desvios só com sinal explícito). **Não pode re-perguntar factos das secções 2/3/4/5**: se o fizer, o SP estava incompleto (registar no post-mortem).

## Onde guardar

`sp-new.py` devolve `knowledge/projects/kaizen/<projeto>/sp/TODO/<slug>-<YYYY-MM-DD>.md`. `<slug>`: minúsculas ascii, hífens, ≤48 caracteres. SPs fora do padrão: `python -I scripts/sp-organize.py` (dry-run; `--apply` só com aprovação).
