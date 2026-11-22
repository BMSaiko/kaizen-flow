# Spike F1 — `herdr agent start/prompt/wait` (herdr 0.9.5)

Script: `core/scripts/herdr-spike-agent.py` (sessão isolada `--session`, servidor headless `herdr --session S server`, `server stop` + `session delete` no fim). Todas as saídas abaixo são reais (claude 2.1.330, `--model haiku`).

## Contrato JSON (para o `herdr_ops` do F2)
Todas as respostas: `{"id":"cli:<grupo>:<acao>","result":{...}}` ou `{"id":...,"error":{"code","message"}}` (rc 1; `error` pode vir em stdout ou stderr).

| Comando | `result.type` | Campos usados |
|---|---|---|
| `workspace create --cwd D --label L --no-focus` | `workspace_created` | `root_pane.pane_id`, `workspace.workspace_id`, `tab.tab_id` |
| `agent start NOME --kind claude --pane P --timeout MS -- <args>` | `agent_started` | `agent.{name,pane_id,agent_status,interactive_ready,agent_session.value,cwd}`, `argv` |
| `agent prompt NOME\|PANE TEXTO --wait [--until S] --timeout MS` | `agent_prompted` | `agent.{agent_status,completion_seq,state_change_seq}` |
| `agent wait ALVO [--until S] --timeout MS` | idem | idem |
| `agent list` / `agent get ALVO` | `agent_list` / `agent_info` | lista de `agent` |
| `agent explain ALVO --json` | — | `evaluated_rules` (porquê do estado) |
| `pane read P --source visible` | texto | ecrã |
| `pane close P` / `server stop` / `session delete S` | `ok` | — |

Estados: `idle, working, blocked, done, unknown`. Observado: `idle` após start; após um turno concluído ficou `idle` com `completion_seq` a subir (não `done`); `blocked` quando o claude pede o «trust folder» de um diretório novo. `prompt` a agente `blocked` → erro `agent_blocked` (sem enviar nada). `start` com nome repetido → `agent_name_taken`.

## Veredicto por capacidade
| Capacidade | Veredicto |
|---|---|
| `agent start --kind claude -- --model X` (flags após `--`) | **usa** (argv `claude --model haiku` confirmado) |
| `agent prompt --wait` (turno completo) | **usa** (devolveu `idle` + `completion_seq`) |
| Estado `blocked` | **usa** (deteta o diálogo de confiança; `prompt` recusa com `agent_blocked`) |
| Sessão isolada para e2e | **usa** (`--session S`, `server`; **as sessões persistem**: apagar com `session delete`, senão o agente volta no run seguinte) |
| cwd do agente = worktree | **contorna** (ver abaixo) |
| Prompt `/michi --auto` | não testado com claude real (gasta quota); é texto de `agent prompt`, esperado igual |
| `done` vs `idle` como fim de turno | **falta clareza**: tratar `idle` com `completion_seq` maior como fim; `done` só se aparecer |

## Limite: `agent start` ignora o cwd do painel
O claude arrancou sempre em `~/Documents/Second-Brain`, mesmo com `workspace create --cwd D`, `cd D` prévio no painel ou o CLI chamado de D. Causa: `~/.bashrc` define `claude() { cd "$HOME/Documents/Second-Brain" && command claude "$@"; }` e o herdr lança pela shell, que usa a função. **Alternativa validada (`pane run`)**: `herdr pane run P "cd <worktree> && command claude --model X"`; o herdr deteta o agente sem `agent start` (cwd certo, `agent list` com `agent_status`), e `agent prompt P ...`/`agent wait P` funcionam pelo id do painel. `agent rename P nome` dá-lhe nome. Para o F2: `launch = pane run "cd WT && command claude ..."` + espera `interactive_ready`/estado ≠ `unknown`, depois `agent prompt`. (Alternativa: o BMS condicionar a função no bashrc.)

## Decisões para F2
- Painéis lançados com `pane run "cd WT && command claude --model N [flags]"`; `agent start` só onde o cwd não importa.
- Alvo dos comandos = `pane_id` (estável) e `agent rename` para legibilidade.
- Tratar `agent_blocked` como sinal de intervenção (trust folder/permissões); `agent_prompt_stalled` e `timeout` como falha com motivo.
- Sempre `--timeout` explícito; e2e sempre em sessão própria com `session delete` no `finally`.
