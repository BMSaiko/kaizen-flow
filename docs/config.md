# `kaizen.config.json`

Optional, in the project root. `init` does not create it; without it the defaults below apply.

```json
{
  "spRoot": "knowledge/projects/kaizen",
  "docsRoot": "knowledge/projects",
  "reportsDir": "reports/usage",
  "sources": ["claude", "codex"],
  "prices": "my-prices.json",
  "userName": "Ana"
}
```

| Key | Default | Used by |
|---|---|---|
| `spRoot` | `knowledge/projects/kaizen` | `sp-*` scripts: stories live in `<spRoot>/<project>/sp/{TODO,Doing,Done}` |
| `docsRoot` | `knowledge/projects` | `doc-list.py`, `doc-move.py` (DR/DP documents) |
| `reportsDir` | `reports/usage` | `kaizen report` |
| `sources` | `["claude", "codex"]` | `kaizen usage`, `kaizen report` |
| `prices` | bundled `usage/prices.json` | cost calculation |
| `userName` | `user` | name the scripts' warnings use for you; empty or non-string falls back to `user` |

`sources` must be a list; malformed values stop with a one-line message.

`spRoot` and `docsRoot` are relative to the project root. `init` and `status` follow `spRoot` too; when `docsRoot` is not set, DR/DP folders sit next to the stories.

## `kaizen-hooks.json`

Optional, in the project root. Runs your own commands on workflow events. `python scripts/kaizen_hooks.py fire <event> --slug S --project P` reads the `hooks` list; invalid entries are dropped silently, and without the file nothing happens.

```json
{
  "hooks": [
    { "event": "michi.closed", "cmd": "npm test", "modo": "bloqueante", "timeout": 120 },
    { "event": "sp.moved", "cmd": "echo moved" }
  ]
}
```

| Field | Default | Meaning |
|---|---|---|
| `event` | required | one of `sp.created`, `sp.moved`, `michi.phase.start`, `michi.phase.end`, `michi.gate.failed`, `michi.commit`, `michi.closed` |
| `cmd` | required | command to run (non-empty string) |
| `modo` | `informativo` | `bloqueante` runs before and aborts on rc != 0 or timeout; `informativo` runs after and only warns |
| `timeout` | `10` | seconds, greater than 0 |
| `if` | `{}` | extra conditions (object) |
| `enabled` | `true` | any value other than `true` disables the entry |

## Projects

`sp-new.py --project P` needs the folder `<spRoot>/P/` to exist. `kaizen init` creates `_default` (with `sp|dr|dp` × `TODO|Doing|Done`); for another project:

```sh
mkdir -p knowledge/projects/kaizen/app/sp/TODO
python scripts/sp-new.py --project app --slug login --priority P2
```
