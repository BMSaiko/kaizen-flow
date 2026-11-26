"use strict";
const fs = require("fs");
const { spawnSync } = require("child_process");
const path = require("path");
const { plan, overlay, files, sha } = require("../sync.js");
const { homedir } = require("../env.js");
const { loadCore } = require("../core.js");

const PKG = path.resolve(__dirname, "..", "..");
const CORE_DIR = path.join(PKG, "core");
const VAULT = process.env.KAIZEN_SOURCE || path.join(homedir(), "Documents", "Second-Brain");

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

// o vault é pessoal: o que o identifica vira marcador ({{chave}}) ao copiar para core/;
// --to-vault repõe os valores de kaizen.config.json; init/doctor renderizam com os defeitos neutros
const { MARKER_KEYS, render } = require("../markers.js");
const VAULT_DEFAULTS = { userFullName: "Bruno Silva", userName: "BMS", agentName: "HEIMDALL", agentSlug: "heimdall" };
const TEXT_EXT = /\.(md|py|json|txt|js|toml)$/i;
const esc = (x) => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// defaults=true só no --from-vault (o vault do autor); o --to-vault usa só a config, senão os defeitos neutros
function readJson(f) {
  if (!fs.existsSync(f)) return {};
  try { return JSON.parse(fs.readFileSync(f, "utf8")); } catch (e) { throw new Error(`JSON inválido em ${f}: ${e.message}`); }
}

function vaultConfig(vault, defaults = false) {
  const cfg = readJson(path.join(vault, "kaizen.config.json"));
  return defaults ? { ...VAULT_DEFAULTS, ...cfg } : cfg;
}

// valores mais longos primeiro (Bruno Silva antes de BMS); só as chaves conhecidas, nunca palavras soltas
function sanitizer(cfg) {
  const rules = [[/[A-Za-z]:[\\/]+Users[\\/]+bruno/gi, "~"]];
  const keys = MARKER_KEYS.filter((k) => cfg[k]).sort((a, b) => cfg[b].length - cfg[a].length);
  for (const k of keys) {
    const v = cfg[k];
    const b1 = /^\w/.test(v) ? "\\b" : "";
    const b2 = /\w$/.test(v) ? "\\b" : "";
    rules.push([new RegExp(b1 + esc(v) + b2, "g"), `{{${k}}}`]);
  }
  // outras grafias do agente (ex.: «Heimdall») não têm marcador: saem com perdas
  if (cfg.agentSlug) {
    const s = cfg.agentSlug;
    rules.push([new RegExp((/^\w/.test(s) ? "\\b" : "") + esc(s) + (/\w$/.test(s) ? "\\b" : ""), "gi"), "kaizen"]);
  }
  return (t) => rules.reduce((acc, [re, to]) => acc.replace(re, to), t);
}

function sanitizeTree(p, clean) {
  if (fs.statSync(p).isDirectory()) return fs.readdirSync(p).forEach((n) => sanitizeTree(path.join(p, n), clean));
  if (TEXT_EXT.test(p)) fs.writeFileSync(p, clean(fs.readFileSync(p, "utf8")));
}

// gera core/ em dest a partir do vault; devolve o que o sync reporta
function build(dest, tdir, stamp) {
  if (!fs.existsSync(VAULT) || !fs.statSync(VAULT).isDirectory()) throw new Error(`fonte do sync não existe: ${VAULT} (defina KAIZEN_SOURCE; só quem mantém o vault precisa de sync, core/ já vem no pacote)`);
  const { parts, missing, unlisted } = plan(VAULT);
  if (missing.length) throw new Error(`faltam no vault (${VAULT}): ${missing.join(", ")}`);
  fs.rmSync(dest, { recursive: true, force: true });
  for (const [from, to] of parts) copy(path.join(VAULT, from), path.join(dest, coreRel(to)));
  sanitizeTree(dest, sanitizer(vaultConfig(VAULT, true)));
  return { parts, unlisted, ...overlay(dest, tdir, stamp) };
}

// valores pessoais (chaves de marcador) que não podem ficar em core/
function leaks(cfg, text) {
  return MARKER_KEYS.filter((k) => cfg[k]).filter((k) => {
    const v = cfg[k];
    return new RegExp((/^\w/.test(v) ? "\\b" : "") + esc(v) + (/\w$/.test(v) ? "\\b" : "")).test(text);
  });
}

