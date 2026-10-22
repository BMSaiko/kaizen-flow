"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");
const { loadCore } = require("../bin/core.js");

const KZ = path.join(__dirname, "..", "bin", "kaizen.js");
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), "kaizen-init-"));
const kz = (...a) => spawnSync("node", [KZ, ...a], { encoding: "utf8" });
const tree = (d) => {
  const out = {};
  (function walk(x) {
    for (const e of fs.readdirSync(x, { withFileTypes: true })) {
      const p = path.join(x, e.name);
      if (e.isDirectory()) walk(p);
      else out[path.relative(d, p).replace(/\\/g, "/")] = fs.readFileSync(p).toString("base64");
    }
  })(d);
  return out;
};

test("adaptador claude reproduz o layout .claude/ sem diferenças", () => {
  const core = loadCore();
  const { files } = require("../adapters/claude").render(core);
  assert.strictEqual(files.length, core.length);
  for (const f of files) {
    const rel = f.path.replace(/^\.claude\//, "");
    const src = core.find((c) => c.rel === rel);
    assert.ok(src, `sem origem para ${f.path}`);
    assert.ok(src.data.equals(f.data));
  }
  assert.ok(files.some((f) => f.path === ".claude/skills/michi/SKILL.md"));
  assert.ok(files.some((f) => f.path === "scripts/sp-list.py"));
});

for (const h of ["claude", "codex", "agents-md"]) {
  test(`init --harness ${h}: instala, doctor ok, segunda execução não altera`, () => {
    const d = tmp();
    assert.strictEqual(kz("init", d, "--harness", h).status, 0);
    const before = tree(d);
    assert.ok(Object.keys(before).some((k) => k.endsWith("michi/SKILL.md")));
    assert.strictEqual(kz("doctor", d, "--harness", h).status, 0);
    assert.strictEqual(kz("init", d, "--harness", h).status, 0);
    assert.deepStrictEqual(tree(d), before);
    if (h === "claude") assert.ok(before[".claude/settings.json"]);
    else assert.ok(Buffer.from(before["AGENTS.md"], "base64").toString().includes("Kaizen flow"));
  });
}

test("AGENTS.md existente é preservado e recebe o bloco", () => {
  const d = tmp();
  fs.writeFileSync(path.join(d, "AGENTS.md"), "# Mine\nkeep me\n");
  kz("init", d, "--harness", "codex");
  const t = fs.readFileSync(path.join(d, "AGENTS.md"), "utf8");
  assert.ok(t.startsWith("# Mine\nkeep me"));
  assert.ok(t.includes("Kaizen flow"));
});

test("doctor falha (rc≠0) quando falta uma peça", () => {
  const d = tmp();
  kz("init", d, "--harness", "codex");
  fs.rmSync(path.join(d, ".agents", "skills", "michi", "SKILL.md"));
  assert.notStrictEqual(kz("doctor", d, "--harness", "codex").status, 0);
});

test("harness desconhecido dá erro", () => {
  assert.notStrictEqual(kz("init", tmp(), "--harness", "nope").status, 0);
});

test("codex e agents-md avisam como fazer handoff sem hook de contexto", () => {
  for (const h of ["codex", "agents-md"]) {
    const { agents } = require(`../adapters/${h}`).render(loadCore());
    assert.ok(agents.includes("sp-handoff.py --launch"));
  }
});
