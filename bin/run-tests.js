const { readdirSync } = require("fs");
const { spawnSync } = require("child_process");
const files = readdirSync("tests").filter((f) => f.endsWith(".test.js")).map((f) => "tests/" + f);
const js = spawnSync(process.execPath, ["--test", ...files], { stdio: "inherit" });
if (js.status !== 0) process.exit(js.status || 1);
const py = spawnSync("python", ["-I", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"], { stdio: "inherit" });
process.exit(py.status === null ? 1 : py.status);
