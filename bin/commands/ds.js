"use strict";
// `kaizen ds init|validate|export`: design system do projeto atual (core/scripts/ds-*.py, stdlib, sem rede).
const path = require("path");
const { py } = require("./python.js");

const SCRIPTS = { init: "ds-init.py", validate: "ds-validate.py", export: "ds-export.py" };

function run(args) {
  const [sub, ...rest] = args;
  if (!Object.hasOwn(SCRIPTS, sub)) {
    console.error("uso: kaizen ds <init <projeto> [--primaria #hex] [--neutra #hex] [--force] | validate [--dir D] | export [--dir D] [--out D]>");
    return sub ? 1 : 0;
  }
  return py([path.join(__dirname, "..", "..", "core", "scripts", SCRIPTS[sub]), ...rest], process.cwd());
}

module.exports = { run };
