const { readdirSync } = require("fs");
const { spawnSync } = require("child_process");
const files = readdirSync("tests").filter((f) => f.endsWith(".test.js")).map((f) => "tests/" + f);
const js = spawnSync(process.execPath, ["--test", ...files], { stdio: "inherit" });
if (js.status !== 0) process.exit(js.status || 1);
// Python: pytest corre tests/ (unittest) e core/scripts/test_*.py num só processo
const py = spawnSync("python", ["-m", "pytest", "-q", "tests", "core/scripts"], { stdio: "inherit" });
if (py.error || py.status === null) {
  console.error("pytest em falta ou não arrancou: pip install pytest");
  process.exit(1);
}
process.exit(py.status);
