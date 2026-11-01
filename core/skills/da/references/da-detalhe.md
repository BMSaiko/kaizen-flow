---
name: da-detalhe
description: Detalhe do da - checkpoint em ficheiro, retoma, verificação, rollback, LFS, anti-padrões, adaptação Claude Code
---
# DA — detalhe (movido do SKILL.md v2.2.0)

> Adaptado de obra/superpowers para pi coding agent + the agent.

Fase de **execução** de um plano DP aprovado: fase a fase, com verificação em cada passo, escalada estruturada na falha, checkpoints para retomar e rollback automático. **Evidência antes de afirmação: sem «feito» sem verificação; cada passo é auditável.**

| Cenário | Aplicar? |
|---|---|
| Executar plano DP aprovado | **OBRIGATÓRIO** |
| Tarefa COMPLEX avulsa | **OBRIGATÓRIO** |
| STANDARD multi-passo | Recomendado |
| TRIVIAL one-liner | Nunca; executar |

## Checklist pré-execução

Plano existe e tem `status: APPROVED`; ficheiros/sistemas do plano acessíveis; dependências disponíveis (assunções do plano); MISTAKE_LOG.md verificado e prevenções aplicadas; plano de rollback revisto e backup se preciso; **checkpoint guardado**. Qualquer falha: resolver antes do loop.

## Checkpoint/Resume (plano avulso, sem SP)

Para um SP usa-se `scripts/michi-checkpoint.py` (ver SKILL.md); o ficheiro abaixo só vale sem SP.

Progresso persistido após cada passo concluído, em `knowledge/projects/<projeto>/plans/_checkpoints/<plano>_checkpoint.md`:

```markdown
---
plan: <plan-file-path>
status: IN_PROGRESS
started: YYYY-MM-DDTHH:MM:SS
last-update: YYYY-MM-DDTHH:MM:SS
current-phase: N
current-step: "descrição"
completed-steps:
  - {step: "1.1", status: OK, evidence: <breve>}
failed-steps: []
aborted: false
---
# Checkpoint: <plano>
## Completed  - [Step N.M] <descrição> — <evidência>
## Failed / Blockers  - None
## Next Step  - [Step N.M+1] <descrição>
```

**Retomar após interrupção** (crash, timeout, stop): (1) ler o checkpoint; (2) `current-phase`/`current-step`; (3) verificar o estado dos passos concluídos (reler ficheiros); (4) retomar do último passo verificado; (5) **nunca re-executar um passo [OK]**: verificar.

## Loop de execução (por passo)

Anunciar → escolher ferramenta → executar → checkpoint → OK: marcar, verificar, reportar, próximo; FAIL: escalada. Formato: `[OK] Step N.M — <descrição> | Evidence: <RC/output>`. Cadência: ≤5 passos reportar cada um; 6-15 de 3 em 3; >15 de 5 em 5 e a cada 5 min; **sempre nas fronteiras de fase**.

## Escalada de falhas (time-box estrito: expira = nível seguinte automático)

| Nível | Gatilho | Ação | Tempo |
|---|---|---|---|
| **L1** | Ferramenta falha | Repetir | máx. 2 repetições |
| **L2** | Repetição falha | Depurar | 3 min |
| **L3** | Debug sem solução | Mudar ferramenta/abordagem | 3 min |
| **L4** | Tudo falhou | Perguntar ao user (saltar/mudar/abortar) | 2 min; sem resposta: passo → BLOCKED |
| **L5** | Bloqueio multi-passo | Plano → BLOCKED + mistake log | — |

## Verificação de integração de fase

Concluída uma fase, antes da seguinte, **obrigatório** (saltá-lo é a causa nº1 de falhas tardias): (1) as saídas integram-se? (2) os ficheiros de fases anteriores ainda se referenciam bem? (3) correr o menor teste de integração que cubra várias fases.

## Regras de verificação

Por passo: reler os ficheiros alterados; codificação (UTF-8, sem BOM em configs); efeitos laterais (ficheiros novos, dependências); menor teste/build relevante. Por fase: integração, testes da fase, evidência no checkpoint. Relatório final:

