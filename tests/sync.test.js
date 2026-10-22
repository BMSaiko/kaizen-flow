"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");
const { plan, overlay, SKILLS } = require("../bin/sync.js");

const KZ = path.join(__dirname, "..", "bin", "kaizen.js");
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), "kaizen-sync-"));
const put = (root, rel, data = "x") => { fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true }); fs.writeFileSync(path.join(root, rel), data); };

function fakeVault() {
  const v = tmp();
  for (const s of SKILLS) put(v, `.claude/skills/${s}/SKILL.md`);
  for (const c of ["sp", "sp-list", "sp-handoff", "one-shot", "handoff"]) put(v, `.claude/commands/${c}.md`);
  for (const s of ["context-guard", "handoff", "skill-cut", "kaizen_config", "test_michi_tree_close", "sp-list", "sp-move"]) put(v, `scripts/${s}.py`);
  return v;
}

test("sync sem fonte falha com mensagem clara e não toca em core/", () => {
  const before = fs.readdirSync(path.join(__dirname, "..", "core"));
  const r = spawnSync("node", [KZ, "sync"], { encoding: "utf8", env: { ...process.env, KAIZEN_SOURCE: path.join(tmp(), "nao-existe") } });
  assert.strictEqual(r.status, 1);
  assert.match(r.stderr, /fonte do sync não existe/);
  assert.deepStrictEqual(fs.readdirSync(path.join(__dirname, "..", "core")), before);
});

test("plan apanha scripts sp-/doc- novos e o teste correspondente sem tocar em listas", () => {
  const v = fakeVault();
  put(v, "scripts/sp-novo.py");
  put(v, "scripts/test_sp_novo.py");
  put(v, "scripts/doc-novo.py");
  const { parts, missing, unlisted } = plan(v);
  const dsts = parts.map((p) => p[1]);
  for (const f of ["scripts/sp-novo.py", "scripts/test_sp_novo.py", "scripts/doc-novo.py"]) assert.ok(dsts.includes(f), f);
  assert.deepStrictEqual(missing, []);
  assert.deepStrictEqual(unlisted, []);
});

test("plan lista peças em falta e avisa de scripts relacionados fora do pacote", () => {
  const v = fakeVault();
  fs.rmSync(path.join(v, "scripts", "handoff.py"));
  fs.rmSync(path.join(v, ".claude", "skills", "swot"), { recursive: true });
  put(v, "scripts/handoff-extra.py");
  put(v, "scripts/limpa-cache.py");
  const { missing, unlisted } = plan(v);
  assert.deepStrictEqual(missing.sort(), [".claude/skills/swot", "scripts/handoff.py"]);
  assert.deepStrictEqual(unlisted, ["scripts/handoff-extra.py"]);
});

test("overlay sobrepõe a tradução e assinala fonte alterada", () => {
  const core = tmp();
  const tr = tmp();
  put(core, "skills/a/SKILL.md", "original");
  put(tr, "skills/a/SKILL.md", "translated");
  let r = overlay(core, tr, false);
  assert.deepStrictEqual(r, { stale: [], orphans: [] });
  assert.strictEqual(fs.readFileSync(path.join(core, "skills/a/SKILL.md"), "utf8"), "translated");
  put(core, "skills/a/SKILL.md", "original v2");
  r = overlay(core, tr, false);
  assert.deepStrictEqual(r.stale, ["skills/a/SKILL.md"]);
  put(tr, "skills/gone/SKILL.md", "orphan");
  assert.deepStrictEqual(overlay(core, tr, true).orphans, ["skills/gone/SKILL.md"]);
});

test("sync --check sai 0 com core/ em dia e 1 quando o vault mudou, sem tocar em core/", () => {
  // cópia do pacote: o teste escreve em core/ e os outros ficheiros de teste correm em paralelo
  const pkg = tmp();
  const root = path.join(__dirname, "..");
  for (const d of ["bin", "adapters", "core"]) fs.cpSync(path.join(root, d), path.join(pkg, d), { recursive: true });
  const kz = path.join(pkg, "bin", "kaizen.js");
  const v = fakeVault();
  const env = { ...process.env, KAIZEN_SOURCE: v };
  assert.strictEqual(spawnSync("node", [kz, "sync"], { encoding: "utf8", env }).status, 0);
  const ok = spawnSync("node", [kz, "sync", "--check"], { encoding: "utf8", env });
  assert.strictEqual(ok.status, 0, ok.stdout + ok.stderr);
  put(v, ".claude/skills/michi/SKILL.md", "alterado");
  const f = path.join(pkg, "core", "skills", "michi", "SKILL.md");
  const before = fs.readFileSync(f, "utf8");
  const stale = spawnSync("node", [kz, "sync", "--check"], { encoding: "utf8", env });
  assert.strictEqual(stale.status, 1);
  assert.match(stale.stdout, /skills\/michi\/SKILL\.md/);
  assert.strictEqual(fs.readFileSync(f, "utf8"), before);
});

test("owns() reconhece caminhos do vault que entram no sync", () => {
  const { owns } = require("../bin/sync.js");
  assert.ok(owns(".claude/skills/michi/SKILL.md"));
  assert.ok(owns("scripts/sp-move.py"));
  assert.ok(owns(".claude/commands/sp.md"));
  assert.ok(!owns("scripts/outro-guard.py"));
  assert.ok(!owns("knowledge/projects/p/sp/TODO/x.md"));
});
