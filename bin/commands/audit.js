"use strict";
const path = require("path");

function run(arg) {
  const hits = require("../audit.js").audit(path.resolve(arg || "."));
  for (const h of hits) console.log(`${h.file}:${h.line} [${h.pattern}]`);
  console.log(`audit: ${hits.length} hits`);
  process.exit(hits.length ? 1 : 0);
}

module.exports = { run };
