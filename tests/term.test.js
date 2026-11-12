"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const BIN = path.join(__dirname, "..", "bin", "kaizen.js");
const run = (...a) => spawnSync("node", [BIN, ...a], { encoding: "utf8", env: { ...process.env, WEZTERM_PANE: "", TMUX_PANE: "" } });

test("term --help lista ls|fila|michi|limpar|retomar|orq", () => {
  const r = run("term", "--help");
  assert.strictEqual(r.status, 0);
  for (const s of ["ls", "fila", "michi", "limpar", "retomar", "orq"]) assert.match(r.stdout, new RegExp(`^  ${s}\\b`, "m"));
});

test("term sem argumentos mostra a ajuda; subcomando desconhecido falha", () => {
  assert.strictEqual(run("term").status, 0);
  const r = run("term", "xx");
  assert.strictEqual(r.status, 1);
  assert.match(r.stderr, /desconhecido/);
});

test("term orq: por implementar, rc 2", () => {
  for (const s of ["orq"]) {
    const r = run("term", s);
    assert.strictEqual(r.status, 2, s);
    assert.match(r.stderr, /por implementar/);
  }
});

test("init instala os scripts de term (wez, painel_backend, open-doc)", () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "kaizen-term-"));
  assert.strictEqual(run("init", d, "--harness", "claude").status, 0);
  for (const f of ["wez.py", "painel_backend.py", "open-doc.py", "kf_term_ls.py", "kf_term_arranque.py", "kf_term_limpar.py", "wez-layouts/dev.json"]) {
    assert.ok(fs.existsSync(path.join(d, "scripts", f)), f);
  }
});

test("term ls num projeto limpo: rc 0, sem SPs, --json devolve []", () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "kaizen-ls-"));
  assert.strictEqual(run("init", d, "--harness", "claude").status, 0);
  const vazio = fs.mkdtempSync(path.join(os.tmpdir(), "kaizen-ls-estado-"));
  const env = { ...process.env, WEZTERM_PANE: "", TMUX_PANE: "", SP_FILA_ROOT: vazio };
  const t = spawnSync("node", [BIN, "term", "ls"], { encoding: "utf8", env, cwd: d });
  assert.strictEqual(t.status, 0, t.stderr);
  assert.match(t.stdout, /sem SPs/);
  assert.match(t.stderr, /aviso/);
  const j = spawnSync("node", [BIN, "term", "ls", "--json"], { encoding: "utf8", env, cwd: d });
  assert.strictEqual(j.status, 0);
  assert.deepStrictEqual(JSON.parse(j.stdout), []);
});

test("term michi/fila num projeto limpo: sem elegíveis rc 0; SP inexistente rc 2 sem lançar nada", () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "kaizen-arranque-"));
  assert.strictEqual(run("init", d, "--harness", "claude").status, 0);
  const env = { ...process.env, WEZTERM_PANE: "", TMUX_PANE: "" };
  const t = (...a) => spawnSync("node", [BIN, "term", ...a], { encoding: "utf8", env, cwd: d, input: "" });
  const m = t("michi");
  assert.strictEqual(m.status, 0, m.stderr);
  assert.match(m.stdout, /sem SPs elegíveis/);
  const f = t("fila");
  assert.strictEqual(f.status, 0, f.stderr);
  assert.match(f.stdout, /sem programas/);
  const x = t("michi", "--slug", "nao-existe", "--sim");
  assert.strictEqual(x.status, 2);
  assert.match(x.stderr, /não elegível/);
});
