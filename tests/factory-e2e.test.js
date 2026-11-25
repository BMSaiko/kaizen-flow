"use strict";
// e2e da software factory: `kaizen demo --factory` percorre VISION -> SPs -> gates -> merge -> release com fakes determinísticos, sem rede.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const KZ = path.join(__dirname, "..", "bin", "kaizen.js");
const demo = (...a) => spawnSync("node", [KZ, "demo", ...a], { encoding: "utf8", timeout: 110000 });

test("demo --factory prova o ciclo da factory e as três paragens esperadas", () => {
  const t0 = Date.now();
  const r = demo("--factory", "--keep");
  assert.strictEqual(r.status, 0, r.stderr + r.stdout);
  assert.ok(Date.now() - t0 < 120000, "demora mais de 2 min");
  const m = /^demo: (.+)$/m.exec(r.stdout);
  assert.ok(m, `sem linha 'demo: <dir>':\n${r.stdout}`);
  const dir = m[1].trim();
  try {
    for (const fase of ["projeto", "visao", "decompor", "gates", "factory", "gate-vermelho", "orcamento", "release", "publish-recusado"]) {
      assert.match(r.stdout, new RegExp(`\\[${fase}\\]`), `falta a fase ${fase}`);
    }
    assert.match(r.stdout, /gate vermelho .* correção/i);
    assert.match(r.stdout, /paragem: orcamento/);
    assert.match(r.stdout, /paragem: release/);
    assert.match(r.stdout, /rc 3.*sem --confirmo|sem --confirmo.*rc 3/i);
    assert.ok(fs.existsSync(path.join(dir, "VISION.md")));
    assert.ok(fs.existsSync(path.join(dir, "design", "tokens.json")));
    const log = fs.readFileSync(path.join(dir, ".kaizen", "factory", "factory.log.jsonl"), "utf8");
    assert.match(log, /"evento": "fim"/);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("demo --factory sem --keep apaga o diretório e recusa combinações inválidas", () => {
  const r = demo("--factory");
  assert.strictEqual(r.status, 0, r.stderr + r.stdout);
  const m = /^demo: (.+)$/m.exec(r.stdout);
  assert.ok(m && !fs.existsSync(m[1].trim()), "diretório não foi apagado");
  const bad = demo("--factory", "--nada");
  assert.notStrictEqual(bad.status, 0);
});
