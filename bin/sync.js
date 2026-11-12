"use strict";
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const SKILLS = ["michi", "super-prompt", "grill-me", "dr", "dp", "da", "brainstorm", "swot", "pentest", "review-ciclo", "pr-fase", "orq"];
const COMMAND_RE = /^(sp(-[a-z]+)*|handoff)\.md$/;
const SCRIPT_RE = /^(sp|doc)[-_][a-z_-]+\.py$/;
const MANIFEST = JSON.parse(fs.readFileSync(path.join(__dirname, "sync-manifest.json"), "utf8"));
const SCRIPT_NAMES = MANIFEST.scriptNames;
// SKIP (no manifesto): testes que ficam no vault; afirmam textos em português ou dependem do vault inteiro
const SKIP = new Set(MANIFEST.skip);
// ficheiros do vault com nomes de kaizen que ainda assim não entram no pacote vão para SKIP; o resto avisa
const RELATED_RE = /^(test_)?(sp|doc|handoff|kaizen|michi)[-_.]/;

// fixtures dos testes do sp-fila (test_sp_fila.py)
const FIXTURES = "scripts/fixtures/par-watch";
// layouts guardados do wez.py
const LAYOUTS = "scripts/wez-layouts";
// config lida pelos scripts em ../.claude/ (modelos.py): fica em core/.claude/
const CONFIGS = [".claude/modelos.json"];

const ls = (dir) => (fs.existsSync(dir) ? fs.readdirSync(dir) : []);

// regra única: o nome de um ficheiro de scripts/ é peça do sync? (usada por plan() e owns())
function isScriptPiece(n) {
  if (SKIP.has(n)) return false;
  if (SCRIPT_RE.test(n) || SCRIPT_NAMES.includes(n)) return true;
  const t = n.match(/^test_(.+)\.py$/);
  if (!t) return false;
  const base = `${t[1]}.py`;
  return [base, base.replace(/_/g, "-")].some((x) => SCRIPT_RE.test(x) || SCRIPT_NAMES.includes(x));
}

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
  for (const c of CONFIGS) {
    if (fs.existsSync(path.join(vault, c))) parts.push([c, c]);
    else missing.push(c);
  }

  const scripts = ls(path.join(vault, "scripts"));
  for (const n of SCRIPT_NAMES) if (!scripts.includes(n)) missing.push(`scripts/${n}`);
  const chosen = new Set(scripts.filter(isScriptPiece));
  for (const n of [...chosen].sort()) parts.push([`scripts/${n}`, `scripts/${n}`]);
  if (fs.existsSync(path.join(vault, FIXTURES))) parts.push([FIXTURES, FIXTURES]);
  if (fs.existsSync(path.join(vault, LAYOUTS))) parts.push([LAYOUTS, LAYOUTS]);

  const unlisted = scripts.filter((n) => n.endsWith(".py") && !chosen.has(n) && !SKIP.has(n) && RELATED_RE.test(n)).map((n) => `scripts/${n}`);
  return { parts, missing, unlisted };
}

// true se o caminho do vault (relativo, com "/") é uma peça do sync; usado pelo hook do vault
function owns(rel) {
  const m = rel.match(/^\.claude\/skills\/([^/]+)\//);
  if (m) return SKILLS.includes(m[1]);
  const c = rel.match(/^\.claude\/commands\/([^/]+)$/);
  if (c) return COMMAND_RE.test(c[1]);
  if (rel.startsWith(`${FIXTURES}/`) || rel.startsWith(`${LAYOUTS}/`)) return true;
  const sc = rel.match(/^scripts\/([^/]+\.py)$/);
  return sc ? isScriptPiece(sc[1]) : false;
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
