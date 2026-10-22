import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "usage"))
import kaizen_usage as ku  # noqa: E402
from test_usage import claude_row, codex_session, jl  # noqa: E402


def run(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            rc = ku.main(list(argv))
        except SystemExit as e:
            rc = e.code
    return rc, buf.getvalue()


class HardeningTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_num(self):
        self.assertEqual([ku.num(v) for v in (5, 5.9, "7", -3, None, True, float("nan"), float("inf"), [1])],
                         [5, 5, 0, 0, 0, 0, 0, 0, 0])

    def test_bad_since_days_week_exit_with_message(self):
        for args in (["usage", "--since", "foo"], ["usage", "--days", "0"], ["usage", "--days", "-2"],
                     ["report", "--week", "2026-W99", "--print"], ["report", "--week", "x", "--print"]):
            rc, _ = run(*args, "--repo", str(self.tmp), "--claude-root", str(self.tmp), "--codex-root", str(self.tmp))
            self.assertIsInstance(rc, str, args)  # sys.exit(message), never a traceback

    def test_prices_without_out_or_malformed(self):
        for body in ('{"models": {"m": {"in": 1}}}', '{"models": []}', "[]", "not json",
                     '{"models": {"m": {"in": "1", "out": 2}}}'):
            f = self.tmp / "p.json"
            f.write_text(body, encoding="utf-8")
            with self.assertRaises(SystemExit):
                ku.Pricing.load(f)
        with self.assertRaises(SystemExit):
            ku.Pricing.load(self.tmp / "missing.json")

    def test_sources_string_in_config(self):
        (self.tmp / ku.CONFIG_NAME).write_text(json.dumps({"sources": "claude"}), encoding="utf-8")
        self.assertEqual(ku.read_config(self.tmp)["sources"], ["claude"])
        (self.tmp / ku.CONFIG_NAME).write_text(json.dumps({"sources": 5, "reportsDir": 3, "prices": 1}), encoding="utf-8")
        cfg = ku.read_config(self.tmp)
        self.assertEqual((cfg["sources"], cfg["reportsDir"], cfg["prices"]), (["claude", "codex"], "reports/usage", None))

    def test_claude_rows_without_ids_are_not_collapsed(self):
        rows = []
        for n in range(3):
            r = claude_row(f"2026-10-20T10:0{n}:00Z", "x")
            del r["message"]["id"], r["requestId"]
            rows.append(r)
        jl(self.tmp / "proj" / "s1.jsonl", rows)
        self.assertEqual(len(ku.ClaudeTranscripts(str(self.tmp)).read()), 3)

    def test_bad_token_values_and_unreadable_lines(self):
        r = claude_row("2026-10-20T10:00:00Z", "a")
        r["message"]["usage"].update(input_tokens="9", output_tokens=-4, cache_read_input_tokens=None)
        p = self.tmp / "proj" / "s1.jsonl"
        jl(p, [r])
        with open(p, "ab") as fh:
            fh.write(b"\xff\xfe not json\n[1,2]\n\"str\"\n")
        (self.tmp / "proj" / "dir.jsonl").mkdir()  # a directory named like a transcript
        recs = ku.ClaudeTranscripts(str(self.tmp)).read()
        self.assertEqual((len(recs), recs[0]["in"], recs[0]["out"], recs[0]["cache_read"]), (1, 0, 0, 0))

    def test_codex_bad_values(self):
        codex_session(self.tmp / "a" / "rollout-x.jsonl", "gpt-x",
                      [({"input_tokens": "5", "output_tokens": -1, "cached_input_tokens": 99}, {"t": 1})])
        recs = ku.CodexSessions(str(self.tmp)).read()
        self.assertEqual((len(recs), recs[0]["in"], recs[0]["out"], recs[0]["cache_read"]), (1, 0, 0, 99))

    def test_non_string_timestamp_and_model(self):
        r = claude_row("2026-10-20T10:00:00Z", "a")
        r["message"]["model"] = 7
        bad = claude_row("2026-10-20T10:00:00Z", "b")
        bad["timestamp"] = 12345
        jl(self.tmp / "proj" / "s1.jsonl", [r, bad])
        recs = ku.ClaudeTranscripts(str(self.tmp)).read()
        self.assertEqual([x["model"] for x in recs], ["?"])


if __name__ == "__main__":
    unittest.main()
