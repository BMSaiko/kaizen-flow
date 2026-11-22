# `kaizen.config.json`

Optional, in the project root. Without it the defaults below apply. `init` only writes it to record the detected test command (`test.cmd`); a project with no recognised tests gets no file.

```json
{
  "spRoot": "knowledge/projects/kaizen",
  "docsRoot": "knowledge/projects",
  "reportsDir": "reports/usage",
  "sources": ["claude", "codex"],
  "prices": "my-prices.json",
  "userName": "Ana",
  "test": { "cmd": "npm test" }
}
```

| Key | Default | Used by |
|---|---|---|
| `spRoot` | `knowledge/projects/kaizen` | `sp-*` scripts: stories live in `<spRoot>/<project>/sp/{TODO,Doing,Done}` |
| `docsRoot` | `knowledge/projects` | `doc-list.py`, `doc-move.py` (DR/DP documents) |
| `reportsDir` | `reports/usage` | `kaizen report` |
| `sources` | `["claude", "codex"]` | `kaizen usage`, `kaizen report` |
| `prices` | bundled `usage/prices.json` | cost calculation |
| `test.cmd` | detected by `init` | command that runs the target project's tests (see below) |
| `painelBackend` | `auto` | `sp-handoff --spawn`: where the new session runs (see below) |
| `herdr` | `{"maxPanesPorTab": 2, "workspacePorProjeto": true}` | herdr backend layout (see below) |
| `desenvolvimento` | none | development method: default authorisations and PR closing (see below) |
| `userName` | `user` | name the scripts' warnings use for you; empty or non-string falls back to `user` |

`sources` must be a list; malformed values stop with a one-line message.

`spRoot` and `docsRoot` are relative to the project root. `init` and `status` follow `spRoot` too; when `docsRoot` is not set, DR/DP folders sit next to the stories.

### `desenvolvimento`

Names the project's development method; without it nothing changes (every commit/push/PR still asks). `kaizen init --metodo <m>` writes it and never overwrites an existing one.

```json
{ "desenvolvimento": { "metodo": "worktree-pr", "ramo_principal": "main", "merge_estrategia": "squash" } }
```

| Method | commit / push / pr | `pr_vigia` | `pr_merge` | Closing |
|---|---|---|---|---|
| `worktree-pr` | `auto` / `auto` / `auto` | `true` | `auto-se-verde` | push, PR, `pr_fechar.py` watches and merges only with every check green |
| `worktree-merge` | `auto` / `nunca` / `nunca` | `false` | `nunca` | local merge into the main branch |
| `direto` | `pergunta` x3 | `false` | `pergunta` | current behaviour |

Optional overrides: `commit`, `push`, `pr` (`auto|pergunta|nunca`), `pr_vigia` (bool), `pr_merge` (`auto-se-verde|pergunta|nunca`), `merge_estrategia` (`squash|merge|rebase`), `ramo_principal` (default `main`).

Precedence: SP frontmatter > `desenvolvimento` > `pergunta`. Safety guard: the `auto` values only hold with HEAD outside `ramo_principal` (and main/master); on the main branch they fall back to `pergunta`. `restricoes` and `permitir` of the SP still win. Failed checks, conflicts or a requested review block the SP with the reason; `--admin` is never used.

### `test.cmd`

`kaizen init` looks for the target project's test command by reading manifest files only (it never runs anything and never reads `.env` or secrets), first match wins:

| File | `test.cmd` |
|---|---|
| `package.json` with a real `scripts.test` | `npm test` |
| `pytest.ini`, or `pyproject.toml` with `[tool.pytest...]` | `pytest` |
| `Cargo.toml` | `cargo test` |
| `go.mod` | `go test ./...` |

The value is saved in `kaizen.config.json` (the file is created if missing) and you can edit it freely: a repeated `init` never overwrites an existing `test.cmd`, and keeps all other keys. Nothing is written when no test command is detected, or when the config is not valid JSON.

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

### `painelBackend`

Where `sp-handoff --spawn` opens the new session (`sp-fila --concorrencia N` and `sp-autor.py` open their panes through the same backend):

| Value | Behaviour |
|---|---|
| `auto` (default) | detects the multiplexer the agent runs in: WezTerm, then tmux |
| `wezterm`, `tmux` | forces that multiplexer (the executable must be on `PATH`) |
| `background` | no terminal: each session is a detached `claude -p "/michi --auto <slug>"` process with its log in `~/.claude/sp-fila-paineis/<pid>.log`; the state is the PID |

`background` is never picked by `auto`; set it explicitly. With no usable backend, `sp-fila --concorrencia` prints a one-line warning saying what is missing and runs the queue sequentially. Any other value falls back to `auto`.

### `herdr`

Layout of the herdr backend (herdr is also picked by `auto`, before WezTerm and tmux):

| Key | Default | Behaviour |
|---|---|---|
| `maxPanesPorTab` | `2` | a new pane splits to the right only while the launching tab has fewer panes than this; otherwise it opens in a new tab |
| `workspacePorProjeto` | `true` | each repo gets one herdr workspace (label = repo name, reused if it exists, created otherwise); a git worktree uses the workspace of its main repo. `false` keeps the launching pane's workspace |

Invalid values (non-integer or below 1, non-boolean) fall back to the defaults.

The queue (`/sp-fila`) and the handoff (`handoff --spawn`) share one herdr layer, `core/scripts/herdr_ops.py`: new pane, `claude` as agent, prompt by `herdr agent prompt` (no screen scraping).

End-to-end check of the herdr engine (isolated herdr session, 2 projects, 3 panes, cap and resume; never touches the default session): `python -I core/scripts/herdr-e2e-multiprojeto.py --isolado`.
