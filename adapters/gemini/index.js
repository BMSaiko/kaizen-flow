"use strict";
const { remap, agentsBlock } = require("../util");

const SKILLS = ".gemini/skills";
const COMMANDS = ".gemini/commands";

// separa o frontmatter simples (chave: valor) do corpo
function splitFront(text) {
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/.exec(text);
  if (!m) return { front: {}, body: text };
  const front = {};
  for (const line of m[1].split(/\r?\n/)) {
    const kv = /^([A-Za-z0-9_-]+):\s*(.*)$/.exec(line);
    if (!kv) continue;
    let v = kv[2].trim();
    if (v.length >= 2 && ((v[0] === '"' && v.endsWith('"')) || (v[0] === "'" && v.endsWith("'")))) v = v.slice(1, -1);
    front[kv[1]] = v;
  }
  return { front, body: m[2] };
}

// comando .md do núcleo -> .toml do Gemini CLI (prompt obrigatório, description opcional, {{args}} no lugar de $ARGUMENTS)
function toToml(data) {
  const { front, body } = splitFront(data.toString("utf8"));
  const lines = [];
  if (front.description) lines.push(`description = ${JSON.stringify(front.description)}`);
  lines.push(`prompt = ${JSON.stringify(body.replace(/\s*$/, "").replace(/\$ARGUMENTS/g, "{{args}}"))}`, "");
  return Buffer.from(lines.join("\n"));
}

// Gemini CLI lê skills em .gemini/skills, comandos em .gemini/commands/*.toml e o contexto em GEMINI.md
// (AGENTS.md só com context.fileName), por isso o bloco de anúncio vai para GEMINI.md.
function render(core) {
  const cmds = core.filter((f) => f.rel.startsWith("commands/") && f.rel.endsWith(".md"));
  const files = remap(core.filter((f) => !f.rel.startsWith("commands/")), [["skills/", `${SKILLS}/`], ["scripts/", "scripts/"]]);
  for (const f of cmds) files.push({ path: `${COMMANDS}/${f.rel.slice("commands/".length).replace(/\.md$/, ".toml")}`, data: toToml(f.data) });
  return { files, agents: agentsBlock(core, SKILLS, COMMANDS), agentsFile: "GEMINI.md" };
}

module.exports = { render };
