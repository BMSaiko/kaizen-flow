# Testes

`npm test` corre tudo num só comando (`bin/run-tests.js`):

1. JS: `node --test tests/*.test.js`
2. Python: `python -m pytest -q tests core/scripts` (pytest tem de estar instalado; sem ele o comando falha com mensagem clara)

Os testes usam `tmp_path`; nenhum escreve no repo (a cache de `sp-gates` é redirecionada em `test_sp_gates.py`).

## Cobertura de `core/scripts`

Todo o script tem teste dedicado, exceto os da tabela, que têm justificação.

| Script | Situação |
|---|---|
| `skill-cut.py` | `test_skill_cut.py` |
| `doc-list.py` | `test_doc_list.py` |
| `sp-validate-hook.py` | `test_sp_validate_hook.py` |
| `sp_progresso.py` | `test_sp_progresso.py` |
| `handoff_pane.py` | `test_handoff_pane.py` (argv, backend, prompt; sem painéis reais) |
| `sp_fila_estado/execucao/paralelo/plano/relatorio.py` | módulos internos de `sp-fila.py`, exercitados por `test_sp_fila.py` |
| `handoff_spawn.py` | `test_handoff_spawn.py` (`run`/`sleep`/`copy` falsos) |
| `context-guard.py` | hook do vault; o teste (`test_context_guard.py`) fica no vault porque afirma textos em português (ver `SKIP` em `bin/sync.js`) |
| `wt_redirect.py` | depende de `sb-worktree.py` do vault; o teste (`test_wt_redirect.py`) fica no vault (`SKIP`) |
