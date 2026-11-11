# Changelog

Todas as alterações relevantes deste projeto ficam aqui.
Formato: [Keep a Changelog](https://keepachangelog.com/pt-PT/1.1.0/); versões: [SemVer](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Added
- `kaizen demo [--keep]`: corre o ciclo SP (init, sp-new, Doing, gates, Done, report) numa pasta temporária; gravação em `docs/assets/demo.cast`.
- Adapters `opencode`, `cursor` e `gemini` em `kaizen init/doctor --harness` (o `gemini` converte os comandos para `.gemini/commands/*.toml` e anuncia-se em `GEMINI.md`).
- `context-guard.py` mede rollouts do Codex (`event_msg/token_count`); `KAIZEN_CONTEXT_LIMIT` (alias `CLAUDE_CONTEXT_LIMIT`); sem `transcript_path` usa o rollout mais recente em `KAIZEN_CODEX_ROOT`. `kaizen doctor --harness codex` diz se o hook está ligado (`--codex-config`).
- Painéis por backend: interface única (`painel_backend.py`) com `wezterm`, `tmux` e `background` (processo com log, estado por PID), escolhida por `painelBackend` no `kaizen.config.json`; `sp-fila`, a vigia e `sp-handoff --spawn` só falam com ela.
- Sem backend utilizável, `sp-fila --concorrencia` avisa o que falta e corre em série.
- `sp-list --tipo dr|dp` e `sp-move --tipo dr|dp` (lógica em `doc_ops.py`); `sp-list` mostra no arranque, em dry-run, o que `sp-envelhecer` subiria (`--sem-envelhecer` desliga); `sp-new` aceita `--ficheiros/--horas/--risco` e usa `sp-escalao` quando falta `--priority`.
- `test_orfaos.py`: falha e lista todo script de `core/scripts` sem chamador fora de `commands.md`, `agent-commands.md` e CHANGELOG.

### Deprecated
- `doc-list.py` e `doc-move.py` ficam como aliases finos obsoletos de `sp-list --tipo` e `sp-move --tipo`, durante pelo menos uma versão.

### Decided
- `sp-metricas` fica: é chamado por `sp-move` em `done` e por `sp-fila`. `skill-cut` fica: é ferramenta manual de refactor de skills, referida no `SKILL.md` do michi e coberta por testes; remover não reduz superfície útil.

## [0.2.0] - 2026-11-08

### Changed
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

[Unreleased]: https://github.com/BMSaiko/kaizen-flow/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/BMSaiko/kaizen-flow/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/BMSaiko/kaizen-flow/releases/tag/v0.1.0