// --only <caminho> (repetível): caminho relativo a core/ (com ou sem «core/»), ficheiro ou pasta
function onlyArgs(argv) {
  const out = [];
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--only") {
      if (!argv[i + 1] || argv[i + 1].startsWith("--")) throw new Error("--only precisa de um caminho (relativo a core/)");
      out.push(argv[++i].replace(/\\/g, "/").replace(/^core\//, "").replace(/\/+$/, ""));
    }
  }
  return out;
}
const covered = (only, rel) => only.some((o) => rel === o || rel.startsWith(`${o}/`));

const git = (args) => spawnSync("git", args, { cwd: PKG, encoding: "utf8" });

// escrever em core/ só numa worktree do repo e com core/ limpo (nada por commitar que se perca)
function guardTree() {
  const top = git(["rev-parse", "--show-toplevel"]);
  if (top.status !== 0 || path.resolve(top.stdout.trim()) !== path.resolve(PKG)) return; // pacote sem git (cópia/instalado): nada a verificar
  const gd = git(["rev-parse", "--path-format=absolute", "--git-dir"]).stdout.trim();
  const cd = git(["rev-parse", "--path-format=absolute", "--git-common-dir"]).stdout.trim();
  if (gd && cd && path.resolve(gd) === path.resolve(cd)) throw new Error("--from-vault escreve em core/: corra-o numa worktree do kaizen-flow, nunca no checkout principal (ou use --dry-run)");
  const st = git(["status", "--porcelain", "--", "core"]);
  if (st.stdout.trim()) throw new Error(`core/ tem alterações por commitar; faça commit antes de --from-vault (ou use --dry-run):\n${st.stdout.trimEnd()}`);
}

