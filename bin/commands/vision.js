"use strict";
// `kaizen vision init|validate|resumo`: VISION.md por projeto, a entrada da factory (core/scripts/sp-visao.py, stdlib, sem rede).
const path = require("path");
const { py } = require("./python.js");

const SUBS = ["init", "validate", "resumo", "decompor"];

function run(args) {
  const [sub] = args;
  if (!SUBS.includes(sub)) {
    console.error("uso: kaizen vision <init <projeto> [--dir D] [--force] | validate <VISION.md> | resumo <VISION.md> | decompor <VISION.md> [--repo R] [--gate CMD] [--priority P] [--dry-run]>");
    return sub ? 1 : 0;
  }
  const script = sub === "decompor" ? "sp-decompor.py" : "sp-visao.py";
  return py([path.join(__dirname, "..", "..", "core", "scripts", script), ...args.slice(sub === "decompor" ? 1 : 0)], process.cwd());
}

module.exports = { run };
