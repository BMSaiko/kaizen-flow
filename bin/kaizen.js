#!/usr/bin/env node
"use strict";
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const PKG = path.resolve(__dirname, "..");
const CORE_DIR = path.join(PKG, "core");
const { loadCore } = require("./core.js");
const { MARKER } = require("../adapters/util.js");
const { detectMode } = require("./mode.js");
const ADAPTERS = { claude: require("../adapters/claude"), codex: require("../adapters/codex"), "agents-md": require("../adapters/agents-md") };
const VAULT = process.env.KAIZEN_SOURCE || path.join(require("os").homedir(), "Documents", "Second-Brain");

// origem (no vault) -> destino (no repo alvo)
const PARTS = [
  [".claude/skills/michi", ".claude/skills/michi"],
  [".claude/skills/super-prompt", ".claude/skills/super-prompt"],
  [".claude/skills/one-shot", ".claude/skills/one-shot"],
  [".claude/commands/sp.md", ".claude/commands/sp.md"],
  [".claude/commands/sp-list.md", ".claude/commands/sp-list.md"],
  [".claude/commands/sp-handoff.md", ".claude/commands/sp-handoff.md"],
  [".claude/commands/one-shot.md", ".claude/commands/one-shot.md"],
  ["scripts/sp-list.py", "scripts/sp-list.py"],
  ["scripts/sp-move.py", "scripts/sp-move.py"],
  ["scripts/sp-new.py", "scripts/sp-new.py"],
  ["scripts/sp-validate.py", "scripts/sp-validate.py"],
  ["scripts/sp-validate-hook.py", "scripts/sp-validate-hook.py"],
  ["scripts/sp-handoff.py", "scripts/sp-handoff.py"],
  ["scripts/context-guard.py", "scripts/context-guard.py"],
  ["scripts/skill-cut.py", "scripts/skill-cut.py"],
  [".claude/skills/grill-me", ".claude/skills/grill-me"],
  [".claude/skills/dr", ".claude/skills/dr"],
  [".claude/skills/dp", ".claude/skills/dp"],
  [".claude/skills/da", ".claude/skills/da"],
  [".claude/skills/brainstorm", ".claude/skills/brainstorm"],
  [".claude/skills/swot", ".claude/skills/swot"],
  ["scripts/doc-list.py", "scripts/doc-list.py"],
  ["scripts/doc-move.py", "scripts/doc-move.py"],
  ["scripts/sp-organize.py", "scripts/sp-organize.py"],
  ["scripts/kaizen_config.py", "scripts/kaizen_config.py"],
  ["scripts/test_kaizen_config.py", "scripts/test_kaizen_config.py"],
  ["scripts/test_sp_list.py", "scripts/test_sp_list.py"],
  ["scripts/test_sp_move.py", "scripts/test_sp_move.py"],
  ["scripts/test_sp_new.py", "scripts/test_sp_new.py"],
  ["scripts/test_sp_validate.py", "scripts/test_sp_validate.py"],
  ["scripts/test_sp_handoff.py", "scripts/test_sp_handoff.py"],
  ["scripts/test_sp_organize.py", "scripts/test_sp_organize.py"],
  ["scripts/test_michi_tree_close.py", "scripts/test_michi_tree_close.py"],
];

// cpSync recursivo escreve em caminhos com mojibake quando o destino tem Unicode (Node 22, Windows)
function copy(src, dst) {
  if (fs.statSync(src).isDirectory()) {
    fs.mkdirSync(dst, { recursive: true });
    for (const name of fs.readdirSync(src)) if (name !== "__pycache__" && name !== ".pytest_cache" && !name.endsWith(".pyc")) copy(path.join(src, name), path.join(dst, name));
  } else {
    fs.mkdirSync(path.dirname(dst), { recursive: true });
    fs.copyFileSync(src, dst);
  }
}

