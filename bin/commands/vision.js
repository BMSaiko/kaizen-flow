"use strict";
// `kaizen vision init|validate|resumo`: VISION.md por projeto, a entrada da factory (core/scripts/sp-visao.py, stdlib, sem rede).
const path = require("path");
const { py } = require("./python.js");

const SUBS = ["init", "validate", "resumo"];

function run(args) {
  const [sub] = args;
  if (!SUBS.includes(sub)) {
    console.error("uso: kaizen vision <init <projeto> [--dir D] [--force] | validate <VISION.md> | resumo <VISION.md>>");
    return sub ? 1 : 0;
  }
  return py([path.join(__dirname, "..", "..", "core", "scripts", "sp-visao.py"), ...args], process.cwd());
}

module.exports = { run };
