"use strict";
const semCache = (src) => !/[\\/](__pycache__|\.pytest_cache|\.ruff_cache|\.hypothesis)([\\/]|$)/.test(src);
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");
const { plan, overlay, SKILLS, MANIFEST } = require("../bin/sync.js");

const KZ = path.join(__dirname, "..", "bin", "kaizen.js");
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), "kaizen-sync-"));
const put = (root, rel, data = "x") => { fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true }); fs.writeFileSync(path.join(root, rel), data); };

function fakeVault() {
  const v = tmp();
  for (const s of SKILLS) put(v, `.claude/skills/${s}/SKILL.md`);
  for (const c of ["sp", "sp-list", "sp-handoff", "handoff"]) put(v, `.claude/commands/${c}.md`);
  put(v, ".claude/modelos.json", "{}");
  for (const n of MANIFEST.scriptNames) put(v, `scripts/${n}`);
  for (const d of MANIFEST.dirs) put(v, `${d}/x.txt`);
  return v;
}

test("plan inclui o conftest.py (isola o cwd dos testes) para o sync n�o o apagar", () => {
  const { parts } = plan(fakeVault());
  assert.ok(parts.map((p) => p[1]).includes("scripts/conftest.py"));
});

test("sync sem fonte falha com mensagem clara e não toca em core/", () => {
  const before = fs.readdirSync(path.join(__dirname, "..", "core"));
  const r = spawnSync("node", [KZ, "sync", "--from-vault"], { encoding: "utf8", env: { ...process.env, KAIZEN_SOURCE: path.join(tmp(), "nao-existe") } });
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
  fs.rmSync(path.join(v, ".claude", "modelos.json"));
  put(v, "scripts/handoff-extra.py");
  put(v, "scripts/limpa-cache.py");
  const { missing, unlisted } = plan(v);
  assert.deepStrictEqual(missing.sort(), [".claude/modelos.json", ".claude/skills/swot", "scripts/handoff.py"]);
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
  for (const d of ["bin", "adapters"]) fs.cpSync(path.join(root, d), path.join(pkg, d), { recursive: true, filter: semCache });
  fs.mkdirSync(path.join(pkg, "core")); // core/ vazio: o 1.º --from-vault só acrescenta
  const kz = path.join(pkg, "bin", "kaizen.js");
  const v = fakeVault();
  const env = { ...process.env, KAIZEN_SOURCE: v };
  assert.strictEqual(spawnSync("node", [kz, "sync", "--from-vault"], { encoding: "utf8", env }).status, 0);
  const ok = spawnSync("node", [kz, "sync", "--from-vault", "--check"], { encoding: "utf8", env });
  assert.strictEqual(ok.status, 0, ok.stdout + ok.stderr);
  put(v, ".claude/skills/michi/SKILL.md", "alterado");
  const f = path.join(pkg, "core", "skills", "michi", "SKILL.md");
  const before = fs.readFileSync(f, "utf8");
  const stale = spawnSync("node", [kz, "sync", "--from-vault", "--check"], { encoding: "utf8", env });
  assert.strictEqual(stale.status, 1);
  assert.match(stale.stdout, /skills\/michi\/SKILL\.md/);
  assert.strictEqual(fs.readFileSync(f, "utf8"), before);
});

test("sync --check falha com ficheiro órfão em core/ que o vault já não gera, sem lhe tocar", () => {
  const pkg = tmp();
  const root = path.join(__dirname, "..");
  for (const d of ["bin", "adapters"]) fs.cpSync(path.join(root, d), path.join(pkg, d), { recursive: true, filter: semCache });
  fs.mkdirSync(path.join(pkg, "core")); // core/ vazio: o 1.º --from-vault só acrescenta
  const kz = path.join(pkg, "bin", "kaizen.js");
  const v = fakeVault();
  const env = { ...process.env, KAIZEN_SOURCE: v };
  assert.strictEqual(spawnSync("node", [kz, "sync", "--from-vault"], { encoding: "utf8", env }).status, 0);
  put(pkg, "core/commands/one-shot.md", "órfão");
  const r = spawnSync("node", [kz, "sync", "--from-vault", "--check"], { encoding: "utf8", env });
  assert.strictEqual(r.status, 1);
  assert.match(r.stdout, /desatualizado: core\/commands\/one-shot\.md/);
  assert.ok(fs.existsSync(path.join(pkg, "core", "commands", "one-shot.md")));
});

