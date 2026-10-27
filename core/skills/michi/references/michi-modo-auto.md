# michi — modo auto (2026-10-21)

`/michi --auto <SP>` ou `modo: auto` no frontmatter do SP. Executa DR→DP→DA→gates→prova→reflect sem perguntas e fecha o SP sozinho.

## Proibições (único sítio; SKILL.md e AGENTS.md só apontam para aqui)
- `--force`, `reset --hard`, `clean -f`, `git add -A`/`.` (stage sempre explícito).
- Push e PR só se o SP os autorizar (`push: auto` / `pr: auto`, ver «Autorizações do SP»); sem o campo, nunca.
- Apagar ficheiros fora do SP; exceções: o `COMMIT_*.md` que originou o commit e temporários próprios (scratchpad).
- Ler segredos (`.env*`, `*.key`, `*.pem`, … — regra crítica 8 do AGENTS.md).
- Commitar ou mover para Done com gate ou prova a falhar.
- Alterar `user.name`/`user.email`; `Co-Authored-By` ou atribuição a agentes.

## Autorizações do SP (único sítio)
Frontmatter `commit`, `push`, `pr` (`auto|pergunta|nunca`) e `restricoes` (texto), gravados pelo `/super-prompt` (`sp-new.py --commit/--push/--pr/--restricoes`) e validados por `sp-validate.py` (push `auto` exige commit ≠ `nunca`; pr `auto` exige push `auto`). Valem no fecho em modo auto **e** manual:
| Valor | Fecho |
|---|---|
| `auto` | commit local (skill `commit`) · push (skill `push`, sem force) · PR via `gh` sem atribuição, sem perguntar |
| `pergunta` | `AskUserQuestion` como no fluxo normal |
| `nunca` | nem propõe |
- Sem campo (SP antigo): `pergunta`; em modo auto, commit local sem push nem PR.
- `permitir` (allowlist, `;`-separada, `sp-new.py --permitir` repetível) e `## Decisões` (`--decisao`, decisões do grill): **consultar antes de perguntar**. Comando em `permitir` corre sem pedir; o resto pergunta. `kaizen_engine.precisa_perguntar(fm, acao)` decide (acao = `commit|push|pr` ou o comando). Irreversíveis (`--force`, `reset --hard`, `git add -A`, segredos) perguntam sempre e `sp-validate.py`/`sp-new.py` recusam-nos em `permitir`. Decisão já em `## Decisões`: não repetir a pergunta.
- `restricoes` é lido no arranque e cumprido à letra (pastas intocáveis, repos, ações externas); em dúvida, o mais conservador.

## Pergunta normal → ação auto
| Normal | Auto |
|---|---|
| «go» por fase, `AskUserQuestion` de dúvida | default mais conservador, registado em `## Decisões modo auto` |
| `/sp-handoff` pergunta sim/não; sessão suja pergunta limpar | `--launch --auto` direto |
| Prova em falta: bloquear e perguntar | prova alternativa e «sem prova» no SP |
| Propor commit com `AskUserQuestion` | fecho automático (abaixo) |

## Fecho (só com gates e prova verdes)
1. `sp-move.py <slug> done` (antes do commit).
2. Se `commit` ≠ `nunca`: gerar `COMMIT_*.md` com stage explícito (skill `commit-msg`), executar-o (skill `commit`: commit local, autor the user) e apagar o `COMMIT_*.md`.
3. Repo de código: commit local por fase (assunto ≤72). Push/PR só conforme «Autorizações do SP».
4. **Continuar sozinho, nunca parar para perguntar «sigo?»** (2026-10-25): fechado um SP em auto, `sp-list.py --status todo` e executar já o próximo elegível (dependências em Done), até não haver nenhum; a mãe com todos os filhos Done fecha também. Parar só por paragem/gate falhado. Se o SP tem filho seguinte: `sp-handoff --launch --auto`. Se corre numa fila (`~/.claude/sp-fila-estado.json` existe): `sp-fila.py --seguinte` (`.claude/commands/sp-fila.md`); também na paragem, para registar o falhado.
5. `git rev-parse --abbrev-ref HEAD` = `master` (SB-VERIFY).

## Paragem
Gate/prova falhada após 2 tentativas, ou proibição em causa: não commita, não move para Done, regista em `## Report modo auto` reverte ao checkpoint e para.
Checkpoint: antes da DA (ou de fase com escrita) `python -I scripts/michi-checkpoint.py save --slug <SP>`. Na paragem: `restore --slug <SP>` mostra o plano; em auto, `--apply` e regista a reversão no Report; em manual, `AskUserQuestion` antes de `--apply` (recusa se o HEAD mudou).

## Report (`## Report modo auto` no SP + resumo curto no chat)
correu bem · correu mal · corrigido · commits (hash + assunto) · próximo passo.

## Pergunta de arranque (único sítio da regra)
Em ciclo novo (`/michi <SP|ideia>`), decidir por esta ordem; a primeira que se aplica ganha:
1. `--auto` explícito → auto, sem pergunta (inclui relançamentos `sp-handoff --launch --auto` e `[context-guard]`).
2. `modo: auto` no frontmatter do SP → auto, sem pergunta; `modo: manual` → sem auto, sem pergunta (definido pelo `/super-prompt`/`sp-new --modo`). Sem o campo: segue para 3-5.
3. `help`, `skip <fase>`, `go to DA` → sem pergunta (não é arranque de ciclo).
4. SP em Doing com modo já registado (`## Decisões modo auto` ou `## Progresso`) → retomar nesse modo, sem repetir.
5. Caso contrário: `AskUserQuestion` «Como corre este ciclo?» com «Sem auto (interativo) (Recomendado)» (default) e «Com auto (`--auto`)»; a resposta vale para o ciclo todo.

Sessão suja: um só `AskUserQuestion` com 2 perguntas (limpar sessão sim/não + modo). Se limpar, o relançamento leva `--auto` só quando o modo escolhido for auto; sem auto, a sessão nova repete só a pergunta do modo (sessão limpa, uma ronda).
