# michi — orquestração (detalhe movido do SKILL.md em 2.6)

Regras que saíram do `SKILL.md` sem alteração de contrato. Prova, reflect por fase e modo auto: `michi-prova.md`, skill `reflect`, `michi-modo-auto.md` (uma só fonte cada).

## Kaizen hooks

`kaizen-hooks.json` (ref. `knowledge/infra/reference/kaizen-hooks.md`): em cada início/fim de fase, gate falhado, commit e fecho correr `python -I scripts/kaizen_hooks.py fire michi.<phase.start|phase.end|gate.failed|commit|closed> --slug <SP> --project <p>`. rc≠0 de hook bloqueante = parar e reportar. Sem config é no-op.

## Arranque

- **Estado:** `python -I scripts/sp-estado.py <SP>` (≤30 linhas) em vez de ler SP, lista e git à parte. Aceita o slug (não o caminho).
- **Perfil:** ler `perfil`/`max_tentativas`/`parar_se` no arranque e na paragem (`michi-perfis.md`).
- **Worktree:** `python -I scripts/sb-worktree.py ensure <slug>` e editar pelo caminho absoluto da worktree (o guard bloqueia o checkout principal); `sp-move`/`sp-fechar` saltam sozinhos para ela; commits por fase lá; `merge` (recusa SP fora de Done, `--force` explícito) + `clean` só no fecho.
- **Tab:** `python -I scripts/tab-title.py <slug>` (best-effort, rc 0; imprime `/rename <slug>`). Vale para a sessão nova do `/sp-handoff`.
- **Checkpoint/rollback:** `scripts/michi-checkpoint.py save|restore` antes da DA e na paragem por gate (`michi-modo-auto.md` §Paragem).
- **Sessão suja:** se o contexto já tem conversa anterior (não veio de `/clear` nem de handoff), um só AskUserQuestion: «Limpar e iniciar o SP em sessão nova?» + modo; com «sim», `python -I scripts/sp-handoff.py --launch <caminho>` (`--auto` se escolhido) e terminar o turno. Conta como suja qualquer sessão onde já correu trabalho (SP criado ou `/michi` anterior). SP com secções vazias (sem objetivo/passos) não é «nada a fazer»: entra no Grill (fase 1), nunca parar nem saltar o Arranque (passos 2-5, incluindo esta verificação).
- O user pode parar após qualquer passo (`/stop`) e retomar (`/resume` ou novo `/michi` no mesmo contexto).

## Fase 1 — Grill

`/grill-me <projeto + ideia>` até alinhar o quê, porquê e forma. DR corre antes do grill por defeito. **Super Prompt de 8 secções como input: saltar fases 1-2 e começar no DP (ou DA se pedido), sem repetir factos das secções 2/3/4/5.** Detalhe: `michi-fases-detalhe.md` §Fase 1.

## Fase 2 — DR

`/dr <projeto> <área tocada>`: caminhos de código reais, restrições, prior art, pontos de integração; fontes primárias (ficheiros do repo, docs oficiais). Fim: síntese de 1 ecrã — onde a mudança cai, o que tem de respeitar, o que é arriscado.

## Fase 3 — DP

`/dp <objetivo + achados do DR>`: assunções, 3-7 fases (o quê / âmbito / done-when), riscos, fora de âmbito; cada fase é um ciclo TDD (Seams confirmados → Red → Green → tautology check; refactor fica na review). **Antes do sign-off: tabela de auditoria por fase `phase | existe hoje | muda depois | redundant?` (redundant=yes sai do plano) e pattern-fit check (`michi-patterns.md`).** Detalhe: `michi-fases-detalhe.md` §Fase 3.

## Fase 4 — DA

`/da <plano assinado>`: fase a fase pelo plano TDD, bloqueios cedo, `todo` para acompanhar. Sem «done» sem evidência (RC, output de teste, lint). Por fase de entrega: prova (`michi-prova.md`) e `/reflect fase <SP>` antes do handoff.

## Fase 5 — Gates

Build/tests/lint/typecheck/e2e aplicáveis; cada comando e RC vão para o report; falha = corrigir a causa e repetir todos, sem `|| true`. Ordem: gates → `/harden` → `/pentest` → `/review-ciclo` (`michi-gates.md`). SP com `gates:`: `python -I scripts/sp-gates.py <SP>` (rc≠0 = não fecha). **Fecho num só passo:** `python -I scripts/sp-fechar.py <slug> [--next]` = gates + context-budget + `done` + `COMMIT_*.md` (pára sem mover se falhar). Antes de `sp-move.py ... done` e do `COMMIT_*.md`: prova de done como cliente final, em `## Prova de done` (se falhar, o SP não passa a Done); E2E de fecho de árvore só quando este SP fecha mãe+filhos+netos (`sp-list.py --tree-closed <slug>`). Detalhe: `michi-fases-detalhe.md` §Fase 5.

## Contexto (context-guard)

Se aparecer `[context-guard] Contexto … >= limite`: acabar o passo em curso (nunca a meio de uma edição ou teste) e correr em modo automático (`--launch --auto`, sem perguntar) o handoff que o aviso nomear: `/sp-handoff` se a sessão correu `/michi <SP>`, `/handoff` se é conversa livre.

| Gatilho | Modo | Regras |
|---|---|---|
| Fim de fase com verificação verde, SP em Doing | `/sp-handoff` manual: regista `## Progresso`, pergunta sim/não | um por fase, não por passo; nunca a meio de edição/teste; não repetir se o guard já o fez nessa fase |
| `[context-guard]` ≥ limite | `--launch --auto`, sem perguntar | acabar o passo em curso primeiro |
| Modo auto (`--auto`) | `--launch --auto` por fase | sem `AskUserQuestion` |
| Sem SP em Doing | nada (`/handoff` só em conversa livre) | |
| `/michi` com contexto ≥ 40K (`CLAUDE_MICHI_START_LIMIT`) | `[context-guard]` no arranque: `/sp-handoff --launch --auto`, sem perguntar | uma vez por sessão; não começar o ciclo na sessão cheia |

## Review restart (pushback)

Quando o user diz que algo está errado/partido/em falta («está errado», «está partido», «tem erros», «isso não está certo», «isso está mal», «wrong», «broken», «has bugs»), o ciclo recomeça na fase anterior mais relevante, não só na DA. Perguntar que fase o user acha que falhou e re-correr daí com o novo input. Defeito: fase 1 (Grill); «scope changed» / «estamos a resolver o problema errado» → fase 1; «implementação errada, plano certo» → fase 4 (DA). Honrar o sinal: não remendar a DA quando a causa é a montante.

## Commit

Autorizações `commit`/`push`/`pr`/`restricoes` do frontmatter mandam (`michi-modo-auto.md` §Autorizações do SP). Só depois de o user aprovar o report (e ter podido agir no Reflect): propor uma mensagem convencional (assunto ≤72 car., corpo com o porquê); o user confirma antes de qualquer `git commit`. Push + merge são passo separado confirmado (alvo por defeito `main`). **Se o repo tem mais de um ramo longo (`master`, `main`, `dev`), perguntar qual antes do push** (michi 2026-09-03).

**Worktree → dev:** `fetch`, merge de `origin/dev` NA worktree, resolver e correr os gates lá, só depois merge no pai (`michi-worktree-merge.md`).

## Ciclo de vida

DR/DP/SP movem-se TODO → Doing → Done com `sp-move.py`/`doc-move.py`; `/michi status` lista o estado. Scripts, tabela de eventos e `status`: `michi-lifecycle.md`.
