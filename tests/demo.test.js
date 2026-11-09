"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const KZ = path.join(__dirname, "..", "bin", "kaizen.js");
const demo = (...a) => spawnSync("node", [KZ, "demo", ...a], { encoding: "utf8" });

test("kaizen demo percorre o ciclo e deixa os artefactos num diretório temporário", () => {
  const r = demo("--keep");
  assert.strictEqual(r.status, 0, r.stderr + r.stdout);
  const m = /^demo: (.+)$/m.exec(r.stdout);
  assert.ok(m, `sem linha 'demo: <dir>' no output:\n${r.stdout}`);
  const dir = m[1].trim();
  try {
    assert.ok(dir.startsWith(fs.realpathSync(require("os").tmpdir())) || dir.startsWith(require("os").tmpdir()), "fora do tmp");
    for (const fase of ["init", "sp-new", "doing", "gates", "done", "report"]) assert.match(r.stdout, new RegExp(`\\[${fase}\\]`), `falta a fase ${fase}`);
    assert.ok(fs.existsSync(path.join(dir, ".git")));
    assert.ok(fs.existsSync(path.join(dir, "scripts", "sp-gates.py")));
    const done = path.join(dir, "knowledge", "projects", "kaizen", "demo", "sp", "Done");
    const sps = fs.readdirSync(done).filter((f) => f.endsWith(".md"));
    assert.strictEqual(sps.length, 1);
    assert.match(fs.readFileSync(path.join(done, sps[0]), "utf8"), /^status: Done/m);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("kaizen demo sem --keep apaga o diretório temporário", () => {
  const r = demo();
  assert.strictEqual(r.status, 0, r.stderr + r.stdout);
  const m = /^demo: (.+)$/m.exec(r.stdout);
  assert.ok(m);
  assert.ok(!fs.existsSync(m[1].trim()), "diretório não foi apagado");
});

test("kaizen demo recusa argumentos desconhecidos", () => {
  const r = demo("--nada");
  assert.notStrictEqual(r.status, 0);
});
