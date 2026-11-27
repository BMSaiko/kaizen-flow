"use strict";
const test = require("node:test");
const assert = require("node:assert");
const { loadCore } = require("../bin/core.js");

const core = loadCore();
const scripts = new Set(core.filter((f) => f.rel.startsWith("scripts/")).map((f) => f.rel.slice("scripts/".length)));
// scripts fora de core/scripts que o core/ cita como opcionais (test-fast.py do vault; kaizen_usage.py vive em usage/ e o orçamento ignora-o se faltar)
const OPTIONAL = new Set(["test-fast.py", "kaizen_usage.py", "skill-fase-aviso.py"]);

test("todo o script .py referido em core/ existe em core/scripts", () => {
  const missing = [];
  for (const f of core) {
    if (!/\.(md|py)$/.test(f.rel)) continue;
    for (const m of f.data.toString("utf8").matchAll(/(?:scripts\/)?(?<![\w-])((?:sp|doc|handoff|context|skill|kaizen|test)[a-z0-9_-]*\.py)\b/g)) {
      if (!scripts.has(m[1]) && !OPTIONAL.has(m[1])) missing.push(`${f.rel}: ${m[1]}`);
    }
  }
  assert.deepStrictEqual([...new Set(missing)], []);
});

test("o guard de contexto para conversa livre aponta para um script que existe", () => {
  const guard = core.find((f) => f.rel === "scripts/context-guard.py").data.toString("utf8");
  assert.ok(guard.includes("handoff.py"));
  assert.ok(scripts.has("handoff.py"));
});

// Referências pendentes: todo o `scripts/<nome>.py` e toda a skill/comando `/<nome>` citados nas
// skills e comandos do pacote existem em core/, salvo as exceções abaixo (cada uma é citada com
// formulação condicional «se existir» / «só no vault» nos ficheiros de origem).
const docs = core.filter((f) => /^(skills|commands)\//.test(f.rel) && /\.md$/.test(f.rel));
const skillNames = new Set(core.filter((f) => /^skills\/[^/]+\/SKILL\.md$/.test(f.rel)).map((f) => f.rel.split("/")[1]));
const commandNames = new Set(core.filter((f) => /^commands\/[^/]+\.md$/.test(f.rel)).map((f) => f.rel.slice("commands/".length, -3)));

// scripts do vault, fora do pacote (sb-worktree.py e o guard de worktree são específicos do vault)
const VAULT_SCRIPTS = new Set(["sb-worktree.py", "sb.py", "test-fast.py"]);
// skills e comandos do vault, opcionais no pacote (o michi diz o que fazer sem eles)
const VAULT_SKILLS = new Set(["reflect", "report", "commit-msg", "commit"]);
// comandos do harness (Claude Code) e do vault que o pacote cita sem os trazer
const HARNESS = new Set(["clear", "usage", "compact", "model", "kaizen-sync", "quit", "help", "stop", "rename", "resume"]);
// falsos positivos: caminhos e exemplos em prosa, não comandos
const NOT_COMMANDS = new Set(["ausente", "reflog", "tmp", "login"]);

test("todo o scripts/<nome>.py citado em skills e comandos existe em core/scripts ou é do vault", () => {
  const missing = [];
  for (const f of docs) {
    for (const m of f.data.toString("utf8").matchAll(/scripts\/([A-Za-z0-9_-]+\.py)\b/g)) {
      if (!scripts.has(m[1]) && !VAULT_SCRIPTS.has(m[1])) missing.push(`${f.rel}: ${m[1]}`);
    }
  }
  assert.deepStrictEqual([...new Set(missing)], []);
});

test("toda a skill ou comando /<nome> citado existe em core/ ou é do vault/harness", () => {
  const missing = [];
  for (const f of docs) {
    for (const m of f.data.toString("utf8").matchAll(/(?:^|[\s`(|])\/([a-z][a-z0-9-]+)(?=[\s`)|:,.;]|$)/gm)) {
      const n = m[1];
      if (!skillNames.has(n) && !commandNames.has(n) && !VAULT_SKILLS.has(n) && !HARNESS.has(n) && !NOT_COMMANDS.has(n)) missing.push(`${f.rel}: /${n}`);
    }
  }
  assert.deepStrictEqual([...new Set(missing)], []);
});

test("as exceções do vault não escondem scripts que o pacote já traz", () => {
  for (const s of VAULT_SCRIPTS) if (s !== "test-fast.py") assert.ok(!scripts.has(s), `${s} já está em core/scripts`);
  for (const s of VAULT_SKILLS) assert.ok(!skillNames.has(s) && !commandNames.has(s), `/${s} já está em core/`);
});
