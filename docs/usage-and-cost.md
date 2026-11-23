# Usage and cost

`kaizen usage` reads Claude Code transcripts (`~/.claude/projects`) and Codex sessions (`~/.codex/sessions`) and prints totals by day, model, session and 5 h window. `kaizen report` writes the weekly version to `reports/usage/YYYY-WNN.md`. Only metrics are read and written, never conversation content.

Cost is the equivalent at API prices, a relative measure and not what a subscription charges. Prices live in `usage/prices.json` (Claude models); **add the OpenAI/GPT models you use** there, or point to your own file with `--prices` or the `prices` config key. Lookup uses the longest matching model prefix. A model with no price shows cost `n/a` and a warning; it never fails. Internal `<synthetic>` Claude entries are ignored.

Prices file format:

```json
{ "models": { "gpt-5": { "in": 1.25, "out": 10.0 } } }
```

Values are USD per million tokens (optional `cache_read` defaults to `in`, `cache_write` to 1.25 × `in`). Check the provider's current price list; the numbers above are an example only.

Examples: see the usage rows in [use cases](use-cases.md) (`--days`, `--since`, `--source`, `--top`, `--codex-root`, `report --print`, `report --out`).

Known limit: the Codex parser follows the rollout format (`event_msg` / `token_count`, `last_token_usage`) and is tested with synthetic fixtures; if your Codex version logs usage differently, open an issue with an anonymised sample.

## Queue budget (`orcamento`)

```json
{"orcamento": {"spUsd": 10, "diaUsd": 50, "falhasSeguidas": 3}}
```

Safety brake of the autonomous queue (`/sp-fila`, `core/scripts/kf_orcamento.py`). Without the key nothing changes. Each ceiling is optional (`spUsd`, `diaUsd` > 0; `falhasSeguidas` integer >= 1, default 3).

- `spUsd`: cost of the SP that just closed (from `sp-metricas`, when available); `diaUsd`: API-equivalent cost of today's Claude Code transcripts (`usage/kaizen_usage.py`); `falhasSeguidas`: consecutive SPs that did not reach Done. With the key set, this replaces `--max-falhas` (the queue pauses instead of ending).
- The queue checks before launching each SP and after each close: `ok` below 80 % of every ceiling, `aviso` (stderr line) at 80 %, `parar` at 100 %.
- `parar` pauses between SPs (a running panel is never killed): `estado.pausa = {estado: "orcamento", razao, desde}` in `fila.json`, nothing more is launched and no report is written, so no state is lost.
- Resume after raising the ceiling in `kaizen.config.json`: `python -I scripts/sp-fila.py --seguinte --retomar` (re-reads the config; still over = stays paused).
- Metrics only (tokens and USD), never conversation content.
