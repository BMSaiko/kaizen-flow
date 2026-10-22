# `kaizen.config.json`

Optional, in the project root. `init` does not create it; without it the defaults below apply.

```json
{
  "spRoot": "knowledge/projects/kaizen",
  "docsRoot": "knowledge/projects",
  "reportsDir": "reports/usage",
  "sources": ["claude", "codex"],
  "prices": "my-prices.json"
}
```

| Key | Default | Used by |
|---|---|---|
| `spRoot` | `knowledge/projects/kaizen` | `sp-*` scripts: stories live in `<spRoot>/<project>/sp/{TODO,Doing,Done}` |
| `docsRoot` | `knowledge/projects` | `doc-list.py`, `doc-move.py` (DR/DP documents) |
| `reportsDir` | `reports/usage` | `kaizen report` |
| `sources` | `["claude", "codex"]` | `kaizen usage`, `kaizen report` |
| `prices` | bundled `usage/prices.json` | cost calculation |

`sources` must be a list; malformed values stop with a one-line message.

## Projects

`sp-new.py --project P` needs the folder `<spRoot>/P/` to exist. `kaizen init` creates `_default` (with `sp|dr|dp` × `TODO|Doing|Done`); for another project:

```sh
mkdir -p knowledge/projects/kaizen/app/sp/TODO
python scripts/sp-new.py --project app --slug login --priority P2
```
