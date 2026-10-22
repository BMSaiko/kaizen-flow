"use strict";

const MARKER = "<!-- kaizen-flow -->";

// mapeia o núcleo para destinos: prefixo de origem -> prefixo de destino
function remap(core, map) {
  const files = [];
  for (const f of core) {
    for (const [from, to] of map) {
      if (f.rel.startsWith(from)) {
        files.push({ path: to + f.rel.slice(from.length), data: f.data });
        break;
      }
    }
  }
  return files;
}

function skillNames(core) {
  return [...new Set(core.filter((f) => /^skills\/[^/]+\/SKILL\.md$/.test(f.rel)).map((f) => f.rel.split("/")[1]))];
}

// bloco de AGENTS.md acrescentado (nunca substituído); o marcador torna a operação idempotente
function agentsBlock(core, skillsDir, commandsDir) {
  const lines = [MARKER, "## Kaizen flow", "", "Workflow: SP (super prompt = user story) + michi (improvement cycle).", "", "Skills (read the SKILL.md before using one):"];
  for (const n of skillNames(core)) lines.push(`- \`${skillsDir}/${n}/SKILL.md\``);
  lines.push("", `Command prompts live in \`${commandsDir}/\`. Helper scripts live in \`scripts/\` (run with \`python -I\`).`,
    "", "No context hook in this harness: when the context gets long, run `python -I scripts/sp-handoff.py --launch <sp.md> --harness <claude|codex>` (uses tmux/WezTerm if present, otherwise copies the resume prompt).", MARKER, "");
  return lines.join("\n");
}

module.exports = { MARKER, remap, skillNames, agentsBlock };
