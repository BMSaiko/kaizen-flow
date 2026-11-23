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

O workflow reutilizável `.github/workflows/test.yml` corre `kaizen audit .` e `npm test` numa matriz Node x Python 3.10/3.13 (cache npm/pip) e é usado por `ci`, `publish` e `release`. O `ci` acrescenta o job `smoke`: `npm pack`, `kaizen init` e `kaizen audit` num diretório temporário. O artefacto de cobertura (JS nativo, Python `pytest-cov`) é gerado com `KAIZEN_COVERAGE=1`; o job `coverage` do `ci` falha abaixo do limiar (ver «Limiar de cobertura»).

## Limiar de cobertura

O limiar vive em `package.json` (`coverageThreshold`): `js.lines` (linhas, `--experimental-test-coverage`) e `python.lines` (`--cov-fail-under` do `pytest-cov`). Valores iniciais = cobertura medida em 2026-11-09, arredondada para baixo: JS 70 % (70,38), Python 90 % (90,74). `bin/run-tests.js` aplica-os só com `KAIZEN_COVERAGE=1`, por isso falha no job `coverage` e não nos testes locais normais.

Regra de subida:

- Só sobe: depois de um PR que aumente a cobertura, medir com `KAIZEN_COVERAGE=1 npm test` e subir o limiar para o novo valor inteiro, no mesmo PR.
- Nunca desce sem justificação escrita no PR.
- Verificar a falha: pôr um limiar acima do medido (p.ex. 99) e confirmar que `KAIZEN_COVERAGE=1 npm test` sai com erro.

## Catálogo EC/UC e limiar 0,9

Além da cobertura de linhas, o workflow mede a cobertura de casos: `docs/catalogo.json` é a fonte única dos edge cases (`EC-NNN`, por categoria) e dos use cases (`UC-NNN`); `docs/edge-cases.md` e `docs/use-cases.md` são gerados a partir dele (`kaizen catalog render`).

- Cada entrada tem `teste` = `caminho::[Classe::]nome` ou `por cobrir`. Um caso só conta como coberto se o teste existir e passar (pytest: não falha nem é saltado; Node: `# pass` ≥ 1 e `# fail` 0).
- `kaizen catalog --check`: valida a estrutura (IDs únicos e sem buracos, categorias com casos, testes existentes, nome do teste sem outro `ec_NNN`/`uc_NNN`) e que os `.md` estão em dia; rc 1 em qualquer problema.
- `kaizen catalog` (report): corre os testes ligados e imprime cobertos/total; rc 0 só com EC ≥ 0,9 e UC = 1,0 (`limiar` no JSON). `--json` para máquinas, `--no-run` conta os testes ligados sem os correr.
- Para cobrir um caso: escrever o teste, trocar `por cobrir` pelo nome real em `docs/catalogo.json`, correr `kaizen catalog render` e `kaizen catalog --check`.
- Linha de base (2026-11-16): EC 43/59 (0,73), UC 22/34 (0,65); rc 1 até os filhos do programa de retoma fecharem os casos em falta. Em 2026-11-19: UC 34/34 (1,0) com os testes e2e.

## Testes e2e dos use cases

`tests/e2e-use-cases.test.js` tem um teste por `UC-NNN` (nome estável `UC-NNN <objetivo>`, ligado em `docs/catalogo.json`) e um teste do fluxo normal (init → doctor → sp-new → sp-validate → sp-move → status). Cada teste corre o CLI real (`bin/kaizen.js` e os `sp-*` instalados) num sandbox de `tests/helpers/sandbox.js`:

- tmpdir com espaço e acento no caminho, `git init` e `kaizen init` prontos;
- `HOME`/`USERPROFILE` isolados e sem variáveis de painel (`HERDR_PANE_ID`, `WEZTERM_PANE`, `TMUX*`): nada toca na máquina nem abre painéis;
- transcripts de fixture para `usage`/`report`; fila, handoff e painéis só em `--dry-run`;
- retoma: UC-030 usa um processo real que segura o lock e é morto a meio (2.º processo recusado com EC-043) (`matar()`, multiplataforma).

Correr só estes: `node --test tests/e2e-use-cases.test.js` (cerca de 15 s); um caso: `node --test --test-name-pattern "UC-015" tests/e2e-use-cases.test.js`.

## Cobertura do diff

O limiar global não diz se as linhas **alteradas** estão testadas. `python core/scripts/sp-cobertura-diff.py --repo . --base main` calcula a cobertura só das linhas adicionadas (mesmo parser de diff do `pentest.py`) a partir de relatórios já gerados (`coverage/lcov.info`, JSON do coverage.py ou `coverage/python.xml` do CI) e sai com rc 1 abaixo de `qualidade.coberturaDiff` (defeito 85, ver `docs/config.md`). Ignora testes, docs, config e linhas não executáveis; ficheiros de código sem dados no relatório são avisados e não contam. Não altera os limiares globais.

## Testes de falha e propriedades

- Fixtures de injeção em `core/scripts/conftest.py`: `relogio` e `tempo_falso` (relógio controlado), `falha_replace` (`os.replace` falha N vezes e depois passa); cada uma tem teste-sentinela.
- Propriedades Hypothesis em `core/scripts/test_propriedades.py` (checkpoint/journal, estado corrompido, locks), perfil `kaizen` determinístico (`derandomize=True`). Contraexemplo = bug: correção mínima no módulo dono + EC no catálogo.
- Fault injection em `core/scripts/test_falha_journal_disco.py` (sinais, disco cheio, quarentena, cauda truncada, `.rec` morto, unlink preso, heartbeat) e performance em `test_falha_performance.py` (checkpoint < 200 ms, pré-voo < 2 s, mediana de 5).
- Nome do teste com o EC que garante (`test_ec_NNN_...`); confirmar o ID no catálogo antes de o escrever.
- Cobertura de linhas ≥ 90 % nos módulos de erro/retoma (`sp_journal`, `sp_disco`, `sp-resume`, `sp-preflight`, `kf_erros`); o bloco Windows de `sp_disco.pid_vivo` não corre no Linux.
- fast-check (Node): sem alvo. O CLI Node só copia ficheiros (`init`, `sync`) e invoca Python; o estado (journal, checkpoint, locks) vive em Python e é coberto pelo Hypothesis.

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
| `sp_painel_estado.py` | `test_sp_painel_estado.py` (estado por fila e por SP, `sp-estado.py` com estado, `--listar`, `--migrar`) |
| `sp-autor.py` | `test_sp_autor_painel.py` |
| `handoff_pane.py` (socket) | `test_handoff_socket.py` (socket do WezTerm morto, painel inexistente; `run` injetado) |
| `context-guard.py` | hook do vault; o teste (`test_context_guard.py`) fica no vault porque afirma textos em português (ver `SKIP` em `bin/sync.js`) |
| `wt_redirect.py` | depende de `sb-worktree.py` do vault; o teste (`test_wt_redirect.py`) fica no vault (`SKIP`) |
