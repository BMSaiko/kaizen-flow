-- kaizen term: WezTerm keys and menu (opt-in example, kaizen init never edits your config).
-- Install: copy this file to <wezterm config>/lib/kaizen_term.lua, then in wezterm.lua:
--   local kt = require 'lib.kaizen_term'
--   config.keys = config.keys or {}
--   for _, k in ipairs(kt.apply(config)) do table.insert(config.keys, k) end
-- Keys: Ctrl+Shift+E opens a menu; F2 then l/f/m/x/r/o runs a sub-command directly
-- (? inside F2 opens the menu, Esc cancels). Win+Space and Ctrl+Alt are reserved on Windows.
local wezterm = require 'wezterm'
local act = wezterm.action
local M = {}

-- shell used to run `kaizen`; adjust if you do not use PowerShell
local SHELL = { 'pwsh', '-NoLogo', '-NoExit', '-Command' }
-- folder of the project where `kaizen term` should run (nil = WezTerm default cwd)
local PROJECT_DIR = nil

-- sub-command -> { key, label }
local ITEMS = {
  { sub = 'ls',      key = 'l', label = 'ls: list SPs and panes' },
  { sub = 'fila',    key = 'f', label = 'fila: pick a program and run its queue' },
  { sub = 'michi',   key = 'm', label = 'michi: pick a SP and launch its michi' },
  { sub = 'limpar',  key = 'x', label = 'limpar: orphan panes (dry-run)' },
  { sub = 'retomar', key = 'r', label = 'retomar: reopen the pane of a Doing SP' },
  { sub = 'orq',     key = 'o', label = 'orq: orchestrator pane' },
}

-- new tab running `kaizen term <sub>`; -NoExit keeps the output readable
local function run(sub)
  local args = {}
  for _, a in ipairs(SHELL) do table.insert(args, a) end
  table.insert(args, 'kaizen term ' .. sub)
  return act.SpawnCommandInNewTab { cwd = PROJECT_DIR, args = args }
end

function M.menu()
  return wezterm.action_callback(function(window, pane)
    local choices = {}
    for _, it in ipairs(ITEMS) do
      table.insert(choices, { id = it.sub, label = it.label })
    end
    window:perform_action(act.InputSelector {
      title = 'kaizen term',
      choices = choices,
      fuzzy = true,
      action = wezterm.action_callback(function(win, p, id)
        if id then win:perform_action(run(id), p) end
      end),
    }, pane)
  end)
end

-- returns the entries for config.keys and fills config.key_tables
function M.apply(config)
  local table_keys = { { key = 'Escape', action = act.PopKeyTable } }
  for _, it in ipairs(ITEMS) do
    table.insert(table_keys, { key = it.key, action = act.Multiple { act.PopKeyTable, run(it.sub) } })
  end
  table.insert(table_keys, { key = '?', action = act.Multiple { act.PopKeyTable, M.menu() } })
  config.key_tables = config.key_tables or {}
  config.key_tables.kaizen_term = table_keys
  return {
    { key = 'F2', action = act.ActivateKeyTable {
        name = 'kaizen_term', one_shot = true, timeout_milliseconds = 4000, replace_current = true } },
    { key = 'E', mods = 'CTRL|SHIFT', action = M.menu() },
  }
end

return M
