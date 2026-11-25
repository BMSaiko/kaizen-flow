"use strict";
// `kaizen factory run|status|stop <projeto>`: factory autónoma de um projeto (core/scripts/kf_factory.py, stdlib, sem rede).
const path = require("path");
const { py } = require("./python.js");

const SUBS = ["run", "status", "stop"];

function run(args) {
  const [sub, projeto] = args;
  if (!SUBS.includes(sub) || !projeto) {
    console.error("uso: kaizen factory <run <projeto> [--visao VISION.md] [--repo R] [--dir D] [--release-feito] | status <projeto> | stop <projeto>>");
    return sub ? 2 : 0;
  }
  return py([path.join(__dirname, "..", "..", "core", "scripts", "kf_factory.py"), ...args], process.cwd());
}

module.exports = { run };
