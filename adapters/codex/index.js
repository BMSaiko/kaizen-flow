"use strict";
const { remap, agentsBlock } = require("../util");

// Codex lê skills em .agents/skills e AGENTS.md; sem hooks equivalentes (degrada para instruções)
function render(core) {
  return {
    files: remap(core, [["skills/", ".agents/skills/"], ["commands/", ".kaizen/commands/"], ["scripts/", "scripts/"]]),
    agents: agentsBlock(core, ".agents/skills", ".kaizen/commands"),
  };
}

module.exports = { render, name: "codex" };
