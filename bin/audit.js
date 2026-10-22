"use strict";
const fs = require("fs");
const path = require("path");

// padrões que nunca podem chegar ao repo público
const PATTERNS = [
  { name: "bruno", re: /bruno/i },
  { name: "heimdall", re: /heimdall/i },
  { name: "windows-user-path", re: /C:[\\/]+Users[\\/]/i },
  { name: "wikilink", re: /\[\[[^\][,"]+\]\]/ },
  { name: "verbose-guard", re: /verbose-guard/i },
];
const SKIP_DIRS = new Set([".git", "node_modules"]);
// o próprio auditor e o seu teste contêm os padrões por definição
const SKIP_FILES = new Set(["LICENSE", "bin/audit.js", "bin/kaizen.js", "docs/privacy-audit.md", "tests/audit.test.js"]);

function audit(root) {
  const hits = [];
  (function walk(dir) {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) {
        if (!SKIP_DIRS.has(e.name)) walk(p);
        continue;
      }
      const rel = path.relative(root, p).replace(/\\/g, "/");
      if (SKIP_FILES.has(rel)) continue;
      const buf = fs.readFileSync(p);
      if (buf.includes(0)) continue;
      buf.toString("utf8").split(/\r?\n/).forEach((line, i) => {
        for (const { name, re } of PATTERNS) if (re.test(line)) hits.push({ file: rel, line: i + 1, pattern: name });
      });
    }
  })(root);
  return hits;
}

module.exports = { audit, PATTERNS };
