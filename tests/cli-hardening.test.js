"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const BIN = path.join(__dirname, "..", "bin", "kaizen.js");
const run = (...a) => spawnSync("node", [BIN, ...a], { encoding: "utf8", env: { ...process.env, WEZTERM_PANE: "", TMUX_PANE: "" } });
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), "kaizen-hard-"));

test("harness inválido ou em falta aborta sem escrever", () => {
  const d = tmp();
  for (const args of [["init", d, "--harness", "foo"], ["init", d, "--harness"]]) {
    const r = run(...args);
    assert.strictEqual(r.status, 1, args.join(" "));
    assert.match(r.stderr, /--harness/);
  }
  assert.deepStrictEqual(fs.readdirSync(d), []);
});

test("settings.json inválido aborta antes de escrever e não é alterado", () => {
  const d = tmp();
  fs.mkdirSync(path.join(d, ".claude"));
  const bad = path.join(d, ".claude", "settings.json");
  fs.writeFileSync(bad, "{ not json");
  const r = run("init", d, "--harness", "claude");
  assert.notStrictEqual(r.status, 0);
  assert.strictEqual(fs.readFileSync(bad, "utf8"), "{ not json");
  assert.ok(!fs.existsSync(path.join(d, ".claude", "skills")));
});

test("init num caminho que é um ficheiro falha com rc≠0", () => {
  const d = tmp();
  const f = path.join(d, "file.txt");
  fs.writeFileSync(f, "x");
  assert.notStrictEqual(run("init", f, "--harness", "codex").status, 0);
  assert.strictEqual(fs.readFileSync(f, "utf8"), "x");
});

test("doctor falha numa instalação em falta e --fix repõe sem sobrescrever", () => {
  const d = tmp();
  assert.notStrictEqual(run("doctor", d, "--harness", "codex").status, 0);
  assert.strictEqual(run("doctor", d, "--harness", "codex", "--fix").status, 0);
  const agents = path.join(d, "AGENTS.md");
  fs.appendFileSync(agents, "\nminha nota\n");
  const before = fs.readFileSync(agents, "utf8");
  assert.strictEqual(run("doctor", d, "--harness", "codex", "--fix").status, 0);
  assert.strictEqual(fs.readFileSync(agents, "utf8"), before);
});