test("owns() reconhece caminhos do vault que entram no sync", () => {
  const { owns } = require("../bin/sync.js");
  assert.ok(owns(".claude/skills/michi/SKILL.md"));
  assert.ok(owns("scripts/sp-move.py"));
  assert.ok(owns(".claude/commands/sp.md"));
  assert.ok(!owns("scripts/outro-guard.py"));
  assert.ok(!owns("knowledge/projects/p/sp/TODO/x.md"));
});

test("sync --check imprime a fonte e sai 1 com ficheiros rastreados de core/ que o vault não tem (o sync não os apaga)", () => {
  const pkg = tmp();
  const root = path.join(__dirname, "..");
  for (const d of ["bin", "adapters"]) fs.cpSync(path.join(root, d), path.join(pkg, d), { recursive: true, filter: semCache });
  fs.mkdirSync(path.join(pkg, "core")); // core/ vazio: o 1.º --from-vault só acrescenta
  const kz = path.join(pkg, "bin", "kaizen.js");
  const git = (...a) => spawnSync("git", ["-c", "user.name=t", "-c", "user.email=t@t", ...a], { cwd: pkg, encoding: "utf8" });
  git("init", "-q");
  put(pkg, "core/scripts/rastreado.py", "x");
  git("add", "core");
  git("commit", "-q", "-m", "base");
  const v = fakeVault();
  const env = { ...process.env, KAIZEN_SOURCE: v };
  const r = spawnSync("node", [kz, "sync", "--from-vault", "--check"], { encoding: "utf8", env });
  assert.strictEqual(r.status, 1, r.stdout + r.stderr);
  assert.ok(r.stdout.includes(`fonte ${v}`), r.stdout);
  assert.match(r.stdout, /removeria rastreado: core\/scripts\/rastreado\.py/);
  assert.ok(fs.existsSync(path.join(pkg, "core", "scripts", "rastreado.py")));
});

test("owns(rel) é verdadeiro exatamente para as origens que plan() devolve", () => {
  const { owns } = require("../bin/sync.js");
  const v = fakeVault();
  put(v, "scripts/test_sp_fila_tema.py");
  put(v, "scripts/test_michi_nucleo.py"); // SKIP
  put(v, "scripts/ficheiro-solto.py"); // fora das regras
  const { parts } = plan(v);
  const origins = parts.map((p) => p[0]).filter((o) => o.startsWith("scripts/") && o.endsWith(".py"));
  for (const o of origins) assert.ok(owns(o), `owns devia aceitar ${o}`);
  const all = fs.readdirSync(path.join(v, "scripts")).map((n) => `scripts/${n}`);
  for (const o of all.filter((x) => !origins.includes(x))) assert.ok(!owns(o), `owns devia recusar ${o}`);
  assert.ok(!owns("scripts/test_michi_nucleo.py"));
  assert.ok(!owns("scripts/ficheiro-solto.py"));
});

// pacote isolado: os testes escrevem em core/ e correm em paralelo
function pkgCopy() {
  const pkg = tmp();
  const root = path.join(__dirname, "..");
  for (const d of ["bin", "adapters"]) fs.cpSync(path.join(root, d), path.join(pkg, d), { recursive: true, filter: semCache });
  fs.mkdirSync(path.join(pkg, "core")); // core/ vazio: o 1.º --from-vault só acrescenta
  return { pkg, kz: path.join(pkg, "bin", "kaizen.js") };
}

const PERSONAL = "ODIN guarda knowledge/projects/odin/x; o AC (Ana Costa) aprova.\n";
const CONFIG = { userName: "AC", userFullName: "Ana Costa", agentName: "ODIN", agentSlug: "odin" };

