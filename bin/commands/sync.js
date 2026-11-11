"use strict";
const fs = require("fs");
const { spawnSync } = require("child_process");
const path = require("path");
const { plan, overlay, files, sha } = require("../sync.js");

const PKG = path.resolve(__dirname, "..", "..");
const CORE_DIR = path.join(PKG, "core");
const VAULT = process.env.KAIZEN_SOURCE || path.join(require("os").homedir(), "Documents", "Second-Brain");

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

// skills e commands vão para a raiz de core/; a config (.claude/modelos.json) mantém .claude/
const coreRel = (to) => to.replace(/^\.claude\/(skills|commands)\//, "$1/");

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

// gera core/ em dest a partir do vault; devolve o que o sync reporta
function build(dest, tdir, stamp) {
  if (!fs.existsSync(VAULT) || !fs.statSync(VAULT).isDirectory()) throw new Error(`fonte do sync não existe: ${VAULT} (defina KAIZEN_SOURCE; só quem mantém o vault precisa de sync, core/ já vem no pacote)`);
  const { parts, missing, unlisted } = plan(VAULT);
  if (missing.length) throw new Error(`faltam no vault (${VAULT}): ${missing.join(", ")}`);
  fs.rmSync(dest, { recursive: true, force: true });
  for (const [from, to] of parts) copy(path.join(VAULT, from), path.join(dest, coreRel(to)));
  sanitizeTree(dest);
  return { parts, unlisted, ...overlay(dest, tdir, stamp) };
}

function sync(argv) {
  const { parts, unlisted, stale, orphans } = build(CORE_DIR, path.join(PKG, "translations"), argv.includes("--stamp"));
  for (const u of unlisted) console.warn(`aviso: peça do vault fora do sync: ${u} (acrescente a bin/sync.js ou a SKIP)`);
  for (const t of stale) console.warn(`aviso: a fonte de ${t} mudou desde a tradução; reveja translations/${t}`);
  for (const t of orphans) console.warn(`aviso: translations/${t} não tem peça correspondente em core/`);
  console.log(`sync: ${parts.length} peças de ${VAULT}`);
}

// ficheiros de core/ rastreados pelo git (o sync apaga os que a fonte já não gera)
function trackedCore() {
  const r = spawnSync("git", ["ls-files", "-z", "--", "core"], { cwd: PKG, encoding: "utf8" });
  return r.status === 0 ? r.stdout.split("\0").filter(Boolean).map((f) => f.replace(/^core\//, "")) : [];
}

// compara o que o sync geraria com core/ sem lhe tocar; sai 1 se estiver desatualizado
// ou se o sync apagaria ficheiros rastreados de core/
function syncCheck() {
  console.log(`sync --check: fonte ${VAULT}`);
  const tmp = fs.mkdtempSync(path.join(require("os").tmpdir(), "kaizen-check-"));
  try {
    const tdir = path.join(tmp, "translations");
    if (fs.existsSync(path.join(PKG, "translations"))) copy(path.join(PKG, "translations"), tdir);
    const fresh = path.join(tmp, "core");
    build(fresh, tdir, false);
    const a = files(fresh);
    const b = files(CORE_DIR);
    const diff = [...new Set([...a, ...b])].filter((f) => !/__pycache__\/|\.pyc$/.test(f)).filter((f) => !a.includes(f) || !b.includes(f) || sha(fs.readFileSync(path.join(fresh, f))) !== sha(fs.readFileSync(path.join(CORE_DIR, f))));
    for (const f of diff) console.log(`desatualizado: core/${f}`);
    const removed = trackedCore().filter((f) => !a.includes(f) && !/__pycache__\/|\.pyc$/.test(f));
    for (const f of removed) console.log(`removeria rastreado: core/${f}`);
    console.log(`sync --check: ${diff.length} diferenças, ${removed.length} remoções de ficheiros rastreados`);
    process.exit(diff.length || removed.length ? 1 : 0);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

module.exports = { run: (argv) => (argv.includes("--check") ? syncCheck() : sync(argv)) };
