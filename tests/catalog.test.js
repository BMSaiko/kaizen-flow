"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const ROOT = path.resolve(__dirname, "..");
const CLI = path.join(ROOT, "bin", "kaizen.js");

function kaizen(args, cwd = ROOT) {
  return spawnSync(process.execPath, [CLI, "catalog", ...args], { cwd, encoding: "utf8" });
}

test("kaizen catalog --check valida o catálogo do repo", () => {
  const r = kaizen(["--check"]);
  assert.strictEqual(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stdout, /catalog --check: ok \(\d+ EC, \d+ UC\)/);
});

test("kaizen catalog --check falha com catálogo inexistente", () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "kaizen-catalog-"));
  const r = kaizen(["--check", "--file", path.join(d, "nao-existe.json")]);
  assert.strictEqual(r.status, 1);
  assert.match(r.stderr, /catálogo não encontrado/);
});

test("kaizen catalog --check falha com ID duplicado", () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "kaizen-catalog-"));
  const f = path.join(d, "catalogo.json");
  const cat = JSON.parse(fs.readFileSync(path.join(ROOT, "docs", "catalogo.json"), "utf8"));
  cat.edge_cases.push({ ...cat.edge_cases[0] });
  fs.writeFileSync(f, JSON.stringify(cat));
  const r = kaizen(["--check", "--file", f]);
  assert.strictEqual(r.status, 1);
  assert.match(r.stdout, /problema\(s\)/);
});

test("kaizen catalog report --no-run imprime EC e UC", () => {
  const r = kaizen(["report", "--no-run"]);
  assert.match(r.stdout, /^EC: \d+\/\d+ cobertos/m);
  assert.match(r.stdout, /^UC: \d+\/\d+ cobertos/m);
  assert.ok(r.status === 0 || r.status === 1, `rc inesperado: ${r.status}`);
});
