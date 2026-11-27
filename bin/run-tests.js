const { readdirSync, mkdirSync } = require("fs");
const { spawnSync } = require("child_process");
// KAIZEN_COVERAGE=1: relatório de cobertura (JS nativo, Python via pytest-cov) em coverage/; falha abaixo do limiar de package.json (coverageThreshold)
const cov = process.env.KAIZEN_COVERAGE === "1";
const thr = require("../package.json").coverageThreshold || {};
const jsMin = (thr.js || {}).lines, pyMin = (thr.python || {}).lines;
const files = readdirSync("tests").filter((f) => f.endsWith(".test.js")).map((f) => "tests/" + f);
if (cov) mkdirSync("coverage", { recursive: true });
// temporários de todos os testes (JS, pytest e filhos) numa pasta da execução, apagada à saída: sem ela, /tmp esgota os inodes
const runTmp = require("fs").mkdtempSync(require("path").join(require("os").tmpdir(), "kaizen-run-"));
for (const k of ["TMPDIR", "TEMP", "TMP"]) process.env[k] = runTmp;
process.on("exit", () => { try { require("fs").rmSync(runTmp, { recursive: true, force: true }); } catch {} });
const jsArgs = ["--test", ...(cov ? ["--experimental-test-coverage", `--test-coverage-exclude=${require("os").tmpdir().replace(/\\/g, "/")}/**`] : []), ...files];
// sem cobertura, o pytest arranca já em paralelo com o JS (saída para ficheiro, impressa no fim): ~25 % menos de tempo total
// pytest-xdist (opcional): se instalado, reparte os testes pelos núcleos (-n auto); senão corre em série
const xdist = spawnSync("python", ["-c", "import xdist"], { stdio: "ignore" }).status === 0 ? ["-n", "auto"] : [];
let bg = null;
if (!cov) {
  const out = require("path").join(require("os").tmpdir(), `kaizen-pytest-${process.pid}.txt`);
  const fd = require("fs").openSync(out, "w");
  bg = { out, proc: require("child_process").spawn("python", ["-m", "pytest", "-q", ...xdist, "tests", "core/scripts"], { stdio: ["ignore", fd, fd] }) };
  bg.done = new Promise((res) => { bg.proc.on("error", (e) => res({ error: e })); bg.proc.on("close", (status) => res({ status })); });
}
const js = spawnSync(process.execPath, jsArgs, { stdio: cov ? ["inherit", "pipe", "inherit"] : "inherit" });
if (cov) {
  process.stdout.write(js.stdout);
  require("fs").writeFileSync("coverage/js.txt", js.stdout);
}
const fim = (code) => process.exit(code);
if (js.status !== 0) { if (bg) bg.proc.kill(); fim(js.status || 1); }
if (cov && jsMin !== undefined) {
  const m = /all files\s*\|\s*([\d.]+)/.exec(js.stdout.toString());
  const got = m ? parseFloat(m[1]) : NaN;
  if (!(got >= jsMin)) {
    console.error(`cobertura JS (linhas) ${got}% abaixo do limiar ${jsMin}% (package.json: coverageThreshold)`);
    process.exit(1);
  }
}
// Python: pytest corre tests/ (unittest) e core/scripts/test_*.py num só processo
async function main() {
  let py;
  if (bg) {
    py = await bg.done;
    process.stdout.write(require("fs").readFileSync(bg.out));
  } else {
    py = spawnSync("python", ["-m", "pytest", "-q", "--cov=core/scripts", "--cov-report=term", "--cov-report=xml:coverage/python.xml", ...(pyMin !== undefined ? [`--cov-fail-under=${pyMin}`] : []), "tests", "core/scripts"], { stdio: "inherit" });
  }
  if (py.error || py.status === null) {
    console.error("pytest em falta ou não arrancou: pip install pytest" + (cov ? " pytest-cov" : ""));
    fim(1);
  }
  fim(py.status);
}
main();
