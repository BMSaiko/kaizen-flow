# Testes

`npm test` corre tudo num só comando (`bin/run-tests.js`):

1. JS: `node --test tests/*.test.js`
2. Python: `python -m pytest -q tests core/scripts` (pytest tem de estar instalado; sem ele o comando falha com mensagem clara)

Os testes usam `tmp_path`; nenhum escreve no repo (a cache de `sp-gates` é redirecionada em `test_sp_gates.py`).

## Deteção no `init` (projeto-alvo)

`kaizen init` lê só os manifestos do projeto-alvo (nunca executa nada nem lê `.env`) e grava `test.cmd` em `kaizen.config.json`: `npm test`, `pytest`, `cargo test` ou `go test ./...`. Sem testes reconhecidos não cria ficheiro; um `init` repetido nunca sobrescreve um `test.cmd` manual. Detalhe e tabela em `docs/config.md`.

## Fase de testes do michi (projeto-alvo)

`python -I core/scripts/sp-gates.py --testes <repo-alvo> --sp <SP>` corre o `test.cmd` de `<repo-alvo>/kaizen.config.json` (detetado por `kaizen init`, ver `docs/config.md`) como gate e regista cada tentativa na secção `## Testes` do SP.

| RC | Significado |
|---|---|
| 0 | verde |
| 1 | vermelho ou timeout (`--timeout`, defeito 300 s): bloqueia o avanço |
| 2 | `test.cmd` proibido (`--force`, `git reset --hard`, segredos): nada corre |
| 3 | sem `test.cmd`: nada corre, fica um aviso no SP e o michi pergunta ao utilizador |
| 4 | `max_tentativas` falhas seguidas com `gate-falha` em `parar_se`: parar e escalar |

Só corre comandos vindos da config. Coberto por `core/scripts/test_sp_gates.py` (sucesso, falha, comando em falta, timeout, comando proibido, registo no SP com CRLF, limites).

## CI

O workflow reutilizável `.github/workflows/test.yml` corre `kaizen audit .` e `npm test` numa matriz Node x Python 3.10/3.13 (cache npm/pip) e é usado por `ci`, `publish` e `release`. O `ci` acrescenta o job `smoke`: `npm pack`, `kaizen init` e `kaizen audit` num diretório temporário. O artefacto de cobertura (JS nativo, Python `pytest-cov`) é gerado com `KAIZEN_COVERAGE=1`, sem limiar bloqueante.

## Correr localmente

```
npm test                          # JS + Python
KAIZEN_COVERAGE=1 npm test        # com cobertura (pytest-cov instalado)
node bin/kaizen.js audit .        # padrões proibidos
python -m pytest core/scripts/test_sp_gates.py -q   # só a fase de testes
```

## Cobertura de `core/scripts`

Todo o script tem teste dedicado, exceto os da tabela, que têm justificação.

| Script | Situação |
|---|---|
| `skill-cut.py` | `test_skill_cut.py` |
| `doc-list.py` | `test_doc_list.py` |
| `sp-validate-hook.py` | `test_sp_validate_hook.py` |
| `sp_progresso.py` | `test_sp_progresso.py` |
| `handoff_pane.py` | `test_handoff_pane.py` (argv, backend, prompt; sem painéis reais) |
| `sp_fila_estado/execucao/paralelo/plano/relatorio.py` | módulos internos de `sp-fila.py`, exercitados por `test_sp_fila_*.py` (auxiliares em `sp_fila_testlib.py`) |
| `handoff_spawn.py` | `test_handoff_spawn.py` (`run`/`sleep`/`copy` falsos) |
| `context-guard.py` | hook do vault; o teste (`test_context_guard.py`) fica no vault porque afirma textos em português (ver `SKIP` em `bin/sync.js`) |
| `wt_redirect.py` | depende de `sb-worktree.py` do vault; o teste (`test_wt_redirect.py`) fica no vault (`SKIP`) |
