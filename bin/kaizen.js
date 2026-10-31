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
  if (!ADAPTERS[harness]) { console.error(`erro: --harness requer um de claude|codex|agents-md (recebido: ${harness === undefined ? "nada" : harness})`); process.exit(1); }
}
const fi = argv.indexOf("--fix");
const fix = fi >= 0 && !!argv.splice(fi, 1);
const [cmd, arg] = argv;
const cmds = {
  init: () => init(arg, harness),
  sync: () => require("./commands/sync.js").run(argv),
  usage: () => process.exit(usage("usage", argv.slice(1))),
  report: () => process.exit(usage("report", argv.slice(1))),
  doctor: () => process.exit(doctor(arg, harness, fix)),
  status: () => process.exit(py(["scripts/sp-list.py", "--all"], path.resolve(arg || "."))),
  audit: () => require("./commands/audit.js").run(arg),
};
if (!Object.hasOwn(cmds, cmd)) {
  console.log("kaizen <init [repo] [--harness claude|codex|agents-md] | doctor [repo] [--harness h] [--fix] | status [repo] | usage [flags] | report [--week YYYY-WNN] [flags] | audit [dir] | sync [--check|--stamp]>");
  process.exit(cmd ? 1 : 0);
}
try {
  cmds[cmd]();
} catch (e) {
  console.error(`erro: ${e.message}`);
  process.exit(1);
}
