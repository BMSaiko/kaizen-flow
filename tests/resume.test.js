"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const BIN = path.join(__dirname, "..", "bin", "kaizen.js");
const { kaizen } = require("./helpers/sandbox");
const run = (cwd, ...a) => kaizen(a, { cwd });

function repo() {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "kaizen-resume-"));
  assert.strictEqual(run(d, "init", d, "--harness", "claude").status, 0);
  return d;
}

test("init instala sp-resume.py", () => {
  assert.ok(fs.existsSync(path.join(repo(), "scripts", "sp-resume.py")));
});

test("resume sem órfãos: rc 0 «nada a retomar»", () => {
  const r = run(repo(), "resume");
  assert.strictEqual(r.status, 0);
  assert.match(r.stdout, /nada a retomar/);
});

test("resume <slug> --from fase inválida: rc 2", () => {
  const r = run(repo(), "resume", "um-slug", "--from", "xx");
  assert.strictEqual(r.status, 2);
  assert.match(r.stderr, /fase inv.lida/);
});

test("uso do kaizen menciona resume", () => {
  const r = run(os.tmpdir());
  assert.match(r.stdout, /resume/);
});
