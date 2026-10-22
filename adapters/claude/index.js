"use strict";
const { remap } = require("../util");

const GUARD = 'python -I "$CLAUDE_PROJECT_DIR/scripts/context-guard.py"';
const HOOKS = {
  UserPromptSubmit: [{ hooks: [{ type: "command", command: GUARD }] }],
  PostToolUse: [
    { hooks: [{ type: "command", command: GUARD }] },
    { matcher: "Write|Edit", hooks: [{ type: "command", command: 'python -I "$CLAUDE_PROJECT_DIR/scripts/sp-validate-hook.py"' }] },
  ],
};

// puro: devolve ficheiros e hooks, não escreve nada
function render(core) {
  return {
    files: remap(core, [["skills/", ".claude/skills/"], ["commands/", ".claude/commands/"], ["scripts/", "scripts/"]]),
    settings: { hooks: HOOKS },
  };
}

module.exports = { render, name: "claude" };
