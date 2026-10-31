"use strict";
const { agentsAdapter } = require("../util");

// fallback genérico: tudo em .kaizen/ e referido a partir de AGENTS.md
module.exports = agentsAdapter(".kaizen/skills", ".kaizen/commands");
