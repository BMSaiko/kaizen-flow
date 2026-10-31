"use strict";
const fs = require("fs");
const path = require("path");
const { loadCore } = require("../core.js");
const { MARKER } = require("../../adapters/util.js");
const { detectMode } = require("../mode.js");
const { ADAPTERS } = require("./adapters.js");
const { init, readSettings, configDir } = require("./init.js");
const { pythonCmd, py } = require("./python.js");

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
  const root = path.join(dir, configDir(dir, "spRoot", "knowledge/projects/kaizen"));
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
  if (harness !== "claude") console.log("context hook: none for this harness (degraded); run the handoff by hand when the context gets long, see the AGENTS.md block");
  console.log(rc === 0 ? `doctor: ok (${sps.length} SPs)` : "doctor: problemas");
  return rc;
}

module.exports = { doctor };
