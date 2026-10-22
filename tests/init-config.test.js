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
