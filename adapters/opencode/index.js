"use strict";
const { agentsAdapter } = require("../util");

// opencode lê skills em .opencode/skills, comandos .md em .opencode/commands e AGENTS.md na raiz; sem hook de contexto (degrada para instruções)
module.exports = agentsAdapter(".opencode/skills", ".opencode/commands");
