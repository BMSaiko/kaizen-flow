"use strict";
const path = require("path");
const { spawnSync } = require("child_process");

const PKG = path.resolve(__dirname, "..", "..");

// "python" não existe em macOS/Linux modernos; procura um interpretador Python 3 real (o stub da Microsoft Store falha o --version)
let PYTHON;
function pythonCmd() {
  if (PYTHON !== undefined) return PYTHON;
  const cands = [process.env.KAIZEN_PYTHON, "python3", "python", "py"].filter(Boolean);
  PYTHON = cands.find((c) => {
    const r = spawnSync(c, ["--version"], { encoding: "utf8" });
    return r.status === 0 && /^Python 3\./.test(`${r.stdout}${r.stderr}`);
  }) || null;
  return PYTHON;
}

function py(args, cwd) {
  const cmd = pythonCmd();
  if (!cmd) { console.error("falta: Python 3 no PATH (ou KAIZEN_PYTHON)"); return 1; }
  const r = spawnSync(cmd, ["-I", "-B", ...args], { cwd, stdio: "inherit", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
  return r.status === null ? 1 : r.status;
}

// `kaizen usage|report [flags]` -> usage/kaizen_usage.py (a raiz do repo é o diretório atual)
function usage(sub, rest) {
  const cmd = pythonCmd();
  if (!cmd) { console.error("falta: Python 3 no PATH (ou KAIZEN_PYTHON)"); return 1; }
  const r = spawnSync(cmd, ["-I", "-B", path.join(PKG, "usage", "kaizen_usage.py"), sub, ...rest], { stdio: "inherit", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
  return r.status === null ? 1 : r.status;
}

module.exports = { pythonCmd, py, usage };