// vault → core/ sem apagar: atualiza peças que existem nos dois lados; novas só com --only
function sync(argv) {
  const dry = argv.includes("--dry-run");
  const only = onlyArgs(argv);
  if (!dry) guardTree();
  const tmp = fs.mkdtempSync(path.join(require("os").tmpdir(), "kaizen-from-"));
  try {
    const tdir = path.join(tmp, "translations");
    if (fs.existsSync(path.join(PKG, "translations"))) copy(path.join(PKG, "translations"), tdir);
    const fresh = path.join(tmp, "core");
    const { parts, unlisted, stale, orphans } = build(fresh, tdir, false);
    const a = files(fresh).filter((f) => !/__pycache__\/|\.pyc$/.test(f));
    const have = new Set(files(CORE_DIR));
    const cfg = vaultConfig(VAULT, true);
    const upd = [], add = [], skipped = [];
    for (const f of a) {
      const data = fs.readFileSync(path.join(fresh, f));
      if (have.has(f)) {
        if (sha(fs.readFileSync(path.join(CORE_DIR, f))) !== sha(data)) upd.push(f);
      } else if (covered(only, f) || !have.size) add.push(f);
      else skipped.push(f);
    }
    const kept = [...have].filter((f) => !a.includes(f) && !/__pycache__\/|\.pyc$/.test(f));
    const sel = (list) => (only.length ? list.filter((f) => covered(only, f)) : list);
    const todo = [...sel(upd), ...add];
    for (const f of todo) {
      const l = TEXT_EXT.test(f) ? leaks(cfg, fs.readFileSync(path.join(fresh, f), "utf8")) : [];
      if (l.length) throw new Error(`core/${f} ficaria com dados pessoais (${l.join(", ")}); nada foi escrito`);
    }
    for (const f of todo) console.log(`${dry ? "mudaria" : "atualiza"}: core/${f}${have.has(f) ? "" : " (novo)"}`);
    for (const f of sel(skipped)) console.log(`ignorado (novo; use --only ${f}): core/${f}`);
    if (kept.length) console.log(`mantido: ${kept.length} ficheiros de core/ que o vault não tem (nunca são apagados)`);
    for (const f of kept) if (dry) console.log(`removeria (evitado): core/${f}`);
    if (!dry) for (const f of todo) copy(path.join(fresh, f), path.join(CORE_DIR, f));
    for (const u of unlisted) console.warn(`aviso: peça do vault fora do sync: ${u} (acrescente a bin/sync.js ou a SKIP)`);
    for (const t of stale) console.warn(`aviso: a fonte de ${t} mudou desde a tradução; reveja translations/${t}`);
    for (const t of orphans) console.warn(`aviso: translations/${t} não tem peça correspondente em core/`);
    console.log(`sync${dry ? " --dry-run" : ""}: ${todo.length} peças ${dry ? "a atualizar" : "atualizadas"} de ${parts.length} (${VAULT})`);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
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

// sentido repo → vault: core/ é a fonte; o vault recebe as peças com os marcadores renderizados
const MANIFEST_FILE = ".kaizen-sync.json";
const vaultRel = (rel) => rel.replace(/^(skills|commands)\//, ".claude/$1/");

// [{ rel, data }] das peças do vault tal como o --to-vault as escreveria
function renderVault(vault) {
  const cfg = vaultConfig(vault);
  return loadCore(CORE_DIR, cfg).map(({ rel, data }) => ({ rel: vaultRel(rel), data }));
}

function readManifest(vault) {
  return readJson(path.join(vault, MANIFEST_FILE));
}

// ficheiro do vault mudou desde o último --to-vault (ou, sem registo, difere do que seria escrito)?
function localEdit(vault, manifest, rel, data) {
  const f = path.join(vault, rel);
  if (!fs.existsSync(f)) return false;
  const cur = sha(fs.readFileSync(f));
  if (cur === sha(data)) return false;
  return manifest[rel] ? manifest[rel] !== cur : true;
}

// órfãs: rels do manifesto anterior que o core/ já não gera e cujo ficheiro ainda existe no vault
// (manifesto vem do disco: rel inválido ou fora do vault é ignorado com aviso, nunca apagado)
function vaultOrphans(vault, manifest, pieces) {
  const current = new Set(pieces.map((p) => p.rel));
  const root = path.resolve(vault);
  const out = [];
  for (const [rel, hash] of Object.entries(manifest || {})) {
    if (current.has(rel)) continue;
    const f = path.resolve(root, rel);
    if (typeof rel !== "string" || !rel || path.isAbsolute(rel) || rel.split(/[\\/]/).includes("..") || !f.startsWith(root + path.sep)) {
      console.error(`aviso: entrada inválida no manifesto ignorada: ${rel}`);
      continue;
    }
    if (!fs.existsSync(f) || !fs.statSync(f).isFile()) continue;
    out.push({ rel, f, edited: sha(fs.readFileSync(f)) !== hash });
  }
  return out;
}

function toVault(argv) {
  if (!fs.existsSync(VAULT) || !fs.statSync(VAULT).isDirectory()) throw new Error(`vault não existe: ${VAULT} (defina KAIZEN_SOURCE)`);
  const pieces = renderVault(VAULT);
  const manifest = readManifest(VAULT);
  if (argv.includes("--check")) {
    console.log(`sync --to-vault --check: vault ${VAULT}`);
    const diff = pieces.filter(({ rel, data }) => { const f = path.join(VAULT, rel); return !fs.existsSync(f) || sha(fs.readFileSync(f)) !== sha(data); });
    for (const { rel } of diff) console.log(`${fs.existsSync(path.join(VAULT, rel)) ? "difere" : "falta"}: ${rel}`);
    const orph = vaultOrphans(VAULT, manifest, pieces);
    for (const { rel } of orph) console.log(`remover: ${rel}`);
    console.log(`sync --to-vault --check: ${diff.length} diferenças, ${orph.length} remoções`);
    process.exit(diff.length || orph.length ? 1 : 0);
  }
  const orph = vaultOrphans(VAULT, manifest, pieces);
  const conflicts = pieces.filter(({ rel, data }) => localEdit(VAULT, manifest, rel, data)).map((p) => p.rel)
    .concat(orph.filter((o) => o.edited).map((o) => o.rel));
  if (conflicts.length && !argv.includes("--force")) {
    for (const c of conflicts) console.error(`editado no vault: ${c}`);
    throw new Error(`${conflicts.length} peças editadas no vault desde o último sync; leve-as para o repo (core/) ou repita com --force`);
  }
  const next = {};
  let written = 0;
  for (const { rel, data } of pieces) {
    const f = path.join(VAULT, rel);
    next[rel] = sha(data);
    if (fs.existsSync(f) && sha(fs.readFileSync(f)) === next[rel]) continue;
    fs.mkdirSync(path.dirname(f), { recursive: true });
    fs.writeFileSync(f, data);
    written++;
  }
  for (const { f } of orph) fs.rmSync(f);
  fs.writeFileSync(path.join(VAULT, MANIFEST_FILE), JSON.stringify(next, null, 2) + "\n");
  console.log(`sync --to-vault: ${written} escritos de ${pieces.length} peças, ${orph.length} removidas em ${VAULT}${conflicts.length ? ` (${conflicts.length} sobrescritos com --force)` : ""}`);
}

function run(argv) {
  if (argv.includes("--to-vault")) return toVault(argv);
  if (!argv.includes("--from-vault")) {
    throw new Error("kaizen sync precisa de sentido: --to-vault (core/ → vault, o normal) ou --from-vault (vault → core/, antigo, só na transição)");
  }
  console.warn("aviso: --from-vault é o sentido antigo (vault → core/); a fonte de verdade é core/ — use --to-vault");
  return argv.includes("--check") ? syncCheck() : sync(argv);
}

module.exports = { run };
