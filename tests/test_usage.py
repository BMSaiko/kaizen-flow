import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "usage"))
import kaizen_usage as ku  # noqa: E402


def jl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def claude_row(ts, mid, model="claude-sonnet-5-5", i=1000, o=500, cr=2000, cw=400):
    return {"type": "assistant", "timestamp": ts, "requestId": "r" + mid,
            "message": {"id": mid, "model": model, "usage": {
                "input_tokens": i, "output_tokens": o, "cache_read_input_tokens": cr,
                "cache_creation_input_tokens": cw}}}


def codex_session(path, model, usages):
    rows = [{"timestamp": "2026-10-20T10:00:00Z", "type": "session_meta", "payload": {"id": "abcdef0123456789"}},
            {"timestamp": "2026-10-20T10:00:01Z", "type": "turn_context", "payload": {"model": model}}]
    for n, (last, total) in enumerate(usages):
        rows.append({"timestamp": f"2026-10-20T10:0{n + 2}:00Z", "type": "event_msg",
                     "payload": {"type": "token_count", "info": {"last_token_usage": last, "total_token_usage": total}}})
    rows.append({"timestamp": "2026-10-20T10:09:00Z", "type": "event_msg", "payload": {"type": "token_count", "info": None}})
    jl(path, rows)


class PricingTest(unittest.TestCase):
    def rec(self, model, **kw):
        return {"model": model, "in": 0, "out": 0, "cache_read": 0, "cache_write": 0, **kw}

    def test_cost_per_million(self):
        p = ku.Pricing({"m": {"in": 2.0, "out": 10.0, "cache_read": 0.1}})
        r = self.rec("m", **{"in": 1_000_000, "out": 1_000_000, "cache_read": 1_000_000, "cache_write": 1_000_000})
        self.assertAlmostEqual(p.cost(r), 2.0 + 10.0 + 0.1 + 2.5)

    def test_longest_prefix_wins(self):
        p = ku.Pricing({"gpt": {"in": 1, "out": 1}, "gpt-mini": {"in": 0.1, "out": 0.1}})
        self.assertEqual(p.lookup("gpt-mini-2026-01-01")["in"], 0.1)

    def test_unknown_model_is_none_not_error(self):
        self.assertIsNone(ku.Pricing({}).cost(self.rec("mystery")))

    def test_bundled_file_loads(self):
        self.assertIsNotNone(ku.Pricing.load().lookup("claude-sonnet-5-5-20261001"))

    def test_load_custom_file(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "p.json"
            f.write_text(json.dumps({"models": {"gpt-x": {"in": 1.0, "out": 2.0}}}), encoding="utf-8")
            self.assertEqual(ku.Pricing.load(f).lookup("gpt-x")["out"], 2.0)


class SourcesTest(unittest.TestCase):
    def test_claude_dedupes_by_message(self):
        with tempfile.TemporaryDirectory() as d:
            row = claude_row("2026-10-20T10:00:00Z", "m1")
            jl(Path(d) / "proj" / "11112222-aaaa.jsonl",
               [row, row, claude_row("2026-10-20T10:01:00Z", "m2"), {"type": "user", "message": {"content": "hi"}}])
            recs = ku.ClaudeTranscripts(d).read()
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0]["session"], "11112222")
        self.assertEqual((recs[0]["in"], recs[0]["out"], recs[0]["cache_read"], recs[0]["cache_write"]), (1000, 500, 2000, 400))

    def test_codex_splits_cached_input_and_skips_repeats(self):
        u1 = {"input_tokens": 1000, "cached_input_tokens": 600, "output_tokens": 50, "total_tokens": 1050}
        u2 = {"input_tokens": 1200, "cached_input_tokens": 1000, "output_tokens": 80, "total_tokens": 1280}
        t1 = {"total_tokens": 1050}
        t2 = {"total_tokens": 2330}
        with tempfile.TemporaryDirectory() as d:
            codex_session(Path(d) / "2026" / "10" / "20" / "rollout-x.jsonl", "gpt-5-codex", [(u1, t1), (u1, t1), (u2, t2)])
            recs = ku.CodexSessions(d).read()
        self.assertEqual([(r["in"], r["cache_read"], r["out"]) for r in recs], [(400, 600, 50), (200, 1000, 80)])
        self.assertEqual({r["model"] for r in recs}, {"gpt-5-codex"})
        self.assertEqual(recs[0]["session"], "abcdef01")

    def test_empty_or_missing_root(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(ku.CodexSessions(d).read(), [])
            self.assertEqual(ku.ClaudeTranscripts(Path(d) / "none").read(), [])


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        jl(d / "c" / "proj" / "aaaa1111.jsonl", [claude_row("2026-10-20T10:00:00Z", "m1", i=1_000_000, o=0, cr=0, cw=0)])
        u = {"input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 10, "total_tokens": 110}
        codex_session(d / "x" / "2026" / "rollout-1.jsonl", "gpt-unpriced", [(u, {"total_tokens": 110})])
        self.argv = ["--repo", str(d), "--claude-root", str(d / "c"), "--codex-root", str(d / "x")]
        self.d = d

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ku.main(list(args))
        return rc, buf.getvalue()

    def test_usage_totals_and_unpriced_warning(self):
        rc, out = self.run_cli("usage", *self.argv)
        self.assertEqual(rc, 0)
        self.assertIn("2026-10-20", out)
        self.assertIn("claude-sonnet-5-5", out)
        self.assertIn("| gpt-unpriced | 1 | 10 | 0 | n/a |", out)
        self.assertIn("Warning: no price for gpt-unpriced", out)
        self.assertIn("| claude-sonnet-5-5 | 1 | 0 | 0 | 2.00 |", out)

    def test_source_filter(self):
        _, out = self.run_cli("usage", *self.argv, "--source", "codex")
        self.assertNotIn("claude-sonnet-5-5", out)

    def test_config_prices_make_codex_priceable(self):
        (self.d / "p.json").write_text(json.dumps({"models": {"gpt-unpriced": {"in": 10.0, "out": 20.0}}}), encoding="utf-8")
        (self.d / "kaizen.config.json").write_text(json.dumps({"prices": "p.json", "sources": ["codex"]}), encoding="utf-8")
        _, out = self.run_cli("usage", *self.argv)
        self.assertIn("| gpt-unpriced | 1 | 10 | 0 | 0.00 |", out)
        self.assertNotIn("Warning", out)

    def test_report_writes_week_file_metrics_only(self):
        rc, out = self.run_cli("report", *self.argv, "--week", "2026-W43")
        path = Path(out.strip())
        self.assertEqual(path, self.d / "reports" / "usage" / "2026-W43.md")
        text = path.read_text(encoding="utf-8")
        self.assertIn("week: 2026-W43", text)
        self.assertIn("2026-10-20", text)

    def test_report_empty_week(self):
        _, out = self.run_cli("report", *self.argv, "--week", "2026-W01", "--print")
        self.assertIn("No usage this week.", out)

    def test_unknown_source_exits(self):
        with self.assertRaises(SystemExit):
            self.run_cli("usage", *self.argv, "--source", "nope")


if __name__ == "__main__":
    unittest.main()