function personalVault() {
  const v = fakeVault();
  put(v, ".claude/skills/michi/SKILL.md", PERSONAL);
  put(v, ".claude/commands/sp.md", `# sp by Ana Costa\n${PERSONAL}`);
  put(v, "scripts/sp-move.py", `# ${PERSONAL}`);
  put(v, "kaizen.config.json", JSON.stringify(CONFIG));
  return v;
}

test("ida e volta: --from-vault e depois --to-vault repõe as peças byte a byte", () => {
  const { kz } = pkgCopy();
  const v = personalVault();
  const from = spawnSync("node", [kz, "sync", "--from-vault"], { encoding: "utf8", env: { ...process.env, KAIZEN_SOURCE: v } });
  assert.strictEqual(from.status, 0, from.stdout + from.stderr);
  const v2 = tmp();
  put(v2, "kaizen.config.json", JSON.stringify(CONFIG));
  const to = spawnSync("node", [kz, "sync", "--to-vault"], { encoding: "utf8", env: { ...process.env, KAIZEN_SOURCE: v2 } });
  assert.strictEqual(to.status, 0, to.stdout + to.stderr);
  for (const [origin] of plan(v).parts) {
    const a = path.join(v, origin);
    for (const rel of fs.statSync(a).isDirectory() ? require("../bin/sync.js").files(a).map((f) => `${origin}/${f}`) : [origin]) {
      assert.strictEqual(fs.readFileSync(path.join(v2, rel), "utf8"), fs.readFileSync(path.join(v, rel), "utf8"), rel);
    }
  }
});

test("slug dentro de outra palavra fica intacto no --from-vault; ocorrências isoladas continuam a virar marcador", () => {
  const { kz, pkg } = pkgCopy();
  const v = personalVault();
  put(v, ".claude/skills/michi/SKILL.md", `${PERSONAL}coding e kaizenodin ODIN odin\n`);
  const from = spawnSync("node", [kz, "sync", "--from-vault"], { encoding: "utf8", env: { ...process.env, KAIZEN_SOURCE: v } });
  assert.strictEqual(from.status, 0, from.stdout + from.stderr);
  const core = fs.readFileSync(path.join(pkg, "core", "skills/michi/SKILL.md"), "utf8");
  assert.match(core, /coding/);
  assert.doesNotMatch(core, /c\{\{agentSlug\}\}g|ckaizeng/);
  assert.match(core, /knowledge\/projects\/\{\{agentSlug\}\}\/x/);
});

for (const [nome, rel] of [["kaizen.config.json", "kaizen.config.json"], [".kaizen-sync.json", ".kaizen-sync.json"]]) {
  test(`${nome} com JSON inválido: --to-vault sai com rc≠0, o caminho no stderr e sem stack`, () => {
    const { kzr, v } = synced();
    put(v, rel, "{ não é json");
    const r = kzr("--to-vault");
    assert.notStrictEqual(r.status, 0);
    assert.ok(r.stderr.includes(path.join(v, rel)), r.stderr);
    assert.doesNotMatch(r.stderr, /    at /);
  });
}

function synced() {
  const { kz } = pkgCopy();
  const v = personalVault();
  assert.strictEqual(spawnSync("node", [kz, "sync", "--from-vault"], { encoding: "utf8", env: { ...process.env, KAIZEN_SOURCE: v } }).status, 0);
  const env = { ...process.env, KAIZEN_SOURCE: v };
  const kzr = (...a) => spawnSync("node", [kz, "sync", ...a], { encoding: "utf8", env });
  return { v, kzr };
}

test("--to-vault --check: 0 com o vault igual, 1 com a lista quando difere; não escreve", () => {
  const { v, kzr } = synced();
  const ok = kzr("--to-vault", "--check");
  assert.strictEqual(ok.status, 0, ok.stdout + ok.stderr);
  put(v, ".claude/skills/michi/SKILL.md", "outra coisa");
  const bad = kzr("--to-vault", "--check");
  assert.strictEqual(bad.status, 1);
  assert.match(bad.stdout, /difere: \.claude\/skills\/michi\/SKILL\.md/);
  assert.strictEqual(fs.readFileSync(path.join(v, ".claude/skills/michi/SKILL.md"), "utf8"), "outra coisa");
});

