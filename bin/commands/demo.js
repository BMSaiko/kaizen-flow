"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");
const { init } = require("./init.js");
const { pythonCmd } = require("./python.js");
const { PY_FLAGS, pyEnv } = require("../env.js");

const PROJECT = "demo";

// corre um comando no projeto de exemplo; falha (exceção) se o rc não for 0
function run(cmd, args, cwd, label, okRcs = [0]) {
  const r = spawnSync(cmd, args, { cwd, encoding: "utf8", env: pyEnv() });
  if (!okRcs.includes(r.status)) throw new Error(`${label} falhou (rc ${r.status}): ${(r.stderr || r.stdout || "").trim()}`);
  for (const line of (r.stdout || "").split(/\r?\n/).filter(Boolean)) console.log(`    ${line}`);
  return r.stdout || "";
}

// `kaizen demo [--keep]`: cria um repo temporário, instala o kaizen-flow e percorre um SP pelo ciclo (sem rede nem agente)
function demo(args) {
  const unknown = args.filter((a) => a !== "--keep");
  if (unknown.length) throw new Error(`argumentos desconhecidos: ${unknown.join(" ")} (uso: kaizen demo [--keep])`);
  const keep = args.includes("--keep");
  const python = pythonCmd();
  if (!python) throw new Error("falta: Python 3 no PATH (ou KAIZEN_PYTHON)");
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "kaizen-demo-"));
  console.log(`demo: ${dir}`);
  const py = (script, rest, label, okRcs) => run(python, [...PY_FLAGS, path.join("scripts", script), ...rest], dir, label, okRcs);
  try {
    console.log("[init] repo git novo e peças do kaizen-flow (skills, comandos, scripts)");
    run("git", ["init", "-q"], dir, "git init");
    init(dir, "claude");
    const sps = path.join(dir, "knowledge", "projects", "kaizen", PROJECT, "sp");
    for (const s of ["TODO", "Doing", "Done"]) fs.mkdirSync(path.join(sps, s), { recursive: true });

    console.log("[sp-new] um SP (super prompt = user story) nasce em TODO com um gate verificável");
    const out = py("sp-new.py", ["--project", PROJECT, "--slug", "ola", "--priority", "P3", "--gate", "node --version"], "sp-new");
    const slug = path.basename(out.trim().split(/\r?\n/).pop().trim(), ".md");
    if (!slug) throw new Error("sp-new não devolveu o SP criado");

    console.log("[doing] o SP passa a Doing: o trabalho começa");
    py("sp-move.py", [slug, "doing"], "sp-move doing");

    console.log("[gates] os gates do SP correm e cada comando mostra o seu RC");
    py("sp-gates.py", [slug], "sp-gates");

    console.log("[done] gates verdes: o SP fecha em Done");
    py("sp-move.py", [slug, "done"], "sp-move done");

    console.log("[report] o report resume o que foi alterado, verificado e provado (rc 3 = «Dificuldades» vazia: o /reflect preenche-a num ciclo real)");
    py("sp-report.py", [slug], "sp-report", [0, 3]);

    console.log(`demo concluída: o ciclo SP -> gates -> Done correu em ${dir}${keep ? "" : " (apagado no fim; usa --keep para o guardar)"}`);
  } finally {
    if (!keep) fs.rmSync(dir, { recursive: true, force: true });
  }
}

module.exports = { demo };