const coreRel = (to) => to.replace(/^\.claude\//, "");

// o vault é pessoal: tudo o que o identifica sai ao copiar para core/
const SANITIZE = [
  [/[A-Za-z]:[\\/]+Users[\\/]+bruno/gi, "~"],
  [/ by Bruno Silva/g, ""],
  [/Bruno Silva/g, "the user"],
  [/\bBMS\b/g, "user"],
  [/\bHEIMDALL\b/g, "the agent"],
  [/heimdall/gi, "kaizen"],
];
const TEXT_EXT = /\.(md|py|json|txt|js|toml)$/i;
const sanitize = (t) => SANITIZE.reduce((acc, [re, to]) => acc.replace(re, to), t);

function sanitizeTree(p) {
  if (fs.statSync(p).isDirectory()) return fs.readdirSync(p).forEach((n) => sanitizeTree(path.join(p, n)));
  if (TEXT_EXT.test(p)) fs.writeFileSync(p, sanitize(fs.readFileSync(p, "utf8")));
}

function sync() {
  fs.rmSync(CORE_DIR, { recursive: true, force: true });
  for (const [from, to] of PARTS) copy(path.join(VAULT, from), path.join(CORE_DIR, coreRel(to)));
  sanitizeTree(CORE_DIR);
  console.log(`sync: ${PARTS.length} peças de ${VAULT}`);
}

// escreve ficheiros sem sobrescrever; devolve quantos criou
function writeFiles(dest, files) {
  let n = 0;
  for (const f of files) {
    const out = path.join(dest, f.path);
    if (fs.existsSync(out)) { console.log(`existe, mantido: ${f.path}`); continue; }
    fs.mkdirSync(path.dirname(out), { recursive: true });
    fs.writeFileSync(out, f.data);
    n++;
  }
  return n;
}

function appendAgents(dest, block) {
  const out = path.join(dest, "AGENTS.md");
  const cur = fs.existsSync(out) ? fs.readFileSync(out, "utf8") : "";
  if (cur.includes(MARKER)) return;
  fs.writeFileSync(out, cur ? cur.replace(/\s*$/, "\n\n") + block : block);
}

// lê settings.json sem nunca o estragar: JSON inválido ou forma inesperada aborta antes de escrever fosse o que fosse
function readSettings(dest) {
  const settings = path.join(dest, ".claude", "settings.json");
  if (!fs.existsSync(settings)) return { settings, cfg: {} };
  let cfg;
  try { cfg = JSON.parse(fs.readFileSync(settings, "utf8").replace(/^﻿/, "")); } catch (e) { throw new Error(`${settings} não é JSON válido (${e.message}); corrija-o e repita`); }
  if (!cfg || typeof cfg !== "object" || Array.isArray(cfg)) throw new Error(`${settings} deve ser um objeto JSON`);
  if (cfg.hooks !== undefined && (!cfg.hooks || typeof cfg.hooks !== "object" || Array.isArray(cfg.hooks))) throw new Error(`${settings}: "hooks" deve ser um objeto`);
  return { settings, cfg };
}

function mergeHooks(dest, hooks) {
  const { settings, cfg } = readSettings(dest);
  cfg.hooks = cfg.hooks || {};
  for (const [ev, entries] of Object.entries(hooks)) {
    if (cfg.hooks[ev] !== undefined && !Array.isArray(cfg.hooks[ev])) throw new Error(`${settings}: hooks.${ev} deve ser uma lista`);
    cfg.hooks[ev] = cfg.hooks[ev] || [];
    const have = cfg.hooks[ev].flatMap((x) => (x.hooks || []).map((h) => h.command));
    for (const e of entries) if (!have.includes(e.hooks[0].command)) cfg.hooks[ev].push(e);
  }
  fs.mkdirSync(path.dirname(settings), { recursive: true });
  fs.writeFileSync(settings, JSON.stringify(cfg, null, 2) + "\n");
}

function init(target, harness = "claude") {
  const adapter = ADAPTERS[harness];
  if (!adapter) throw new Error(`harness desconhecido: ${harness} (claude|codex|agents-md)`);
  const dest = path.resolve(target || ".");
  if (fs.existsSync(dest) && !fs.statSync(dest).isDirectory()) throw new Error(`${dest} não é um diretório`);
  const out = adapter.render(loadCore());
  if (out.settings) readSettings(dest); // falha cedo, antes de escrever peças
  fs.mkdirSync(dest, { recursive: true });
  const n = writeFiles(dest, out.files);
  if (out.agents) appendAgents(dest, out.agents);
  if (out.settings) mergeHooks(dest, out.settings.hooks);
  const sp = path.join(dest, "knowledge", "projects", "kaizen");
  for (const d of ["sp", "dr", "dp"]) for (const s of ["TODO", "Doing", "Done"]) fs.mkdirSync(path.join(sp, "_default", d, s), { recursive: true });
  console.log(`init (${harness}): ${n} peças copiadas para ${dest}`);
  return n;
}

// "python" não existe em macOS/Linux modernos; procura um interpretador Python 3 real (o stub da Microsoft Store falha o --version)
let PYTHON;
function pythonCmd() {
  if (PYTHON !== undefined) return PYTHON;
  const cands = [process.env.KAIZEN_PYTHON, "python3", "python", "py"].filter(Boolean);
  PYTHON = cands.find((c) => {
    const r = spawnSync(c, ["--version"], { encoding: "utf8" });
    return r.status === 0 && /^Python 3\./.test(`${r.stdout}${r.stderr}`);
  }) || null;
  return PYTHON;
}

function py(args, cwd) {
  const cmd = pythonCmd();
  if (!cmd) { console.error("falta: Python 3 no PATH (ou KAIZEN_PYTHON)"); return 1; }
  const r = spawnSync(cmd, ["-I", "-B", ...args], { cwd, stdio: "inherit", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
  return r.status === null ? 1 : r.status;
}

function checkInstall(dir, harness) {
  const problems = [];
  const out = ADAPTERS[harness].render(loadCore());
  for (const f of out.files) if (!fs.existsSync(path.join(dir, f.path))) problems.push(`falta: ${f.path}`);
  if (out.agents) {
    const a = path.join(dir, "AGENTS.md");
    if (!fs.existsSync(a) || !fs.readFileSync(a, "utf8").includes(MARKER)) problems.push("falta: bloco kaizen em AGENTS.md");
  }
  if (out.settings) {
    let cfg = {};
    try { cfg = readSettings(dir).cfg; } catch (e) { problems.push(`settings: ${e.message}`); }
    for (const [ev, entries] of Object.entries(out.settings.hooks)) {
      const have = ((cfg.hooks || {})[ev] || []).flatMap((x) => (x.hooks || []).map((h) => h.command));
      for (const e of entries) if (!have.includes(e.hooks[0].command)) problems.push(`falta hook ${ev}: ${e.hooks[0].command}`);
    }
  }
  return problems;
}

function doctor(target, harness = "claude", fix = false) {
  const dir = path.resolve(target || ".");
  if (!fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) { console.error(`erro: ${dir} não é um diretório`); return 1; }
  let problems = checkInstall(dir, harness);
  if (problems.length && fix) {
    console.log(`doctor --fix: a repor ${problems.length} problema(s) (nada existente é sobrescrito)`);
    init(dir, harness);
    problems = checkInstall(dir, harness);
  }
  for (const p of problems) console.error(p);
  let rc = problems.length ? 1 : 0;
  if (!pythonCmd()) { console.error("falta: Python 3 no PATH (ou KAIZEN_PYTHON)"); rc = 1; }
  else if (!problems.some((p) => p.includes("scripts/"))) rc = py(["scripts/sp-list.py", "--all"], dir) || rc; // os scripts arrancam
  const root = path.join(dir, "knowledge", "projects", "kaizen");
  const sps = [];
  (function walk(d) {
    if (!fs.existsSync(d)) return;
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.name.endsWith(".md") && /\/sp\/(TODO|Doing|Done)\//.test(p.replace(/\\/g, "/")) && !e.name.startsWith("_")) sps.push(p);
    }
  })(root);
  if (sps.length && pythonCmd()) rc = py(["scripts/sp-validate.py", ...sps], dir) || rc;
  const m = detectMode();
  console.log(`handoff: ${m.mode} (${m.backend})`);
  console.log(rc === 0 ? `doctor: ok (${sps.length} SPs)` : "doctor: problemas");
  return rc;
}

// `kaizen usage|report [flags]` -> usage/kaizen_usage.py (a raiz do repo é o diretório atual)
function usage(sub, rest) {
  const cmd = pythonCmd();
  if (!cmd) { console.error("falta: Python 3 no PATH (ou KAIZEN_PYTHON)"); return 1; }
  const r = spawnSync(cmd, ["-I", "-B", path.join(PKG, "usage", "kaizen_usage.py"), sub, ...rest], { stdio: "inherit", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
  return r.status === null ? 1 : r.status;
}

const argv = process.argv.slice(2);
const hi = argv.indexOf("--harness");
let harness = "claude";
if (hi >= 0) {
  harness = argv.splice(hi, 2)[1];
  if (!ADAPTERS[harness]) { console.error(`erro: --harness requer um de claude|codex|agents-md (recebido: ${harness === undefined ? "nada" : harness})`); process.exit(1); }
}
const fi = argv.indexOf("--fix");
const fix = fi >= 0 && !!argv.splice(fi, 1);
const [cmd, arg] = argv;
const cmds = {
  init: () => init(arg, harness),
  sync,
  usage: () => process.exit(usage("usage", argv.slice(1))),
  report: () => process.exit(usage("report", argv.slice(1))),
  doctor: () => process.exit(doctor(arg, harness, fix)),
  status: () => process.exit(py(["scripts/sp-list.py", "--all"], path.resolve(arg || "."))),
  audit: () => {
    const hits = require("./audit.js").audit(path.resolve(arg || "."));
    for (const h of hits) console.log(`${h.file}:${h.line} [${h.pattern}]`);
    console.log(`audit: ${hits.length} hits`);
    process.exit(hits.length ? 1 : 0);
  },
};
if (!cmds[cmd]) {
  console.log("kaizen <init [repo] [--harness claude|codex|agents-md] | doctor [repo] [--harness h] [--fix] | status [repo] | usage [flags] | report [--week YYYY-WNN] [flags] | audit [dir] | sync>");
  process.exit(cmd ? 1 : 0);
}
try {
  cmds[cmd]();
} catch (e) {
  console.error(`erro: ${e.message}`);
  process.exit(1);
}
