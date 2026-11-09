"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const KZ = path.join(__dirname, "..", "bin", "kaizen.js");
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), "kaizen-cfg-"));
const init = (d) => spawnSync("node", [KZ, "init", d, "--harness", "agents-md"], { encoding: "utf8" });
const has = (d, rel) => fs.existsSync(path.join(d, rel));

test("init sem config usa as pastas por defeito", () => {
  const d = tmp();
  assert.strictEqual(init(d).status, 0);
  for (const k of ["sp", "dr", "dp"]) assert.ok(has(d, `knowledge/projects/kaizen/_default/${k}/Doing`));
});

test("init segue spRoot e docsRoot de kaizen.config.json", () => {
  const d = tmp();
  fs.writeFileSync(path.join(d, "kaizen.config.json"), JSON.stringify({ spRoot: "work/stories", docsRoot: "work/docs" }));
  assert.strictEqual(init(d).status, 0);
  assert.ok(has(d, "work/stories/_default/sp/TODO"));
  assert.ok(has(d, "work/docs/_default/dr/Done"));
  assert.ok(has(d, "work/docs/_default/dp/Doing"));
  assert.ok(!has(d, "knowledge"));
});

test("spRoot fora do repo ou inválido volta ao defeito", () => {
  const d = tmp();
  fs.writeFileSync(path.join(d, "kaizen.config.json"), JSON.stringify({ spRoot: `../${path.basename(d)}-fora`, docsRoot: 7 }));
  assert.strictEqual(init(d).status, 0);
  assert.ok(has(d, "knowledge/projects/kaizen/_default/sp/TODO"));
  assert.ok(!fs.existsSync(`${d}-fora`));
});

test("config com JSON inválido não impede o init", () => {
  const d = tmp();
  fs.writeFileSync(path.join(d, "kaizen.config.json"), "{ nope");
  assert.strictEqual(init(d).status, 0);
  assert.ok(has(d, "knowledge/projects/kaizen/_default/sp/Doing"));
});

test("doctor avisa que codex e agents-md não têm hook de contexto; claude não", () => {
  for (const [h, expected] of [["codex", true], ["agents-md", true], ["claude", false]]) {
    const d = tmp();
    spawnSync("node", [KZ, "init", d, "--harness", h], { encoding: "utf8" });
    const r = spawnSync("node", [KZ, "doctor", d, "--harness", h], { encoding: "utf8" });
    assert.strictEqual(r.status, 0, r.stdout + r.stderr);
    assert.strictEqual(/context hook: none/.test(r.stdout), expected, h);
  }
});

const cfgOf = (d) => JSON.parse(fs.readFileSync(path.join(d, "kaizen.config.json"), "utf8"));
const write = (d, rel, data) => fs.writeFileSync(path.join(d, rel), data);

test("init deteta o comando de testes pelos manifestos", () => {
  const casos = [
    ["package.json", JSON.stringify({ scripts: { test: "vitest" } }), "npm test"],
    ["pytest.ini", "[pytest]\n", "pytest"],
    ["pyproject.toml", "[tool.pytest.ini_options]\naddopts = \"-q\"\n", "pytest"],
    ["Cargo.toml", "[package]\nname = \"x\"\n", "cargo test"],
    ["go.mod", "module x\n", "go test ./..."],
  ];
  for (const [file, data, cmd] of casos) {
    const d = tmp();
    write(d, file, data);
    assert.strictEqual(init(d).status, 0);
    assert.strictEqual(cfgOf(d).test.cmd, cmd, file);
  }
});

test("projeto sem testes não cria config nem chave test", () => {
  const d = tmp();
  write(d, "package.json", JSON.stringify({ scripts: { build: "tsc" } }));
  assert.strictEqual(init(d).status, 0);
  assert.ok(!has(d, "kaizen.config.json"));
  const e = tmp();
  assert.strictEqual(init(e).status, 0);
  assert.ok(!has(e, "kaizen.config.json"));
});

test("init repetido nunca sobrescreve test.cmd manual e preserva as outras chaves", () => {
  const d = tmp();
  write(d, "package.json", JSON.stringify({ scripts: { test: "vitest" } }));
  write(d, "kaizen.config.json", JSON.stringify({ spRoot: "work/stories", test: { cmd: "make check", extra: 1 } }));
  assert.strictEqual(init(d).status, 0);
  assert.strictEqual(init(d).status, 0);
  assert.deepStrictEqual(cfgOf(d), { spRoot: "work/stories", test: { cmd: "make check", extra: 1 } });
});

test("deteção acrescenta test.cmd a uma config existente sem perder chaves", () => {
  const d = tmp();
  write(d, "Cargo.toml", "[package]\n");
  write(d, "kaizen.config.json", JSON.stringify({ userName: "Ana" }));
  assert.strictEqual(init(d).status, 0);
  assert.deepStrictEqual(cfgOf(d), { userName: "Ana", test: { cmd: "cargo test" } });
});

test("config com JSON inválido não é reescrita pela deteção", () => {
  const d = tmp();
  write(d, "go.mod", "module x\n");
  write(d, "kaizen.config.json", "{ nope");
  assert.strictEqual(init(d).status, 0);
  assert.strictEqual(fs.readFileSync(path.join(d, "kaizen.config.json"), "utf8"), "{ nope");
});

test("a deteção não executa nada nem lê .env", () => {
  const d = tmp();
  write(d, "package.json", JSON.stringify({ scripts: { test: "node -e \"require('fs').writeFileSync('pwned','x')\"" } }));
  write(d, ".env", "SEGREDO=1\n");
  assert.strictEqual(init(d).status, 0);
  assert.ok(!has(d, "pwned"));
});

test("doctor --harness codex: hook ligado, ausente e sem config", () => {
  const d = tmp();
  spawnSync("node", [KZ, "init", d, "--harness", "codex"], { encoding: "utf8" });
  const cfg = path.join(d, "codex-config.toml");
  const out = (extra) => spawnSync("node", [KZ, "doctor", d, "--harness", "codex", "--codex-config", cfg], { encoding: "utf8", ...extra }).stdout;
  assert.match(out(), /context hook: none, degradado \(sem config/);
  fs.writeFileSync(cfg, "model = \"x\"\n");
  assert.match(out(), /context hook: none, degradado \(context-guard ausente/);
  fs.writeFileSync(cfg, "[hooks]\ncommand = \"python -I scripts/context-guard.py\"\n");
  assert.match(out(), /context hook: ligado/);
});
