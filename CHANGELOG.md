# Changelog

Todas as alterações relevantes deste projeto ficam aqui.
Formato: [Keep a Changelog](https://keepachangelog.com/pt-PT/1.1.0/); versões: [SemVer](https://semver.org/lang/pt-BR/).

## [Unreleased]

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
- Runner de testes portável (Node 18 no Windows não expande globs).
- Handoffs sem consola a piscar no Windows (`CREATE_NO_WINDOW`).
- Testes e caminhos POSIX independentes do ambiente e do WezTerm no CI.
- `sync` copia as fixtures do `sp-fila`; fixture sem literais de caminho Windows.

[Unreleased]: https://github.com/BMSaiko/kaizen-flow/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/BMSaiko/kaizen-flow/releases/tag/v0.1.0
