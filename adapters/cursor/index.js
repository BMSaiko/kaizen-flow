"use strict";
const { remap, agentsBlock } = require("../util");

const SKILLS = ".cursor/skills";
const COMMANDS = ".kaizen/commands";
const FRONT = ["---", "description: Kaizen flow: SP + michi workflow, skills and helper scripts", "alwaysApply: true", "---", ""].join("\n");

// Cursor lê skills em .cursor/skills e regras .mdc em .cursor/rules (alwaysApply). O caminho dos comandos
// do Cursor não está verificado, por isso os prompts ficam em .kaizen/commands e a regra aponta para lá.
function render(core) {
  const files = remap(core, [["skills/", `${SKILLS}/`], ["commands/", `${COMMANDS}/`], ["scripts/", "scripts/"]]);
  files.push({ path: ".cursor/rules/kaizen-flow.mdc", data: Buffer.from(FRONT + agentsBlock(core, SKILLS, COMMANDS)) });
  return { files };
}

module.exports = { render };
