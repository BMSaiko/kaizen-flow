"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { audit, PATTERNS } = require("../bin/audit.js");

function tmp() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "kaizen-audit-"));
}

test("repo limpo passa", () => {
  const d = tmp();
  fs.writeFileSync(path.join(d, "a.md"), "# Hello\nplain text\n");
  assert.deepStrictEqual(audit(d), []);
});

test("cada padrão proibido plantado é detetado", () => {
  for (const [name, sample] of [
    ["bruno", "owner: Bruno"],
    ["heimdall", "HEIMDALL guard"],
    ["windows-user-path", "C:\\Users\\someone\\x"],
    ["wikilink", "see [[note]]"],
    ["verbose-guard", "verbose-guard.py"],
    ["email", "contact: someone@example.com"],
    ["token", "key = sk-abcdefghijklmnop1234"],
    ["token", "ghp_abcdefghijklmnopqrstuvwx"],
    ["private-key", "-----BEGIN RSA PRIVATE KEY-----"],
  ]) {
    const d = tmp();
    fs.writeFileSync(path.join(d, "f.md"), sample);
    const hits = audit(d);
    assert.ok(hits.some((h) => h.pattern === name), `não detetou ${name}`);
  }
  assert.strictEqual(PATTERNS.length, 8);
});

test("ignora node_modules e .git", () => {
  const d = tmp();
  fs.mkdirSync(path.join(d, "node_modules"));
  fs.writeFileSync(path.join(d, "node_modules", "x.md"), "bruno");
  assert.deepStrictEqual(audit(d), []);
});
