# Changelog

Todas as alterações relevantes deste projeto ficam aqui.
Formato: [Keep a Changelog](https://keepachangelog.com/pt-PT/1.1.0/); versões: [SemVer](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Added
- Release assistida: `kf_release.py plan|prepare|publish` (bump semver pelos commits convencionais, CHANGELOG `[Unreleased]` -> `[x.y.z]`, branch `agent/release-x-y-z`, gates e PR sem merge); `publish` só com `--confirmo` e só empurra a tag (nunca reescreve tags, o npm publish fica no workflow); a factory pausa no marco com release e aponta para ele.
- Skill `kf-ship` (`/kf-ship`): leva o ramo ao merge com guarda «testes como contrato» (`core/scripts/kf_ship_testes_guard.py`: teste apagado ou com menos asserts = rc 1, sem testes = rc 3), review-ciclo, PR reutilizado ou aberto por `pr-fase` e merge por `pr_fechar` só com verde e método `worktree-pr`.
- `kaizen factory run|status|stop <projeto>` (`core/scripts/kf_factory.py`, `/factory`): loop autónomo VISION -> backlog -> fila -> gates -> merge (só CI verde) -> reflect, com orçamento, pausas limpas, retoma e lock por projeto.
- Gates de design para SPs `ui: sim`: `ds-lint.py` (literais de cor/espaçamento/tipografia fora dos tokens, `ficheiro:linha`) e `ds-verify.py` (axe WCAG 2.2 AA, screenshots em 3 breakpoints vs `design/baselines/`, orçamento Lighthouse opcional; rc 3 sem browser, nunca verde); `sp-gates --repo` injeta-os só com `ui: sim`; `kaizen ds lint|verify`.
- Perfil `qualidade` em `kaizen.config.json` (`bloqueantes`, `consultivos`, `fases`): `sp-gates --repo` junta-o aos gates do SP (consultivos só registam), `sp-gates --perfil` sugere-o por tipo de repo e `pr_fechar` não faz merge com gate bloqueante vermelho nem sem pentest/review verdes (SP `bloqueado` com motivo).
- Ratchet de tipos e complexidade: `quality-ratchet.py` (ruff C901/PLR + mypy vs `quality-baseline.json`), `mypy.ini`, `max-complexity = 12`, jobs CI `quality` e `typecheck`; `sp-gates.py --sugerir` inclui `ruff`, `mypy` e `tsc --noEmit --strict`

### Fixed
- `handoff --spawn` (herdr) confirma a submissão: se o `agent prompt` deixar o `/michi` no prompt sem Enter, repete o Enter e falha com erro claro se nunca submeter.

## [0.4.0] - 2026-11-23

### Added
- Motor herdr do `sp-fila`: núcleo sobre herdr (`--motor herdr`, subcomandos, retoma), vigia por eventos com metadata «fila n/N · vagas» (sem toasts nem prefixos) e e2e real em sessão isolada (2 projetos, 3 painéis, retoma).
- `herdr_ops` como único sítio da CLI herdr (`HerdrBackend` delega); spike `agent start/prompt/wait`.
- O motor herdr passa a defeito no `sp-fila`; o antigo fica como fallback (`--motor antigo`). `sp-fila` corre só em painel (sem ramo sequencial nem limite por orçamento).
- `sp-handoff --spawn` usa `herdr_ops` (agente + prompt); docs do `/sp-fila` herdr-first.
- `sync`: pastas em `dirs` no manifesto e `fakeVault` gerado dele; `avisos_caixa`, aviso do `sp-autor` e vigia por pasta da fila trazidos do vault.

### Changed
- Simplificação: `a + [b]` passa a `[*a, b]` (RUF005) e variáveis desempacotadas por usar levam `_` (RUF059); sem mudança de comportamento.
- Refactor sem mudança de comportamento: `main`/funções longas divididas em passos nomeados em `sp-handoff`, `sp-fila`, `sp-new`, `sp-move`, `sp-fechar`, `sp-resume`, `sp-preflight`, `sp-provas`, `sp-validate`, `sp-organize`, `sp_fila_execucao`, `kf_catalogo` e `wez` (menos avisos ruff PLR0912/PLR0915).
- Simplificações do `ruff` (`removeprefix`, variáveis por usar, espaços e linhas em branco).
- Removidos `sp-rever` e `sp_veredicto`; `sp-autor` e `sp-revisor` sincronizados com o vault; 5 exports sem uso tirados.
- Testes: `BIN` e `kaizen()` partilhados em `helpers/sandbox.js`, corrida de lock sem sleep, timeouts de 0,3 s nos gates.
- CI: `push` só em `main`, PRs correm uma vez, cancela corrida anterior, `audit` antes do PR; job `lint` com `ruff.toml`.
- CI: a combinação ubuntu/node 22/python 3.13 deixa a matriz `test` (já corre no job `coverage`).

### Fixed
- `handoff --spawn` repete o prompt até o agente ser detetado; o handoff espera que o painel fique livre antes de escrever `/clear`, ignora a sugestão «Try» do prompt vazio e regista erros do envio.
- Vigia usa o estado da fila-mãe, não o `fila.json` dos painéis; `sp-fila` sequencial com worktree e vigia; `--parar` limpa filas órfãs.
- Loops só afetam a sessão dona (`session_id` + `CLAUDE_PID`).
- `sync`: limites de palavra nas regras do `agentSlug`; testes de JSON inválido; portar peças do vault e ponto único de processos.
- Testes: temporários por execução em pasta própria (`/tmp` esgotava os inodes), `loadCore` ignora caches, EC-043 tolera leitura corrompida transitória no Windows.
- `SECURITY.md` e `.github/workflows/ci.yml` estavam em ISO-8859-1; passam a UTF-8.

## [0.3.0] - 2026-11-19

### Added
- `kaizen catalog [render|--check|--json|--no-run]`: catálogo numerado de edge cases (`EC-NNN`, 7 categorias) e use cases (`UC-NNN`) em `docs/catalogo.json`, cada um ligado ao teste que o cobre; gera `docs/edge-cases.md` e a coluna `ID` de `docs/use-cases.md` e mede a fração coberta (rc 0 só com EC ≥ 0,9 e UC = 1,0). Linha de base: EC 0,73, UC 0,65.
- `kaizen demo [--keep]`: corre o ciclo SP (init, sp-new, Doing, gates, Done, report) numa pasta temporária; gravação em `docs/assets/demo.cast`.
- Adapters `opencode`, `cursor` e `gemini` em `kaizen init/doctor --harness` (o `gemini` converte os comandos para `.gemini/commands/*.toml` e anuncia-se em `GEMINI.md`).
- `context-guard.py` mede rollouts do Codex (`event_msg/token_count`); `KAIZEN_CONTEXT_LIMIT` (alias `CLAUDE_CONTEXT_LIMIT`); sem `transcript_path` usa o rollout mais recente em `KAIZEN_CODEX_ROOT`. `kaizen doctor --harness codex` diz se o hook está ligado (`--codex-config`).
- Painéis por backend: interface única (`painel_backend.py`) com `wezterm`, `tmux` e `background` (processo com log, estado por PID), escolhida por `painelBackend` no `kaizen.config.json`; `sp-fila`, a vigia e `sp-handoff --spawn` só falam com ela.
- Sem backend utilizável, `sp-fila --concorrencia` avisa o que falta e corre em série.
- `sp-list --tipo dr|dp` e `sp-move --tipo dr|dp` (lógica em `doc_ops.py`); `sp-list` mostra no arranque, em dry-run, o que `sp-envelhecer` subiria (`--sem-envelhecer` desliga); `sp-new` aceita `--ficheiros/--horas/--risco` e usa `sp-escalao` quando falta `--priority`.
- `test_orfaos.py`: falha e lista todo script de `core/scripts` sem chamador fora de `commands.md`, `agent-commands.md` e CHANGELOG.

### Changed
- Simplificação: `try/except/pass` passa a `contextlib.suppress` em `sp-move`, `sp-rever`, `sp_escalada` e `sp_disco` (ruff SIM105), sem mudança de comportamento.
- Refactor do vault chega ao `core/`: regras das skills `da`, `dr`, `dp` e `super-prompt` passam a apontar para um só dono (`AGENTS.md`, `michi-modo-auto.md`); sync, testes e audit verdes.

### Deprecated
- `doc-list.py` e `doc-move.py` ficam como aliases finos obsoletos de `sp-list --tipo` e `sp-move --tipo`, durante pelo menos uma versão.

### Decided
- `sp-metricas` fica: é chamado por `sp-move` em `done` e por `sp-fila`. `skill-cut` fica: é ferramenta manual de refactor de skills, referida no `SKILL.md` do michi e coberta por testes; remover não reduz superfície útil.

## [0.2.0] - 2026-11-08

### Changed
- Refactor de `bin/`: um só predicado de seleção do sync (`plan()` e `owns()`), `SCRIPT_NAMES`/`SKIP` em `bin/sync-manifest.json`, lançamento do Python (`-I -B`, `PYTHONDONTWRITEBYTECODE`) e `homedir` em `bin/env.js`; sem mudança de comportamento (`core/` idêntico).
- CI: workflow reutilizável `test.yml` (matriz Node x Python 3.10/3.13, cache npm/pip) usado por `ci`, `publish` e `release`.

### Added
- `kaizen init` deteta o comando de testes do projeto-alvo (`npm test`, `pytest`, `cargo test`, `go test ./...`) e grava `test.cmd` em `kaizen.config.json`, sem sobrescrever valores manuais.
- Fase de testes do michi: `sp-gates --testes <repo> [--sp SP]` corre o `test.cmd` como gate, regista tentativas em `## Testes` e respeita `max_tentativas` (rc 3 sem `test.cmd`, rc 4 no limite); o sync inclui `da-stop.py`.
- Docs: `docs/testes.md` cobre deteção, fase de testes, CI e execução local; `docs/config.md` e `docs/commands.md` atualizados.
- CI: job `smoke` (`npm pack` + `kaizen init` + `kaizen audit` num diretório temporário) e artefacto de cobertura (JS nativo, Python `pytest-cov`; `KAIZEN_COVERAGE=1 npm test`), sem limiar bloqueante.

## [0.1.1] - 2026-11-05

### Added
- Publicação no npm (`npx kaizen-flow`): metadados do pacote e workflow `publish` por tag com provenance.


## [0.1.0] - 2026-11-05

Primeira release do kaizen-flow (histórico desde 2026-10-22).

### Added
- Pacote multi-harness com adapters e CLI `kaizen` (`init`, `sync`, `audit`, `usage`).
- Fases do ciclo michi no pacote: `pentest`, `review-ciclo` e `pr-fase` (skill, script e gate).
- Motor único `kaizen_engine`, parametrizado por `kaizen.config.json` (`userName`, `spRoot`).
- `sp-fila` com orquestrador de saída curta, execução paralela e orçamento por programa (`--programa`).
- `sp-estado`, `sp-fechar`, `sp-metricas` e `sp-escalao`; `sp-gates` salta gates verdes com inputs inalterados.
- Pré-aprovação no SP (`permitir`, Decisões, `precisa_perguntar`), escopo por SP e gates no frontmatter.
- Hooks de ciclo de vida (`kaizen_hooks`) e `kf_errlog`, que regista falhas dos `sp-*.py` em JSONL.
- `sync --check` para detetar um `core/` desatualizado.

### Fixed
- `kaizen sync` copia `.claude/modelos.json` para `core/.claude/` e os adapters instalam-no em `.claude/` do projeto: sem ele `sp-fila --concorrencia` parava com «sem modelo» (24 falhas em `test_sp_fila_paralelo.py`).
- Testes de handoff simulam o texto no prompt (o envio confirma-o antes do Enter).
- Runner de testes portável (Node 18 no Windows não expande globs).
- Handoffs sem consola a piscar no Windows (`CREATE_NO_WINDOW`).
- Testes e caminhos POSIX independentes do ambiente e do WezTerm no CI.
- `sync` copia as fixtures do `sp-fila`; fixture sem literais de caminho Windows.

[Unreleased]: https://github.com/BMSaiko/kaizen-flow/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/BMSaiko/kaizen-flow/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/BMSaiko/kaizen-flow/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/BMSaiko/kaizen-flow/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/BMSaiko/kaizen-flow/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/BMSaiko/kaizen-flow/releases/tag/v0.1.0
