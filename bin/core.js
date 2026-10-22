"use strict";
const fs = require("fs");
const path = require("path");

const CORE = path.resolve(__dirname, "..", "core");

// devolve [{ rel, data }] com rel relativo a core/ e separador "/"
function loadCore(dir = CORE) {
  const out = [];
  (function walk(d) {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p);
      else out.push({ rel: path.relative(dir, p).replace(/\\/g, "/"), data: fs.readFileSync(p) });
    }
  })(dir);
  return out.sort((a, b) => (a.rel < b.rel ? -1 : 1));
}

module.exports = { loadCore, CORE };
