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

## Fase de testes (`test.cmd` da config)

`python -I scripts/sp-gates.py --testes <repo-alvo> --sp <SP> [--timeout N]` corre o `test.cmd` de `<repo-alvo>/kaizen.config.json` (gravado por `kaizen init`, editável) como gate, em `<repo-alvo>`, e regista cada tentativa na secção `## Testes` do SP (`- tentativa N: comando rc=… estado`), que o Report lê.

| RC | Significado | Ação |
|---|---|---|
| 0 | verde | seguir para harden |
| 1 | vermelho ou `TIMEOUT` | bloqueia o avanço; corrigir a causa e repetir |
| 2 | `test.cmd` proibido (`--force`, `git reset --hard`, segredos, …) | nada corre; corrigir a config |
| 3 | sem `test.cmd` | nada corre, fica um aviso no SP; **perguntar ao user** (`AskUserQuestion`) o comando, nunca saltar em silêncio |
| 4 | limite atingido | `max_tentativas` falhas seguidas e `gate-falha` em `parar_se` (mesma regra do DA): parar e escalar |

- Só corre comandos vindos da config do projeto, nunca de argumentos nem do corpo do SP.
- As falhas seguidas contam-se desde o último verde; um verde zera o contador.

## Passos seguintes

`/harden` (só leitura, FAIL bloqueia) → `/pentest` (achados viram SPs) → `/review-ciclo` (3 iterações, depois escalada). Detalhe: `michi-fases-detalhe.md` §Fase 5.
