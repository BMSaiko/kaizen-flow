# `kaizen term` keys in WezTerm

Optional shortcuts to run `kaizen term <sub>` without typing. They live in your WezTerm config; `kaizen init` never edits it.

## Install

1. Copy [`wezterm-term.lua`](wezterm-term.lua) to `<wezterm config>/lib/kaizen_term.lua`.
2. In `wezterm.lua`:

```lua
local kt = require 'lib.kaizen_term'
config.keys = config.keys or {}
for _, k in ipairs(kt.apply(config)) do table.insert(config.keys, k) end
```

3. Set `PROJECT_DIR` (the project where `kaizen term` should run) and `SHELL` at the top of the file if the defaults do not fit. WezTerm reloads the config on save.

## Keys

| Keys | Action |
|---|---|
| `Ctrl+Shift+E` | Menu (fuzzy search) with all sub-commands |
| `F2`, then `l` | `kaizen term ls` |
| `F2`, then `f` | `kaizen term fila` |
| `F2`, then `m` | `kaizen term michi` |
| `F2`, then `x` | `kaizen term limpar` (dry-run) |
| `F2`, then `r` | `kaizen term retomar` |
| `F2`, then `o` | `kaizen term orq` |
| `F2`, then `?` | Same menu; `Esc` cancels |

Each action opens a new tab with `-NoExit`, so the output stays readable. The `F2` table times out after 4 seconds.

## Why not Win+Space or Ctrl+Alt

- `Win+Space` is reserved by Windows (input language switch); WezTerm never receives it.
- `Ctrl+Alt+<key>` is AltGr on many Windows keyboard layouts, so it types characters instead of firing the binding.

`Ctrl+Shift+E` and the `F2` table avoid both.

## Safety

The keys only start `kaizen term <sub>`; the confirmations of `fila`, `michi`, `limpar` and `retomar` still apply (see [commands](commands.md)).
