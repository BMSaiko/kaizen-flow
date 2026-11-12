"use strict";
const path = require("path");
const { py } = require("./python.js");

// subcomando -> { ajuda, script (relativo ao projeto), args fixos } ou { ajuda, pendente } quando o script ainda não existe
const SUBS = {
  ls: { ajuda: "painéis com SP, fase, estado e fila (--json, --fila X)", script: "scripts/kf_term_ls.py", args: [] },
  fila: { ajuda: "escolher um programa (preview) e lançar a fila num painel", script: "scripts/kf_term_arranque.py", args: ["fila"] },
  michi: { ajuda: "escolher um SP (preview) e lançar o michi num painel", script: "scripts/kf_term_arranque.py", args: ["michi"] },
  limpar: { ajuda: "limpar painéis e estado órfãos", pendente: "kaizenflow-term-limpeza-2026-11-12" },
  orq: { ajuda: "orquestrador de painéis (Claude Code)", pendente: "kaizenflow-term-orq-2026-11-12" },
};

function help() {
  const linhas = Object.entries(SUBS).map(([n, s]) => `  ${n.padEnd(7)}${s.ajuda}${s.pendente ? " (por implementar)" : ""}`);
  return `kaizen term <${Object.keys(SUBS).join("|")}> [args...]\n${linhas.join("\n")}`;
}

// devolve o código de saída; `cwd` é a raiz do projeto onde `kaizen init` instalou scripts/
function run(argv, cwd = process.cwd()) {
  const [sub, ...rest] = argv;
  if (!sub || sub === "--help" || sub === "-h" || sub === "help") { console.log(help()); return 0; }
  if (!Object.hasOwn(SUBS, sub)) { console.error(`erro: subcomando desconhecido: ${sub}\n${help()}`); return 1; }
  const s = SUBS[sub];
  if (s.pendente) { console.error(`kaizen term ${sub}: por implementar (${s.pendente})`); return 2; }
  return py([s.script, ...s.args, ...rest], path.resolve(cwd));
}

module.exports = { run, SUBS };