test("--to-vault recusa peça editada no vault desde o último sync e --force sobrescreve", () => {
  const { v, kzr } = synced();
  assert.strictEqual(kzr("--to-vault").status, 0);
  assert.ok(fs.existsSync(path.join(v, ".kaizen-sync.json")));
  put(v, "scripts/sp-move.py", "# edição local\n");
  const r = kzr("--to-vault");
  assert.notStrictEqual(r.status, 0);
  assert.match(r.stderr, /editado no vault: scripts\/sp-move\.py/);
  assert.strictEqual(fs.readFileSync(path.join(v, "scripts/sp-move.py"), "utf8"), "# edição local\n");
  assert.strictEqual(kzr("--to-vault", "--force").status, 0);
  assert.strictEqual(fs.readFileSync(path.join(v, "scripts/sp-move.py"), "utf8"), `# ${PERSONAL}`);
});

test("sem manifesto, peça do vault diferente do core conta como edição local", () => {
  const { v, kzr } = synced();
  put(v, ".claude/commands/sp.md", "mexido");
  const r = kzr("--to-vault");
  assert.notStrictEqual(r.status, 0);
  assert.match(r.stderr, /editado no vault: \.claude\/commands\/sp\.md/);
});

// órfã: peça registada no manifesto que o core/ já não gera, com o ficheiro ainda no vault
function withOrphan(content = "velho\n", recorded = content) {
  const ctx = synced();
  assert.strictEqual(ctx.kzr("--to-vault").status, 0);
  const rel = "scripts/sp-velho.py";
  put(ctx.v, rel, content);
  const mf = path.join(ctx.v, ".kaizen-sync.json");
  const m = JSON.parse(fs.readFileSync(mf, "utf8"));
  m[rel] = require("../bin/sync.js").sha(Buffer.from(recorded));
  fs.writeFileSync(mf, JSON.stringify(m, null, 2) + "\n");
  const manifest = () => JSON.parse(fs.readFileSync(mf, "utf8"));
  return { ...ctx, rel, f: path.join(ctx.v, rel), manifest };
}

test("--to-vault --check lista a órfã como remover:, conta-a e sai 1 sem apagar", () => {
  const { kzr, f, rel, manifest } = withOrphan();
  const r = kzr("--to-vault", "--check");
  assert.strictEqual(r.status, 1, r.stdout + r.stderr);
  assert.ok(r.stdout.includes(`remover: ${rel}`), r.stdout);
  assert.match(r.stdout, /1 remoç/);
  assert.ok(fs.existsSync(f));
  assert.ok(manifest()[rel]);
});

test("--to-vault apaga a órfã não editada e tira-a do manifesto", () => {
  const { kzr, f, rel, manifest } = withOrphan();
  const r = kzr("--to-vault");
  assert.strictEqual(r.status, 0, r.stdout + r.stderr);
  assert.ok(!fs.existsSync(f));
  assert.ok(!(rel in manifest()));
  assert.match(r.stdout, /1 removid/);
});

test("--to-vault recusa órfã editada no vault sem apagar nem escrever; --force apaga", () => {
  const { v, kzr, f, rel, manifest } = withOrphan("# editado\n", "velho\n");
  put(v, ".claude/skills/michi/SKILL.md", "outra coisa");
  const before = fs.readFileSync(path.join(v, ".kaizen-sync.json"), "utf8");
  const r = kzr("--to-vault");
  assert.notStrictEqual(r.status, 0);
  assert.ok(r.stderr.includes(`editado no vault: ${rel}`), r.stderr);
  assert.ok(fs.existsSync(f));
  assert.strictEqual(fs.readFileSync(path.join(v, ".claude/skills/michi/SKILL.md"), "utf8"), "outra coisa");
  assert.strictEqual(fs.readFileSync(path.join(v, ".kaizen-sync.json"), "utf8"), before);
  assert.strictEqual(kzr("--to-vault", "--force").status, 0);
  assert.ok(!fs.existsSync(f));
  assert.ok(!(rel in manifest()));
});

