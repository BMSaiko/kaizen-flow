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

for (const h of ["claude", "codex", "agents-md", "opencode", "cursor", "gemini"]) {
  test(`init --harness ${h}: instala, doctor ok, segunda execução não altera`, () => {
    const d = tmp();
    assert.strictEqual(kz("init", d, "--harness", h).status, 0);
    const before = tree(d);
    assert.ok(Object.keys(before).some((k) => k.endsWith("michi/SKILL.md")));
    assert.strictEqual(kz("doctor", d, "--harness", h).status, 0);
    assert.strictEqual(kz("init", d, "--harness", h).status, 0);
    assert.deepStrictEqual(tree(d), before);
    if (h === "claude") assert.ok(before[".claude/settings.json"]);
    else if (h === "gemini") assert.ok(Buffer.from(before["GEMINI.md"], "base64").toString().includes("Kaizen flow") && !before["AGENTS.md"]);
    else if (h === "cursor") assert.ok(Buffer.from(before[".cursor/rules/kaizen-flow.mdc"], "base64").toString().includes("alwaysApply: true"));
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

test("opencode: skills em .opencode/skills, comandos em .opencode/commands, bloco em AGENTS.md", () => {
  const { files, agents } = require("../adapters/opencode").render(loadCore());
  assert.ok(files.some((f) => f.path === ".opencode/skills/michi/SKILL.md"));
  assert.ok(files.some((f) => f.path === ".opencode/commands/sp.md"));
  assert.ok(files.some((f) => f.path === "scripts/sp-list.py"));
  assert.ok(agents.includes(".opencode/skills/michi/SKILL.md"));
  assert.ok(agents.includes("sp-handoff.py --launch"));
});

test("cursor: skills em .cursor/skills, regra .mdc sempre aplicada, sem AGENTS.md", () => {
  const { files, agents } = require("../adapters/cursor").render(loadCore());
  assert.ok(files.some((f) => f.path === ".cursor/skills/michi/SKILL.md"));
  assert.ok(files.some((f) => f.path === ".kaizen/commands/sp.md"));
  assert.ok(files.some((f) => f.path === "scripts/sp-list.py"));
  const rule = files.find((f) => f.path === ".cursor/rules/kaizen-flow.mdc");
  assert.ok(rule);
  const t = rule.data.toString();
  assert.ok(t.startsWith("---" + String.fromCharCode(10)));
  assert.ok(t.includes("alwaysApply: true"));
  assert.ok(t.includes(".cursor/skills/michi/SKILL.md"));
  assert.ok(t.includes("sp-handoff.py --launch"));
  assert.strictEqual(agents, undefined);
});

test("gemini: skills em .gemini/skills, comandos TOML em .gemini/commands, bloco em GEMINI.md", () => {
  const core = loadCore();
  const { files, agents, agentsFile } = require("../adapters/gemini").render(core);
  assert.strictEqual(agentsFile, "GEMINI.md");
  assert.ok(files.some((f) => f.path === ".gemini/skills/michi/SKILL.md"));
  assert.ok(files.some((f) => f.path === "scripts/sp-list.py"));
  assert.ok(!files.some((f) => f.path.startsWith(".gemini/commands/") && !f.path.endsWith(".toml")));
  const cmd = files.find((f) => f.path === ".gemini/commands/sp.toml");
  assert.ok(cmd);
  const t = cmd.data.toString();
  assert.match(t, /^description = "/m);
  assert.match(t, /^prompt = "/m);
  assert.ok(t.includes("{{args}}") && !t.includes("$ARGUMENTS"));
  assert.ok(agents.includes(".gemini/skills/michi/SKILL.md"));
});

test("gemini: o prompt TOML preserva o corpo do comando (aspas, quebras e unicode)", () => {
  const src = '---\ndescription: Olá "mundo"\nargument-hint: "[x]"\n---\nLinha 1\nUsa \\ e "aspas" $ARGUMENTS ção\n';
  const core = [{ rel: "commands/x.md", data: Buffer.from(src) }];
  const { files } = require("../adapters/gemini").render(core);
  const t = files.find((f) => f.path === ".gemini/commands/x.toml").data.toString();
  const get = (k) => JSON.parse(t.split("\n").find((l) => l.startsWith(k + " = ")).slice(k.length + 3));
  assert.strictEqual(get("description"), 'Olá "mundo"');
  assert.strictEqual(get("prompt"), 'Linha 1\nUsa \\ e "aspas" {{args}} ção');
});
