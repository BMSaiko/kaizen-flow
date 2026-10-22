"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");
const { detectMode } = require("../bin/mode.js");

test("detectMode: multiplexer = CLI com painel", () => {
  assert.deepStrictEqual(detectMode({ WEZTERM_PANE: "3" }), { mode: "cli", backend: "wezterm" });
  assert.deepStrictEqual(detectMode({ TMUX_PANE: "%1" }), { mode: "cli", backend: "tmux" });
});

test("detectMode: sem painel = app/terminal simples, handoff por clipboard", () => {
  assert.deepStrictEqual(detectMode({}), { mode: "app", backend: "clipboard" });
});

test("doctor imprime o modo detetado", () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "kaizen-mode-"));
  const run = (...a) => spawnSync("node", [path.join(__dirname, "..", "bin", "kaizen.js"), ...a], { encoding: "utf8", env: { ...process.env, WEZTERM_PANE: "", TMUX_PANE: "" } });
  run("init", d, "--harness", "codex");
  const r = run("doctor", d, "--harness", "codex");
  assert.strictEqual(r.status, 0);
  assert.match(r.stdout, /handoff: app \(clipboard\)/);
});
