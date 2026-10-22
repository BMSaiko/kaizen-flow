"use strict";
const { remap, agentsBlock } = require("../util");

// fallback genérico: tudo em .kaizen/ e referido a partir de AGENTS.md
function render(core) {
  return {
    files: remap(core, [["skills/", ".kaizen/skills/"], ["commands/", ".kaizen/commands/"], ["scripts/", "scripts/"]]),
    agents: agentsBlock(core, ".kaizen/skills", ".kaizen/commands"),
  };
}

module.exports = { render, name: "agents-md" };
