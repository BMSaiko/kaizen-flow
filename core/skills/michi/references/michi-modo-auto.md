# michi — modo auto (2026-10-21)

`/michi --auto <SP>` ou `modo: auto` no frontmatter do SP. Executa DR→DP→DA→gates→prova→reflect sem perguntas e fecha o SP sozinho. O modo one-shot (SP de `/one-shot`) é este modo com `horas_disponiveis` e commit por fase; não tem regras próprias.

## Proibições (único sítio; SKILL.md e AGENTS.md só apontam para aqui)
- Push de qualquer tipo, `--force`, `reset --hard`, `clean -f`, `git add -A`/`.` (stage sempre explícito).
- Apagar ficheiros fora do SP; exceções: o `COMMIT_*.md` que originou o commit e temporários próprios (scratchpad).
- Ler segredos (`.env*`, `*.key`, `*.pem`, … — regra crítica 8 do AGENTS.md).
- Commitar ou mover para Done com gate ou prova a falhar.
- Alterar `user.name`/`user.email`; `Co-Authored-By` ou atribuição a agentes.

## Pergunta normal → ação auto
| Normal | Auto |
|---|---|
| «go» por fase, `AskUserQuestion` de dúvida | default mais conservador, registado em `## Decisões modo auto` |
| `/sp-handoff` pergunta sim/não; sessão suja pergunta limpar | `--launch --auto` direto |
| Prova em falta: bloquear e perguntar | prova alternativa e «sem prova» no SP |
| Propor commit com `AskUserQuestion` | fecho automático (abaixo) |

## Fecho (só com gates e prova verdes)
1. `sp-move.py <slug> done` (antes do commit).
2. Gerar `COMMIT_*.md` com stage explícito (skill `commit-msg`), executar-o (skill `commit`: commit local, autor the user) e apagar o `COMMIT_*.md`.
3. Repo de código: commit local por fase (assunto ≤72). Nunca push.
4. Se o SP tem filho seguinte: `sp-handoff --launch --auto`.
5. `git rev-parse --abbrev-ref HEAD` = `master` (SB-VERIFY).

## Paragem
Gate/prova falhada após 2 tentativas, ou proibição em causa: não commita, não move para Done, regista em `## Report modo auto` e para. Em one-shot passa à folha independente seguinte.

## Report (`## Report modo auto` no SP + resumo curto no chat)
correu bem · correu mal · corrigido · commits (hash + assunto) · próximo passo.
