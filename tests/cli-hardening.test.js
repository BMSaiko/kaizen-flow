"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const { BIN, kaizen } = require("./helpers/sandbox");
const run = (...a) => kaizen(a);
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), "kaizen-hard-"));

test("harness inválido ou em falta aborta sem escrever", () => {
  const d = tmp();
  for (const args of [["init", d, "--harness", "foo"], ["init", d, "--harness"]]) {
    const r = run(...args);
    assert.strictEqual(r.status, 1, args.join(" "));
    assert.match(r.stderr, /--harness/);
  }
  assert.deepStrictEqual(fs.readdirSync(d), []);
});

test("settings.json inválido aborta antes de escrever e não é alterado", () => {
  const d = tmp();
  fs.mkdirSync(path.join(d, ".claude"));
  const bad = path.join(d, ".claude", "settings.json");
  fs.writeFileSync(bad, "{ not json");
  const r = run("init", d, "--harness", "claude");
  assert.notStrictEqual(r.status, 0);
  assert.strictEqual(fs.readFileSync(bad, "utf8"), "{ not json");
  assert.ok(!fs.existsSync(path.join(d, ".claude", "skills")));
});

test("init num caminho que é um ficheiro falha com rc≠0", () => {
  const d = tmp();
  const f = path.join(d, "file.txt");
  fs.writeFileSync(f, "x");
  assert.notStrictEqual(run("init", f, "--harness", "codex").status, 0);
  assert.strictEqual(fs.readFileSync(f, "utf8"), "x");
});

test("doctor falha numa instalação em falta e --fix repõe sem sobrescrever", () => {
  const d = tmp();
  assert.notStrictEqual(run("doctor", d, "--harness", "codex").status, 0);
  assert.strictEqual(run("doctor", d, "--harness", "codex", "--fix").status, 0);
  const agents = path.join(d, "AGENTS.md");
  fs.appendFileSync(agents, "\nminha nota\n");
  const before = fs.readFileSync(agents, "utf8");
  assert.strictEqual(run("doctor", d, "--harness", "codex", "--fix").status, 0);
  assert.strictEqual(fs.readFileSync(agents, "utf8"), before);
});

// --- formato único de erro (EC-NNN) e kaizen preflight (preflight-erros-ux) ---
const { formatar } = require("../bin/commands/erros.js");
const EC4 = /^EC-\d{3} O quê: .+\n  Porquê: .+\n  Estado guardado: .+\n  Próximo: .+$/m;

test("formatar dá 4 partes numa linha cada e recusa EC inválido ou parte vazia", () => {
  const t = formatar("EC-016", "limite\nde uso", "quota", "checkpoint intacto", "kaizen resume x");
  assert.match(t, EC4);
  assert.strictEqual(t.split("\n").length, 4);
  assert.ok(t.includes("limite de uso"));
  assert.throws(() => formatar("EC-1", "a", "b", "c", "d"));
  assert.throws(() => formatar("EC-010", "a", " ", "c", "d"));
});

test("doctor numa pasta que não existe sai rc 1 no formato EC-067", () => {
  const r = run("doctor", path.join(tmp(), "nao-existe"));
  assert.strictEqual(r.status, 1);
  assert.match(r.stderr, EC4);
  assert.match(r.stderr, /^EC-067 O quê: .*não é um diretório/m);
});

test("doctor com peças em falta lista-as numa mensagem EC-068 e propõe --fix", () => {
  const d = tmp();
  const r = run("doctor", d, "--harness", "codex");
  assert.notStrictEqual(r.status, 0);
  assert.match(r.stderr, /^EC-068 O quê: faltam \d+ peça\(s\) do kaizen: /m);
  assert.match(r.stderr, /Próximo: `kaizen doctor .* --fix`/);
});

const PREFLIGHT = path.join(__dirname, "..", "core", "scripts", "sp-preflight.py");
const semPreflight = !fs.existsSync(PREFLIGHT) && "core/scripts/sp-preflight.py chega com o kaizen sync";

test("preflight fora de git sai rc 2 no formato EC", { skip: semPreflight }, () => {
  const r = run("preflight", "--repo", tmp());
  assert.strictEqual(r.status, 2);
  assert.match(r.stderr.replace(/\r\n/g, "\n"), EC4);  // Windows escreve \r\n
});

test("preflight propaga rc 1 e lista cada problema com EC sem alterar nada", { skip: semPreflight }, () => {
  const d = tmp();
  const g = (...a) => spawnSync("git", ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main", "-C", d, ...a], { encoding: "utf8" });
  g("init", "-q");
  fs.writeFileSync(path.join(d, "a.txt"), "a");
  g("add", "a.txt");
  g("commit", "-q", "-m", "base");
  g("checkout", "-q", "-b", "outro");
  fs.writeFileSync(path.join(d, "sujo.txt"), "x");
  const r = run("preflight", "--repo", d);
  assert.strictEqual(r.status, 1);
  assert.match(r.stdout, /^EC-031 O quê: /m);
  assert.match(r.stdout, /^EC-060 O quê: .*sujo\.txt/m);
  assert.ok(fs.existsSync(path.join(d, "sujo.txt")));
  assert.strictEqual(g("rev-parse", "--abbrev-ref", "HEAD").stdout.trim(), "outro");
});

test("quality --lista mostra as etapas e rc 1 com base inválida em etapa de diff", () => {
  const l = run("quality", "--lista");
  assert.strictEqual(l.status, 0);
  assert.match(l.stdout, /^lint\r?\nratchet\r?\nstrict\r?\n/);
  const r = run("quality", "--so", "protegidos", "--base", "nao-existe");
  assert.strictEqual(r.status, 1);
});
