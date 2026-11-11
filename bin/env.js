"use strict";
const os = require("os");

// lançamento do Python: sem site/ambiente do utilizador (-I) e sem .pyc (-B, PYTHONDONTWRITEBYTECODE)
const PY_FLAGS = ["-I", "-B"];
const pyEnv = () => ({ ...process.env, PYTHONDONTWRITEBYTECODE: "1" });

// diretório pessoal; um só sítio para o sync e o doctor
const homedir = () => os.homedir();

module.exports = { PY_FLAGS, pyEnv, homedir };
