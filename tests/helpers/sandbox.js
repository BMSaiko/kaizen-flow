"use strict";
// Sandbox dos testes e2e: tmpdir com espaço e acento, HOME isolado, sem painel real, `kaizen init` pronto.
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn, spawnSync } = require("child_process");

const ROOT = path.join(__dirname, "..", "..");
const BIN = path.join(ROOT, "bin", "kaizen.js");
const PY = process.env.KAIZEN_PYTHON || (process.platform === "win32" ? "python" : "python3");
const TIMEOUT = 30_000;

function envIsolado(dir) {
  const home = path.join(dir, ".home");
  fs.mkdirSync(home, { recursive: true });
  const env = { ...process.env, HOME: home, USERPROFILE: home, PYTHONIOENCODING: "utf-8",
    GIT_AUTHOR_NAME: "t", GIT_AUTHOR_EMAIL: "t@t", GIT_COMMITTER_NAME: "t", GIT_COMMITTER_EMAIL: "t@t" };
  for (const k of ["HERDR_PANE_ID", "WEZTERM_PANE", "TMUX_PANE", "TMUX", "WEZTERM_UNIX_SOCKET", "KAIZEN_REPO", "SB_VAULT"]) delete env[k];
  return env;
}

function correr(cmd, args, cwd, env, extra = {}) {
  const r = spawnSync(cmd, args, { cwd, env, encoding: "utf8", timeout: TIMEOUT, ...extra });
  return { status: r.status, stdout: r.stdout || "", stderr: r.stderr || "", out: (r.stdout || "") + (r.stderr || "") };
}

/** Cria o sandbox; `init: false` deixa só o tmpdir com `git init`. */
function sandbox({ init = true, harness = "claude" } = {}) {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), "kaizen e2e "));
  const dir = path.join(base, "projeto ção");
  fs.mkdirSync(dir);
  const env = envIsolado(base);
  const sb = {
    base, dir, env,
    git: (...a) => correr("git", a, dir, env),
    kz: (...a) => correr("node", [BIN, ...a], dir, env),
    py: (script, ...a) => correr(PY, ["-I", path.join(dir, "scripts", script), ...a], dir, env),
    pyCore: (script, ...a) => correr(PY, ["-I", path.join(ROOT, script), ...a], dir, env),
    escrever: (rel, texto) => { const p = path.join(dir, rel); fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, texto); return p; },
    ler: (rel) => fs.readFileSync(path.join(dir, rel), "utf8"),
    existe: (rel) => fs.existsSync(path.join(dir, rel)),
    limpar: () => fs.rmSync(base, { recursive: true, force: true }),
  };
  sb.git("init", "-q");
  if (init) {
    const r = sb.kz("init", dir, "--harness", harness);
    if (r.status !== 0) throw new Error(`kaizen init falhou: ${r.out}`);
  }
  return sb;
}

/** Caminho relativo do SP impresso pelo sp-new (linha com `.md`). */
function caminhoSp(sb, saida) {
  const linha = saida.split(/\r?\n/).find((l) => l.trim().endsWith(".md"));
  if (!linha) throw new Error(`sp-new sem caminho: ${saida}`);
  return path.relative(sb.dir, linha.trim());
}

/** Preenche as 8 secções, `gates:` e `## Decisões` para o sp-validate dar rc 0. */
function preencherSp(sb, rel) {
  let t = sb.ler(rel).replace(/\r\n/g, "\n");
  t = t.replace(/^---\n([\s\S]*?)\n---\n/, (m, fm) => `---\n${fm}\ngates:\n  - cmd: node --version\n---\n`);
  t = t.replace(/(## \d\.[^\n]*\n)\n+(?=## |$)/g, "$1Texto de teste.\n\n");
  t = t.trimEnd() + "\n\n## Decisões\n- Decisão de teste.\n";
  fs.writeFileSync(path.join(sb.dir, rel), t);
}

/** Mata um processo filho (Windows: taskkill da árvore; resto: SIGKILL). */
function matar(child) {
  if (process.platform === "win32") spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"]);
  else child.kill("SIGKILL");
}

/** Lança `python -c código` em segundo plano e espera pela linha `pronto` no stdout. */
function lancarPy(sb, codigo) {
  const child = spawn(PY, ["-c", codigo], { cwd: sb.dir, env: sb.env, stdio: ["ignore", "pipe", "pipe"] });
  return new Promise((res, rej) => {
    let buf = "";
    const t = setTimeout(() => { matar(child); rej(new Error("processo filho não ficou pronto")); }, TIMEOUT);
    child.stdout.on("data", (d) => { buf += d; if (buf.includes("pronto")) { clearTimeout(t); res(child); } });
    child.on("exit", (c) => { clearTimeout(t); rej(new Error(`filho saiu cedo rc ${c}: ${buf}`)); });
  });
}

function esperarSaida(child) {
  return new Promise((res) => { if (child.exitCode !== null || child.signalCode) res(); else child.on("exit", () => res()); });
}

module.exports = { ROOT, BIN, PY, TIMEOUT, sandbox, caminhoSp, preencherSp, matar, lancarPy, esperarSaida };
