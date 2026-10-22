"use strict";
const test = require("node:test");
const assert = require("node:assert");
const { loadCore } = require("../bin/core.js");

const core = loadCore();
const scripts = new Set(core.filter((f) => f.rel.startsWith("scripts/")).map((f) => f.rel.slice("scripts/".length)));

test("todo o script .py referido em core/ existe em core/scripts", () => {
  const missing = [];
  for (const f of core) {
    if (!/\.(md|py)$/.test(f.rel)) continue;
    for (const m of f.data.toString("utf8").matchAll(/(?:scripts\/)?\b((?:sp|doc|handoff|context|skill|kaizen|test)[a-z0-9_-]*\.py)\b/g)) {
      if (!scripts.has(m[1])) missing.push(`${f.rel}: ${m[1]}`);
    }
  }
  assert.deepStrictEqual([...new Set(missing)], []);
});

test("o guard de contexto para conversa livre aponta para um script que existe", () => {
  const guard = core.find((f) => f.rel === "scripts/context-guard.py").data.toString("utf8");
  assert.ok(guard.includes("handoff.py"));
  assert.ok(scripts.has("handoff.py"));
});
