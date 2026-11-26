#!/usr/bin/env node
"use strict";
const path = require("path");
const { ADAPTERS } = require("./commands/adapters.js");
const { init } = require("./commands/init.js");
const { doctor } = require("./commands/doctor.js");
const { py, usage } = require("./commands/python.js");

const argv = process.argv.slice(2);
const hi = argv.indexOf("--harness");
let harness = "claude";
if (hi >= 0) {
  harness = argv.splice(hi, 2)[1];
  if (!ADAPTERS[harness]) { console.error(`erro: --harness requer um de ${Object.keys(ADAPTERS).join("|")} (recebido: ${harness === undefined ? "nada" : harness})`); process.exit(1); }
}
const fi = argv.indexOf("--fix");
const fix = fi >= 0 && !!argv.splice(fi, 1);
const ci = argv.indexOf("--codex-config");
const codexConfig = ci >= 0 ? argv.splice(ci, 2)[1] : undefined;
const mi = argv.indexOf("--metodo");
const metodo = mi >= 0 ? argv.splice(mi, 2)[1] : undefined;
if (mi >= 0 && !metodo) { console.error("erro: --metodo requer um de worktree-pr|worktree-merge|direto"); process.exit(1); }
const [cmd, arg] = argv;
const cmds = {
  init: () => init(arg, harness, metodo),
  sync: () => require("./commands/sync.js").run(argv),
  usage: () => process.exit(usage("usage", argv.slice(1))),
  report: () => process.exit(usage("report", argv.slice(1))),
  doctor: () => process.exit(doctor(arg, harness, fix, codexConfig)),
  status: () => process.exit(py(["scripts/sp-list.py", "--all"], path.resolve(arg || "."))),
  audit: () => require("./commands/audit.js").run(arg),
  catalog: () => process.exit(py([path.join(__dirname, "..", "catalog", "kf_catalogo.py"), ...argv.slice(1)], process.cwd())),
  demo: () => require("./commands/demo.js").demo(argv.slice(1)),
  term: () => process.exit(require("./commands/term.js").run(argv.slice(1))),
  resume: () => process.exit(py(["scripts/sp-resume.py", ...argv.slice(1)], process.cwd())),
  ds: () => process.exit(require("./commands/ds.js").run(argv.slice(1))),
  vision: () => process.exit(require("./commands/vision.js").run(argv.slice(1))),
  factory: () => process.exit(require("./commands/factory.js").run(argv.slice(1))),
  quality: () => process.exit(py([path.join(__dirname, "..", "core", "scripts", "kf_quality.py"), ...argv.slice(1)], process.cwd())),
  preflight: () => process.exit(py([path.join(__dirname, "..", "core", "scripts", "sp-preflight.py"), ...argv.slice(1), ...(fix ? ["--fix"] : [])], process.cwd())),
};
if (!Object.hasOwn(cmds, cmd)) {
  console.log(`kaizen <init [repo] [--metodo worktree-pr|worktree-merge|direto] [--harness ${Object.keys(ADAPTERS).join("|")}] | doctor [repo] [--harness h] [--fix] | status [repo] | usage [flags] | report [--week YYYY-WNN] [flags] | audit [dir] | catalog [render|--check|--json|--no-run] | sync [--check|--stamp] | term <ls|fila|michi|limpar|orq> | resume [slug] [--from <passo>] [--restart] | quality [--base REF] [--so etapa...] [--lista] | preflight [slug] [--repo dir] [--fix] [--json] | ds <init|validate|export> | vision <init|validate|resumo|decompor> | factory <run|status|stop> <projeto> | demo [--factory] [--keep]>`);
  process.exit(cmd ? 1 : 0);
}
try {
  cmds[cmd]();
} catch (e) {
  console.error(`erro: ${e.message}`);
  process.exit(1);
}
