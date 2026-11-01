"use strict";
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const SKILLS = ["michi", "super-prompt", "grill-me", "dr", "dp", "da", "brainstorm", "swot", "pentest", "review-ciclo", "pr-fase"];
const COMMAND_RE = /^(sp(-[a-z]+)*|handoff)\.md$/;
const SCRIPT_RE = /^(sp|doc)[-_][a-z_-]+\.py$/;
const SCRIPT_NAMES = ["context-guard.py", "context-budget.py", "handoff.py", "handoff_pane.py", "handoff_spawn.py", "sp_progresso.py", "skill-cut.py", "kaizen_config.py", "kaizen_engine.py", "kaizen_hooks.py", "wt_redirect.py", "pentest.py", "test_pentest.py", "review_ciclo.py", "test_review_ciclo.py", "pr_corpo.py", "test_pr_corpo.py", "test_kaizen_engine.py", "test_kaizen_hooks.py", "test_michi_tree_close.py"];
// testes que ficam no vault: afirmam textos em português ou dependem do vault inteiro
const SKIP = new Set(["test_michi_nucleo.py", "test_context_guard.py", "test_e2e_kaizen_pacote.py", "test_e2e_kaizen_sp.py", "michi-checkpoint.py", "test_michi_checkpoint.py", "michi-escopo.py", "test_michi_escopo.py", "test_guard_escopo.py", "test_wt_redirect.py"]);
// ficheiros do vault com nomes de kaizen que ainda assim não entram no pacote vão para SKIP; o resto avisa
const RELATED_RE = /^(test_)?(sp|doc|handoff|kaizen|michi)[-_.]/;

// fixtures dos testes do sp-fila (test_sp_fila.py)
const FIXTURES = "scripts/fixtures/par-watch";

const ls = (dir) => (fs.existsSync(dir) ? fs.readdirSync(dir) : []);

// devolve { parts: [[origem, destino]], missing: [...], unlisted: [...] } sem tocar em disco
function plan(vault) {
  const parts = [];
  const missing = [];
  for (const s of SKILLS) {
    if (!fs.existsSync(path.join(vault, ".claude", "skills", s))) missing.push(`.claude/skills/${s}`);
    else parts.push([`.claude/skills/${s}`, `.claude/skills/${s}`]);
  }
  const commands = ls(path.join(vault, ".claude", "commands")).filter((n) => COMMAND_RE.test(n));
  for (const n of commands) parts.push([`.claude/commands/${n}`, `.claude/commands/${n}`]);
  for (const need of ["sp.md", "sp-list.md", "sp-handoff.md"]) if (!commands.includes(need)) missing.push(`.claude/commands/${need}`);

  const scripts = ls(path.join(vault, "scripts"));
  const chosen = new Set(scripts.filter((n) => SCRIPT_RE.test(n)));
  for (const n of SCRIPT_NAMES) {
    if (scripts.includes(n)) chosen.add(n);
    else missing.push(`scripts/${n}`);
  }
  for (const n of [...chosen]) {
    const t = `test_${n.replace(/-/g, "_")}`;
    if (!n.startsWith("test_") && scripts.includes(t) && !SKIP.has(t)) chosen.add(t);
  }
  for (const n of [...chosen].sort()) parts.push([`scripts/${n}`, `scripts/${n}`]);
  if (fs.existsSync(path.join(vault, FIXTURES))) parts.push([FIXTURES, FIXTURES]);

  const unlisted = scripts.filter((n) => n.endsWith(".py") && !chosen.has(n) && !SKIP.has(n) && RELATED_RE.test(n)).map((n) => `scripts/${n}`);
  return { parts, missing, unlisted };
}

// true se o caminho do vault (relativo, com "/") é uma peça do sync; usado pelo hook do vault
function owns(rel) {
  const m = rel.match(/^\.claude\/skills\/([^/]+)\//);
  if (m) return SKILLS.includes(m[1]);
  const c = rel.match(/^\.claude\/commands\/([^/]+)$/);
  if (c) return COMMAND_RE.test(c[1]);
  if (rel.startsWith(`${FIXTURES}/`)) return true;
  const sc = rel.match(/^scripts\/([^/]+\.py)$/);
  if (!sc) return false;
  const n = sc[1];
  if (SKIP.has(n)) return false;
  if (SCRIPT_RE.test(n) || SCRIPT_NAMES.includes(n)) return true;
  const t = n.match(/^test_(.+)\.py$/);
  if (!t) return false;
  const base = `${t[1]}.py`;
  return [base, base.replace(/_/g, "-")].some((x) => SCRIPT_RE.test(x) || SCRIPT_NAMES.includes(x));
}

const sha = (buf) => crypto.createHash("sha256").update(buf).digest("hex");

// ficheiros em dir (relativos, com "/")
function files(dir) {
  const out = [];
  (function walk(d) {
    for (const e of ls(d)) {
      const p = path.join(d, e);
      if (fs.statSync(p).isDirectory()) walk(p);
      else out.push(path.relative(dir, p).replace(/\\/g, "/"));
    }
  })(dir);
  return out.sort();
}

// sobrepõe translations/ (EN) ao core/ gerado; o manifesto guarda o hash da fonte que foi traduzida
function overlay(core, tdir, stamp) {
  const manifestPath = path.join(tdir, "sources.json");
  const manifest = fs.existsSync(manifestPath) ? JSON.parse(fs.readFileSync(manifestPath, "utf8")) : {};
  const next = {};
  const stale = [];
  const orphans = [];
  for (const rel of files(tdir).filter((f) => f !== "sources.json")) {
    const dst = path.join(core, rel);
    if (!fs.existsSync(dst)) { orphans.push(rel); continue; }
    const h = sha(fs.readFileSync(dst));
    next[rel] = stamp || !manifest[rel] ? h : manifest[rel];
    if (manifest[rel] && manifest[rel] !== h && !stamp) stale.push(rel);
    fs.copyFileSync(path.join(tdir, rel), dst);
  }
  if (stamp) fs.writeFileSync(manifestPath, JSON.stringify(next, null, 2) + "\n");
  else if (Object.keys(next).length && JSON.stringify(next) !== JSON.stringify(manifest)) fs.writeFileSync(manifestPath, JSON.stringify(next, null, 2) + "\n");
  return { stale, orphans };
}

module.exports = { plan, overlay, owns, files, sha, SKILLS };
