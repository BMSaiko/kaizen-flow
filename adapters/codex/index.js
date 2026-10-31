"use strict";
const { agentsAdapter } = require("../util");

// Codex lê skills em .agents/skills e AGENTS.md; sem hooks equivalentes (degrada para instruções)
module.exports = agentsAdapter(".agents/skills", ".kaizen/commands");
