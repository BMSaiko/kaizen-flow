const { readdirSync, mkdirSync } = require("fs");
const { spawnSync } = require("child_process");
// KAIZEN_COVERAGE=1: relatório de cobertura (JS nativo, Python via pytest-cov) em coverage/; falha abaixo do limiar de package.json (coverageThreshold)
const cov = process.env.KAIZEN_COVERAGE === "1";
const thr = require("../package.json").coverageThreshold || {};
const jsMin = (thr.js || {}).lines, pyMin = (thr.python || {}).lines;
const files = readdirSync("tests").filter((f) => f.endsWith(".test.js")).map((f) => "tests/" + f);
if (cov) mkdirSync("coverage", { recursive: true });
const jsArgs = ["--test", ...(cov ? ["--experimental-test-coverage"] : []), ...files];
const js = spawnSync(process.execPath, jsArgs, { stdio: cov ? ["inherit", "pipe", "inherit"] : "inherit" });
if (cov) {
  process.stdout.write(js.stdout);
  require("fs").writeFileSync("coverage/js.txt", js.stdout);
}
if (js.status !== 0) process.exit(js.status || 1);
if (cov && jsMin !== undefined) {
  const m = /all files\s*\|\s*([\d.]+)/.exec(js.stdout.toString());
  const got = m ? parseFloat(m[1]) : NaN;
  if (!(got >= jsMin)) {
    console.error(`cobertura JS (linhas) ${got}% abaixo do limiar ${jsMin}% (package.json: coverageThreshold)`);
    process.exit(1);
  }
}
// Python: pytest corre tests/ (unittest) e core/scripts/test_*.py num só processo
const pyArgs = ["-m", "pytest", "-q", ...(cov ? ["--cov=core/scripts", "--cov-report=term", "--cov-report=xml:coverage/python.xml", ...(pyMin !== undefined ? [`--cov-fail-under=${pyMin}`] : [])] : []), "tests", "core/scripts"];
const py = spawnSync("python", pyArgs, { stdio: "inherit" });
if (py.error || py.status === null) {
  console.error("pytest em falta ou não arrancou: pip install pytest" + (cov ? " pytest-cov" : ""));
  process.exit(1);
}
process.exit(py.status);
