"use strict";
const fs = require("fs");
const path = require("path");
const { render } = require("./markers.js");

const TEXT_EXT = /\.(md|py|json|txt|js|toml)$/i;

const CACHES = new Set(["__pycache__", ".pytest_cache", ".ruff_cache", ".hypothesis"]);
const CORE = path.resolve(__dirname, "..", "core");

// devolve [{ rel, data }] com rel relativo a core/ e separador "/"; os marcadores {{chave}}
// dos ficheiros de texto saem renderizados com cfg (defeitos neutros sem config)
function loadCore(dir = CORE, cfg = {}) {
  const out = [];
  (function walk(d) {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      if (CACHES.has(e.name) || e.name.endsWith(".pyc")) continue;
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p);
      else {
        const raw = fs.readFileSync(p);
        const data = TEXT_EXT.test(e.name) ? Buffer.from(render(raw.toString("utf8"), cfg), "utf8") : raw;
        out.push({ rel: path.relative(dir, p).replace(/\\/g, "/"), data });
      }
    }
  })(dir);
  return out.sort((a, b) => (a.rel < b.rel ? -1 : 1));
}

module.exports = { loadCore };
