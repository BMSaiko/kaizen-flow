# Estado dos painéis (hooks Stop/Notification)

Cada SP numa fila tem `<raiz>/<fila>/<slug>.json` (raiz: `~/.claude/sp-fila`, `SP_FILA_ROOT`). Só metadados, nunca texto da conversa.

| Campo | Valor |
|---|---|
| `estado` | `pendente`, `a-correr`, `pergunta`, `bloqueado`, `done`, `falhou` |
| `pergunta` | `null`, `notification` (o harness pediu atenção) ou `stop` (o turno acabou à espera do BMS) |
| `fase` | fase do michi em curso ou `null` |
| `modelo`, `worktree`, `pane`, `inicio`, `fim`, `msg`, `atualizado` | como em `sp-estado.py` |

Ficheiros antigos sem `fase`/`pergunta` continuam a ler-se.

## Hook `scripts/kf_painel_hook.py`

| Evento | Efeito |
|---|---|
| `UserPromptSubmit` | `a-correr`, `pergunta=null` |
| `Notification` | `pergunta`, `pergunta=notification` |
| `Stop` | `pergunta`, `pergunta=stop`; `done` se o SP já está em `sp/Done` |

O slug vem de `KAIZEN_SLUG` ou do ramo `agent/<slug>` (casa por prefixo, o ramo vem truncado). Sem fila, JSON ilegível ou transição inválida: ignora e sai com 0, nunca bloqueia o painel. A escrita é atómica (`sp_disco.guardar`).

- Claude Code: `kaizen init` regista os três hooks (`adapters/claude`).
- Outros harness: sem hooks equivalentes verificados; ligar `kf_painel_hook.py` ao evento de fim de turno e de notificação, com o mesmo JSON no stdin (`hook_event_name`), e usar `get-text` do WezTerm só como apoio.
