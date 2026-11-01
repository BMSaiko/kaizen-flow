# michi — fase Gates (5)

Ordem fixa: **gates → harden → pentest → review**. Cada passo só corre se o anterior estiver verde; `skip harden|pentest|review` salta só esse passo, nunca os gates.

## Gates por tipo de repo

`python -I scripts/sp-gates.py --sugerir <repo>` imprime o bloco `gates:` para colar no frontmatter do SP.

| Tipo (deteção) | Comandos |
|---|---|
| Node (`package.json`) | `npm run lint`, `npm run typecheck`, `npm run build`, `npm test` (só os scripts que existem) |
| Tauri (`src-tauri/Cargo.toml`) | `cargo check --manifest-path src-tauri/Cargo.toml` + os de Node |
| Python (`pyproject.toml`/`pytest.ini`/`setup.cfg`) | `python -m pytest -q` |
| Vault (`tools/vault-mcp` + `scripts/context-budget.py`) | `python -I scripts/context-budget.py`, `python -I scripts/test-fast.py` |

## Execução e resumo

- `python -I scripts/sp-gates.py <SP> [--full]`: por ordem, pára no primeiro vermelho (rc 1) e nunca corre os seguintes.
- Saída: por gate `comando`, `rc`, tempo e últimas 10 linhas; no fim tabela `# | comando | RC | estado` (`verde`, `VERMELHO`, `TIMEOUT`, `cache`, `não correu`). Cola-se no Report.
- Sem `|| true`, sem `--force`, sem segredos: o script recusa (rc 2) antes de correr.
- **Retry:** falha = corrigir a causa e repetir todos com `--full`; o limite vem de `max_tentativas` do perfil (`michi-perfis.md`).

## Passos seguintes

`/harden` (só leitura, FAIL bloqueia) → `/pentest` (achados viram SPs) → `/review-ciclo` (3 iterações, depois escalada). Detalhe: `michi-fases-detalhe.md` §Fase 5.
