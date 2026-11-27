---
name: auditar
description: Auditoria só de leitura que deteta o contexto (vault, código, SP/PR, UI) e aponta o que está mal, incorreto ou errado. Usar nas fases 5-7 do michi, antes de um PR ou a pedido.
version: 1.0.0
---
# auditar

`/auditar [rapido|normal|total] [alvo]` corre `python -I scripts/auditar.py --repo <repo> [--modo M] [--base REF] [--sp SP.md]` (stdlib, local, sem rede, nunca abre segredos). **Nunca altera o alvo**: só escreve com `--criar-sps`, `--relatorio` e o estado do `ciclo`.

**Contexto** (auto-deteção por cwd, diff, SP em Doing): `codigo`, `vault`, `ui`, `sp`. Se ambíguo, declarar o assumido numa linha e seguir; nunca perguntar em loop/auto.

| Modo | Âmbito |
|---|---|
| rapido | linhas adicionadas do diff |
| normal (defeito) | ficheiros alterados e novos, por inteiro |
| total | todo o repo |

| Tipo | Procura |
|---|---|
| bug | sintaxe Python, JSON inválido, marcadores de conflito |
| regra | `settings.json` do vault sem `permissions.deny`; SP sem gates ou com secção vazia |
| docs | wikilinks partidos em `.md` |
| seguranca | injeção, desserialização, SQL, XSS, paths, Rust `unsafe`, Tauri, segredos |
| robustez | `except:` nu |

**Relatório:** tabela por severidade (crítico/alto/médio/baixo) com tipo, `ficheiro:linha`, problema, correção e evidência (segredos redigidos). Incertos (`TODO`/`FIXME`) vão para «suspeitas» e não contam. rc 0 sem confirmados, 1 com.

**Ignora:** comentários (menos segredos), `test_*`, `*.test.*`, `*.spec.*`, `tests/`. **Supressão:** `# auditar: ok <motivo>` (ou `//`); sem motivo não suprime. **Baseline:** `.auditar-baseline.json` (lista de `tipo|onde|problema`) ou `--no-baseline`.

**Achados → SPs:** `--criar-sps --project <p> [--prefixo s]` cria um SP P1 por achado em `sp/TODO` (`sp-new.py`).

**Ciclo corrigir→reauditar (fase 7 do michi):** revisor independente `sp-revisor.py` escreve os achados (`[bloqueante|menor] ficheiro:linha descrição | verificar: …`); depois `python -I scripts/auditar.py ciclo <estado.json> --achados <f> [--max 3] [--ficheiros F... --raiz D] [--criar-sps --project P]`. APROVADO rc 0, CORRIGIR rc 1, ESCALAR rc 2 (pedir decisão ao {{userName}}). `skip` das fases 5-7 = decisão do {{userName}}.

Testes: `python -m pytest scripts/test_auditar.py -q`.