test("entrada do manifesto sem ficheiro no vault sai do manifesto sem erro nem remoção", () => {
  const { kzr, f, rel, manifest } = withOrphan();
  fs.rmSync(f);
  const c = kzr("--to-vault", "--check");
  assert.strictEqual(c.status, 0, c.stdout + c.stderr);
  assert.doesNotMatch(c.stdout, /remover:/);
  const r = kzr("--to-vault");
  assert.strictEqual(r.status, 0, r.stdout + r.stderr);
  assert.ok(!(rel in manifest()));
  assert.match(r.stdout, /0 removid/);
});

test("manifesto com caminho para fora do vault não apaga nada fora dele", () => {
  const { v, kzr } = synced();
  assert.strictEqual(kzr("--to-vault").status, 0);
  const outside = path.join(path.dirname(v), `fora-${path.basename(v)}.txt`);
  fs.writeFileSync(outside, "fora\n");
  const mf = path.join(v, ".kaizen-sync.json");
  const m = JSON.parse(fs.readFileSync(mf, "utf8"));
  const sha = require("../bin/sync.js").sha;
  m[`../${path.basename(outside)}`] = sha(Buffer.from("fora\n"));
  m[outside] = sha(Buffer.from("fora\n"));
  fs.writeFileSync(mf, JSON.stringify(m, null, 2) + "\n");
  const r = kzr("--to-vault");
  assert.strictEqual(r.status, 0, r.stdout + r.stderr);
  assert.ok(fs.existsSync(outside));
  assert.match(r.stderr, /inválid/);
  fs.rmSync(outside);
});

test("sync sem sentido falha e pede --to-vault ou --from-vault", () => {
  const { kzr } = synced();
  const r = kzr();
  assert.notStrictEqual(r.status, 0);
  assert.match(r.stderr, /--to-vault.*--from-vault/);
});

test("core/ guarda marcadores e loadCore renderiza-os (defeitos neutros sem config)", () => {
  const { loadCore } = require("../bin/core.js");
  const c = tmp();
  put(c, "skills/a/SKILL.md", "{{agentName}} e {{userName}} em {{agentSlug}}/");
  put(c, "x.bin", "{{userName}}");
  const neutral = Object.fromEntries(loadCore(c).map((f) => [f.rel, f.data.toString()]));
  assert.strictEqual(neutral["skills/a/SKILL.md"], "the agent e user em kaizen/");
  assert.strictEqual(neutral["x.bin"], "{{userName}}");
  const own = loadCore(c, { agentName: "ODIN", userName: "AC", agentSlug: "odin" });
  assert.strictEqual(own.find((f) => f.rel === "skills/a/SKILL.md").data.toString(), "ODIN e AC em odin/");
});

test("pasta listada em dirs é copiada pelo plan e reconhecida por owns", () => {
  const { owns } = require("../bin/sync.js");
  const v = fakeVault();
  const d = MANIFEST.dirs[0];
  assert.ok(plan(v).parts.some((p) => p[1] === d));
  assert.ok(owns(`${d}/x.txt`));
  assert.ok(!owns("scripts/outra-pasta/x.txt"));
});

// --- incidente 2026-11-26: --from-vault apagava peças de core/ que o vault não tem e trocava marcadores por «BMS»
function pkgComCore() {
  const { pkg, kz } = pkgCopy();
  fs.cpSync(path.join(__dirname, "..", "core"), path.join(pkg, "core"), { recursive: true, filter: semCache });
  return { pkg, kz };
}
const fromVault = (kz, v, ...a) => spawnSync("node", [kz, "sync", "--from-vault", ...a], { encoding: "utf8", env: { ...process.env, KAIZEN_SOURCE: v } });

