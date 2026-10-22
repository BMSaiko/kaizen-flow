"use strict";

// painel injetável (CLI em multiplexer) ou não (app desktop / terminal simples: handoff por clipboard)
function detectMode(env = process.env) {
  if (env.WEZTERM_PANE) return { mode: "cli", backend: "wezterm" };
  if (env.TMUX_PANE) return { mode: "cli", backend: "tmux" };
  return { mode: "app", backend: "clipboard" };
}

module.exports = { detectMode };
