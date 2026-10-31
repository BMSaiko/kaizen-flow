"use strict";
const fs = require("fs");
const path = require("path");
const { loadCore } = require("../core.js");
const { MARKER } = require("../../adapters/util.js");
const { ADAPTERS } = require("./adapters.js");

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

// pasta (relativa a dest) vinda de kaizen.config.json; chave em falta, tipo errado ou caminho fora de dest -> defeito
function configDir(dest, key, fallback) {
  let cfg = {};
  try { cfg = JSON.parse(fs.readFileSync(path.join(dest, "kaizen.config.json"), "utf8").replace(/^﻿/, "")); } catch (e) { /* sem config válida: defeitos */ }
  const v = cfg && typeof cfg === "object" ? cfg[key] : undefined;
  if (typeof v !== "string" || !v || path.isAbsolute(v)) return fallback;
  const rel = path.relative(dest, path.resolve(dest, v));
  return rel.startsWith("..") || path.isAbsolute(rel) ? fallback : v;
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
  const spRoot = path.join(dest, configDir(dest, "spRoot", "knowledge/projects/kaizen"));
  // DR/DP seguem docsRoot só se a config o define; sem ele ficam ao lado dos SPs (comportamento anterior)
  const docsRel = configDir(dest, "docsRoot", "");
  const docsRoot = docsRel ? path.join(dest, docsRel) : spRoot;
  for (const d of ["sp", "dr", "dp"]) for (const s of ["TODO", "Doing", "Done"]) fs.mkdirSync(path.join(d === "sp" ? spRoot : docsRoot, "_default", d, s), { recursive: true });
  console.log(`init (${harness}): ${n} peças copiadas para ${dest}`);
  return n;
}

module.exports = { init, readSettings, configDir };
