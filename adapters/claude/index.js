"use strict";
const { remap } = require("../util");

const GUARD = 'python -I "$CLAUDE_PROJECT_DIR/scripts/context-guard.py"';
const PAINEL = 'python -I "$CLAUDE_PROJECT_DIR/scripts/kf_painel_hook.py"';
const HOOKS = {
  UserPromptSubmit: [{ hooks: [{ type: "command", command: GUARD }, { type: "command", command: PAINEL }] }],
  Stop: [{ hooks: [{ type: "command", command: PAINEL }] }],
  Notification: [{ hooks: [{ type: "command", command: PAINEL }] }],
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

module.exports = { render };
