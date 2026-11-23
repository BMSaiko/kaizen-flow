# Estado dos painéis (hooks Stop/Notification)

Cada SP numa fila tem `<raiz>/<fila>/<slug>.json` (raiz: `~/.claude/sp-fila`, `SP_FILA_ROOT`). Só metadados, nunca texto da conversa.

| Campo | Valor |
|---|---|
| `estado` | `pendente`, `a-correr`, `pergunta`, `bloqueado`, `done`, `falhou` |
| `pergunta` | `null`, `notification` (o harness pediu atenção) ou `stop` (o turno acabou à espera do BMS) |
| `fase` | fase do michi em curso ou `null` |
| `modelo`, `worktree`, `pane`, `inicio`, `fim`, `msg`, `atualizado` | como em `sp-estado.py` |
| `motivo` | `null` ou a pausa gravada pelo vigia: `EC-016` quota/limite de uso, `EC-017` rede, `EC-066` sessão/login expirado, com a linha do ecrã |
| `retoma_em` | `null` ou hora local ISO em que a pausa acaba (a do texto do harness, senão agora + `KF_RETOMA_MIN`, defeito 30 min); `EC-066` não tem retoma automática |

Ficheiros antigos sem `fase`/`pergunta`/`motivo`/`retoma_em` continuam a ler-se.

Pausa por quota/rede/sessão: o vigia lê a cauda do ecrã de cada SP `a-correr`; se ficar parada em dois ticks e `kf_erros.classificar_falha` a reconhecer, o SP passa a `bloqueado` com `motivo` e `retoma_em` (sem escalada de modelo, checkpoint intacto). Passada a hora, com o painel vivo, volta a `a-correr` e recebe «continua»; com o painel morto, `kaizen resume <slug>` retoma (antes da hora recusa com o EC e a hora). `sp-estado.py --listar` mostra `retoma <hora>`.

## Nomes dos painéis

`<SP_FILA_ROOT>/nomes.json` guarda nome→pane (`nome`, `backend`, `pane`, `cwd`, `papel`, `slug`, `criado`), escrita atómica; entradas cujo pane já não está em `backend.listar()` são podadas na leitura e um ficheiro corrompido é recriado com aviso. O campo `nome` do estado de cada SP guarda o nome do seu painel. `heimdall` só se regista para o cwd da raiz do Second Brain (`SB_ROOT`).
## Hook `scripts/kf_painel_hook.py`

| Evento | Efeito |
|---|---|
| `UserPromptSubmit` | `a-correr`, `pergunta=null` |
| `Notification` | `pergunta`, `pergunta=notification` |
| `Stop` | `pergunta`, `pergunta=stop`; `done` se o SP já está em `sp/Done` |

O slug vem de `KAIZEN_SLUG` ou do ramo `agent/<slug>` (casa por prefixo, o ramo vem truncado). Sem fila, JSON ilegível ou transição inválida: ignora e sai com 0, nunca bloqueia o painel. A escrita é atómica (`sp_disco.guardar`).

- Claude Code: `kaizen init` regista os três hooks (`adapters/claude`).
- Outros harness: sem hooks equivalentes verificados; ligar `kf_painel_hook.py` ao evento de fim de turno e de notificação, com o mesmo JSON no stdin (`hook_event_name`), e usar `get-text` do WezTerm só como apoio.

Um SP em Doing sem painel vivo e com `fim` em falta no journal aparece em `sp-estado.py --listar` como `interrompido`, com o comando `kaizen resume <slug>`; o lock por SP (`sp_disco.tomar_lock`, heartbeat) recusa um segundo painel e põe lock corrompido em quarentena `.corrupt-<ts>`.

Estado de fase por SP (checkpoint e journal em `.kaizen/estado/`, quarentena `.corrupt-<ts>`): ver «Phase checkpoint and journal» em [error-log.md](error-log.md).