test("--from-vault nunca apaga peças de core/ que o vault não tem", () => {
  const { pkg, kz } = pkgComCore();
  put(pkg, "core/skills/so-no-core/SKILL.md", "só em core");
  put(pkg, "core/scripts/test_so_no_core.py", "x");
  const r = fromVault(kz, personalVault());
  assert.strictEqual(r.status, 0, r.stdout + r.stderr);
  assert.ok(fs.existsSync(path.join(pkg, "core/skills/so-no-core/SKILL.md")));
  assert.ok(fs.existsSync(path.join(pkg, "core/scripts/test_so_no_core.py")));
  assert.match(r.stdout, /mantido: \d+ ficheiros/);
});

test("--from-vault repõe marcadores e não deixa dados pessoais em core/", () => {
  const { pkg, kz } = pkgComCore();
  const v = personalVault();
  put(v, ".claude/commands/sp.md", `# sp\n${PERSONAL}`);
  const r = fromVault(kz, v);
  assert.strictEqual(r.status, 0, r.stdout + r.stderr);
  const c = fs.readFileSync(path.join(pkg, "core/commands/sp.md"), "utf8");
  assert.match(c, /\{\{userName\}\}/);
  assert.doesNotMatch(c, /Ana Costa|\bAC\b|ODIN/);
});

test("--from-vault: peça nova só entra com --only; --dry-run não escreve e lista remoções evitadas", () => {
  const { pkg, kz } = pkgComCore();
  const v = personalVault();
  put(v, "scripts/sp-novo.py", "# novo\n");
  const f = path.join(pkg, "core/scripts/sp-novo.py");
  const sem = fromVault(kz, v);
  assert.strictEqual(sem.status, 0, sem.stdout + sem.stderr);
  assert.ok(!fs.existsSync(f));
  assert.match(sem.stdout, /ignorado \(novo; use --only scripts\/sp-novo\.py\)/);
  const dry = fromVault(kz, v, "--dry-run", "--only", "scripts/sp-novo.py");
  assert.strictEqual(dry.status, 0, dry.stdout + dry.stderr);
  assert.match(dry.stdout, /mudaria: core\/scripts\/sp-novo\.py \(novo\)/);
  assert.match(dry.stdout, /removeria \(evitado\)/);
  assert.ok(!fs.existsSync(f));
  assert.strictEqual(fromVault(kz, v, "--only", "core/scripts/sp-novo.py").status, 0);
  assert.strictEqual(fs.readFileSync(f, "utf8"), "# novo\n");
});

test("--from-vault --only limita a atualização às peças indicadas", () => {
  const { pkg, kz } = pkgComCore();
  const v = personalVault();
  put(v, ".claude/skills/michi/SKILL.md", "michi novo\n");
  put(v, ".claude/skills/dr/SKILL.md", "dr novo\n");
  assert.strictEqual(fromVault(kz, v, "--only", "skills/michi").status, 0);
  assert.strictEqual(fs.readFileSync(path.join(pkg, "core/skills/michi/SKILL.md"), "utf8"), "michi novo\n");
  assert.notStrictEqual(fs.readFileSync(path.join(pkg, "core/skills/dr/SKILL.md"), "utf8"), "dr novo\n");
});

test("--from-vault recusa árvore suja e checkout principal; --dry-run passa", () => {
  const { pkg, kz } = pkgComCore();
  const g = (...a) => spawnSync("git", a, { cwd: pkg, encoding: "utf8" });
  g("init", "-q"); g("add", "-A");
  g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base");
  const v = personalVault();
  const main = fromVault(kz, v);
  assert.notStrictEqual(main.status, 0);
  assert.match(main.stderr, /worktree/);
  g("worktree", "add", "-q", "-b", "wt", path.join(pkg, "..", path.basename(pkg) + "-wt"));
  const wt = path.join(pkg, "..", path.basename(pkg) + "-wt");
  put(wt, "core/skills/dr/SKILL.md", "sujo");
  const wkz = path.join(wt, "bin", "kaizen.js");
  const sujo = fromVault(wkz, v);
  assert.notStrictEqual(sujo.status, 0);
  assert.match(sujo.stderr, /por commitar/);
  assert.strictEqual(fromVault(wkz, v, "--dry-run").status, 0);
});
