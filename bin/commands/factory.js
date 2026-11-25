"use strict";
// `kaizen factory run|status|stop|step|approve|pause|resume|skip|takeover <projeto>`: factory autónoma de um projeto (core/scripts/kf_factory.py, stdlib, sem rede).
const path = require("path");
const { py } = require("./python.js");

const SUBS = ["run", "status", "stop", "step", "approve", "pause", "resume", "skip", "takeover"];

function run(args) {
  const [sub, projeto] = args;
  if (!SUBS.includes(sub) || !projeto) {
    console.error("uso: kaizen factory <run <projeto> [--visao VISION.md] [--repo R] [--dir D] [--release-feito] [--manual|--auto] | status|stop|step <projeto> | approve <projeto> [--so a,b] | pause|resume|skip|takeover <projeto> <sp>>");
    return sub ? 2 : 0;
  }
  return py([path.join(__dirname, "..", "..", "core", "scripts", "kf_factory.py"), ...args], process.cwd());
}

module.exports = { run };
