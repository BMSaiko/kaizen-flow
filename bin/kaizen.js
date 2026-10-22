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
    for (const name of fs.readdirSync(src)) copy(path.join(src, name), path.join(dst, name));
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

function mergeHooks(dest, hooks) {
  const settings = path.join(dest, ".claude", "settings.json");
  const cfg = fs.existsSync(settings) ? JSON.parse(fs.readFileSync(settings, "utf8")) : {};
  cfg.hooks = cfg.hooks || {};
  for (const [ev, entries] of Object.entries(hooks)) {
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
  const out = adapter.render(loadCore());
  const n = writeFiles(dest, out.files);
  if (out.agents) appendAgents(dest, out.agents);
  if (out.settings) mergeHooks(dest, out.settings.hooks);
  const sp = path.join(dest, "knowledge", "projects", "kaizen");
  for (const d of ["sp", "dr", "dp"]) for (const s of ["TODO", "Doing", "Done"]) fs.mkdirSync(path.join(sp, "_default", d, s), { recursive: true });
  console.log(`init (${harness}): ${n} peças copiadas para ${dest}`);
}

function py(args, cwd) {
  const r = spawnSync("python", ["-I", ...args], { cwd, stdio: "inherit" });
  return r.status === null ? 1 : r.status;
}

function doctor(target, harness = "claude") {
  const dir = path.resolve(target || ".");
  let rc = 0;
  for (const f of ADAPTERS[harness].render(loadCore()).files) if (!fs.existsSync(path.join(dir, f.path))) { console.error(`falta: ${f.path}`); rc = 1; }
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
  if (sps.length) rc = py(["scripts/sp-validate.py", ...sps], dir) || rc;
  const m = detectMode();
  console.log(`handoff: ${m.mode} (${m.backend})`);
  console.log(rc === 0 ? `doctor: ok (${sps.length} SPs)` : "doctor: problemas");
  return rc;
}

// `kaizen usage|report [flags]` -> usage/kaizen_usage.py (a raiz do repo é o diretório atual)
function usage(sub, rest) {
  const r = spawnSync("python", ["-I", path.join(PKG, "usage", "kaizen_usage.py"), sub, ...rest], { stdio: "inherit" });
  return r.status === null ? 1 : r.status;
}

const argv = process.argv.slice(2);
const hi = argv.indexOf("--harness");
const harness = hi >= 0 ? argv.splice(hi, 2)[1] : "claude";
const [cmd, arg] = argv;
const cmds = {
  init: () => init(arg, harness),
  sync,
  usage: () => process.exit(usage("usage", argv.slice(1))),
  report: () => process.exit(usage("report", argv.slice(1))),
  doctor: () => process.exit(doctor(arg, harness)),
  status: () => process.exit(py(["scripts/sp-list.py", "--all"], path.resolve(arg || "."))),
  audit: () => {
    const hits = require("./audit.js").audit(path.resolve(arg || "."));
    for (const h of hits) console.log(`${h.file}:${h.line} [${h.pattern}]`);
    console.log(`audit: ${hits.length} hits`);
    process.exit(hits.length ? 1 : 0);
  },
};
if (!cmds[cmd]) {
  console.log("kaizen <init [repo] [--harness claude|codex|agents-md] | doctor [repo] [--harness h] | status [repo] | usage [flags] | report [--week YYYY-WNN] [flags] | audit [dir] | sync>");
  process.exit(cmd ? 1 : 0);
}
try {
  cmds[cmd]();
} catch (e) {
  console.error(`erro: ${e.message}`);
  process.exit(1);
}