```markdown
## Test Report — <plano>
- [OK/FAIL] Build: <comando> → RC <código>
- [OK/FAIL] Tests: <N> run, <N> failures
- [OK/FAIL] Lint: <comando> → RC <código>
- [OK/FAIL] Manual: <verificação>
- [OK/FAIL] Integration: <check de integração de fase>
```

## Refresh de contexto

Execuções longas (>10 passos ou >15 min): a cada 10 passos concluídos, 15 min, antes de nova fase e após qualquer escalada L2+: reler o plano **do disco** (não o snapshot do contexto), o Research Brief, `git status` (alterações inesperadas) e os ficheiros alterados antes. O corpo da skill em contexto é um snapshot, o ficheiro pode ter sido editado por um turno paralelo; um `read` custa menos que três patches falhados.

## Rollback automático

| Condição | Âmbito | Ação |
|---|---|---|
| Build falha após 2+ passos | Fase atual | `git checkout -- .` nos modificados |
| Testes falhados >50% | Desde o último checkpoint | Voltar ao estado do checkpoint |
| Erro crítico (perda de dados, corrupção) | Toda a execução | Rollback total + mistake log |
| User pede abortar | Desde o início do plano | Rollback do plano |

Ficheiro novo → apagar; modificado → `git checkout -- <file>` (exige backup git); vários → `git checkout -- .`. **Documentar o rollback ANTES de alterar** (está no plano). Depois: `git status --short` para confirmar árvore limpa.

## Passos paralelos

Só passos independentes de uma fase: não modificam os mesmos ficheiros, não dependem do output uns dos outros, não partilham estado. Independentes: em paralelo (chamadas de ferramentas paralelas); dependentes: sequenciais, pela ordem do plano. **Verificar os resultados paralelos** antes de dar a fase por completa. Assinalar `[PARALLEL]` no plano.

## Pós-execução — LFS (OBRIGATÓRIO)

(1) Nota de sessão `knowledge/projects/<proj>/sessions/YYYY-MM-DD.md`; (2) erros no schema YAML de mistakes; (3) resumo na daily `knowledge/periodic/daily/YYYY/MM/W{1-5}/YYYY-MM-DD.md`; (4) padrão recorrente → atualizar MISTAKE_LOG.md; (5) apagar o checkpoint; (6) plano `status: DONE`, mover para `_done/`.

## Critérios de «feito»

TODOS: cada fase com `[OK]` em cada passo; relatório final com tudo verde; integração verificada; checkpoint apagado (ou `status: DONE`); plano em `DONE`; LFS executado; sem bloqueios abertos. **Faltando algum: NÃO está feito**; reportar o que falta.

## Anti-padrões

«Feito» sem evidência (correr teste/build e reportar RC/output); saltar a integração de fase; repetir às cegas depois de 2 falhas (escalar L1→L4); ignorar o checkpoint (guardar após cada passo); sem refresh de contexto; esconder bloqueios (L4 cedo); saltar o rollback (documentar antes); executar sem plano APPROVED; re-executar [OK] ao retomar; paralelizar passos dependentes.

## Referência rápida

Loop: Announce → Select → Execute → Checkpoint → Verify → Report. Time-box: L1 2 repetições, L2 3 min, L3 3 min, L4 2 min. Código em `~\Documents\projetcs\<projeto>\`. No fim: plano `DONE`, checkpoint apagado, LFS feito.

## Adaptação Claude Code (the agent)

Ferramentas Pi → Claude Code. Sem sub-agentes (sequencial; ver CLAUDE.md).

| Pi | Claude Code |
|----|-------------|
| `sb_search` | `Grep` (conteúdo) / `Glob` (nomes) |
| `sb_read` | `Read` (usar `offset`/`limit`) |
| `sb_list` | `Glob` (ordenar por data) |
| `sb_resolve` | `Glob` por `**/<nome>.md` (wikilink → caminho) |
| `bash` + `find`/`grep` | Proibido; usar `Glob`/`Grep` |
| `subagents` / paralelo | Chamadas de ferramentas paralelas na mesma resposta; nunca `Agent` salvo pedido do user |
| `sync_daily_notes` | Ler/editar a daily note à mão |
