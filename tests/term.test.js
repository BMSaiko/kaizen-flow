"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const BIN = path.join(__dirname, "..", "bin", "kaizen.js");
const run = (...a) => spawnSync("node", [BIN, ...a], { encoding: "utf8", env: { ...process.env, WEZTERM_PANE: "", TMUX_PANE: "" } });

test("term --help lista ls|fila|michi|limpar|orq", () => {
  const r = run("term", "--help");
  assert.strictEqual(r.status, 0);
  for (const s of ["ls", "fila", "michi", "limpar", "orq"]) assert.match(r.stdout, new RegExp(`^  ${s}\\b`, "m"));
});

test("term sem argumentos mostra a ajuda; subcomando desconhecido falha", () => {
  assert.strictEqual(run("term").status, 0);
  const r = run("term", "xx");
  assert.strictEqual(r.status, 1);
  assert.match(r.stderr, /desconhecido/);
});

test("term limpar/orq: por implementar, rc 2", () => {
  for (const s of ["limpar", "orq"]) {
    const r = run("term", s);
    assert.strictEqual(r.status, 2, s);
    assert.match(r.stderr, /por implementar/);
  }
});

test("init instala os scripts de term (wez, painel_backend, open-doc)", () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "kaizen-term-"));
  assert.strictEqual(run("init", d, "--harness", "claude").status, 0);
  for (const f of ["wez.py", "painel_backend.py", "open-doc.py", "wez-layouts/dev.json"]) {
    assert.ok(fs.existsSync(path.join(d, "scripts", f)), f);
  }
});
