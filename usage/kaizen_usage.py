#!/usr/bin/env python3
"""Usage analysis for agent harness transcripts (metrics only, never conversation content).

Sources: Claude Code (~/.claude/projects/*/*.jsonl) and Codex CLI (~/.codex/sessions/**/*.jsonl).
Cost is the equivalent at API prices (a relative measure, not what a subscription charges).

  kaizen_usage.py usage [--days N | --since YYYY-MM-DD] [--source claude,codex]
  kaizen_usage.py report [--week YYYY-WNN] [--out DIR] [--print]
"""
import argparse
import glob
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

WINDOW = timedelta(hours=5)
HERE = Path(__file__).resolve().parent
CONFIG_NAME = "kaizen.config.json"
DEFAULTS = {"reportsDir": "reports/usage", "sources": ["claude", "codex"], "prices": None}


def read_config(repo):
    try:
        data = json.loads((Path(repo) / CONFIG_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**DEFAULTS, **(data if isinstance(data, dict) else {})}


class Pricing:
    def __init__(self, models):
        self.models = models

    @classmethod
    def load(cls, path=None):
        data = json.loads(Path(path or HERE / "prices.json").read_text(encoding="utf-8"))
        return cls(data.get("models", {}))

    def lookup(self, model):
        hits = [k for k in self.models if model.startswith(k)]
        return self.models[max(hits, key=len)] if hits else None

    def cost(self, rec):
        """USD for one record, or None when the model has no price."""
        p = self.lookup(rec["model"])
        if p is None:
            return None
        write = p.get("cache_write", p["in"] * 1.25)
        return (rec["in"] * p["in"] + rec["out"] * p["out"]
                + rec["cache_write"] * write + rec["cache_read"] * p.get("cache_read", p["in"])) / 1e6


def _ts(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()


def _rec(ts, session, model, i, o, cr, cw):
    return {"ts": ts, "session": session, "model": model, "in": i, "out": o, "cache_read": cr, "cache_write": cw}


class ClaudeTranscripts:
    name = "claude"

    def __init__(self, root=None):
        self.root = root or os.path.expanduser("~/.claude/projects")

    def read(self, since=None):
        seen, out = set(), []
        for path in glob.glob(os.path.join(self.root, "*", "*.jsonl")):
            sid = os.path.basename(path)[:8]
            with open(path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    m = d.get("message")
                    if d.get("type") != "assistant" or not isinstance(m, dict) or not m.get("usage"):
                        continue
                    key = (m.get("id"), d.get("requestId"))
                    if key in seen:
                        continue
                    seen.add(key)
                    try:
                        ts = _ts(d["timestamp"])
                    except (KeyError, ValueError):
                        continue
                    if since and ts < since:
                        continue
                    u = m["usage"]
                    out.append(_rec(ts, sid, m.get("model", "?"), u.get("input_tokens") or 0,
                                    u.get("output_tokens") or 0, u.get("cache_read_input_tokens") or 0,
                                    u.get("cache_creation_input_tokens") or 0))
        return sorted(out, key=lambda r: r["ts"])


class CodexSessions:
    """Codex rollout files: `turn_context` carries the model, `event_msg/token_count` the usage.

    `last_token_usage` is the per-request delta; `input_tokens` includes the cached part,
    so it is split into fresh input + cache read.
    """
    name = "codex"

    def __init__(self, root=None):
        self.root = root or os.path.expanduser("~/.codex/sessions")

    def read(self, since=None):
        out = []
        for path in glob.glob(os.path.join(self.root, "**", "*.jsonl"), recursive=True):
            sid, model, last_total = None, "?", None
            with open(path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    p = d.get("payload")
                    if not isinstance(p, dict):
                        continue
                    if d.get("type") == "session_meta":
                        sid = str(p.get("id") or p.get("session_id") or "")[:8] or None
                    elif d.get("type") == "turn_context":
                        model = p.get("model") or model
                    elif d.get("type") == "event_msg" and p.get("type") == "token_count":
                        info = p.get("info")
                        if not isinstance(info, dict) or not isinstance(info.get("last_token_usage"), dict):
                            continue
                        total = info.get("total_token_usage")
                        if total is not None and total == last_total:
                            continue  # repeated event, same cumulative total
                        last_total = total
                        try:
                            ts = _ts(d["timestamp"])
                        except (KeyError, ValueError):
                            continue
                        if since and ts < since:
                            continue
                        u = info["last_token_usage"]
                        cached = u.get("cached_input_tokens") or 0
                        out.append(_rec(ts, sid or os.path.basename(path)[-14:-6], model,
                                        max((u.get("input_tokens") or 0) - cached, 0),
                                        u.get("output_tokens") or 0, cached, 0))
        return sorted(out, key=lambda r: r["ts"])


SOURCES = {"claude": ClaudeTranscripts, "codex": CodexSessions}


def load_records(names, since=None, roots=None):
    recs = []
    for n in names:
        recs += SOURCES[n]((roots or {}).get(n)).read(since)
    return sorted(recs, key=lambda r: r["ts"])


def fmt(n):
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}K" if n >= 1e3 else str(n)


def usd(v):
    return "n/a" if v is None else f"{v:.2f}"


def aggregate(recs, pricing):
    """Totals by day, session, model and 5 h window; cost shows n/a when nothing was priced."""
    def blank():
        return {"req": 0, "out": 0, "cache_read": 0, "cost": 0.0, "priced": 0}
    r = {"day": defaultdict(blank), "session": defaultdict(blank), "model": defaultdict(blank),
         "windows": [], "unpriced": set(), "total": blank()}
    win = None
    for x in recs:
        c = pricing.cost(x)
        if c is None:
            r["unpriced"].add(x["model"])
        for bucket in (r["day"][x["ts"].strftime("%Y-%m-%d")], r["session"][x["session"]],
                       r["model"][x["model"]], r["total"]):
            bucket["req"] += 1
            bucket["out"] += x["out"]
            bucket["cache_read"] += x["cache_read"]
            if c is not None:
                bucket["cost"] += c
                bucket["priced"] += 1
        if win is None or x["ts"] >= win["start"] + WINDOW:
            win = {"start": x["ts"], "req": 0, "cost": 0.0}
            r["windows"].append(win)
        win["req"] += 1
        win["cost"] += c or 0.0
    return r


def cell(b):
    return usd(b["cost"] if b["priced"] else None)


def table(title, rows, label):
    L = [f"## {title}", f"| {label} | requests | output | cache read | $ |", "|---|---|---|---|---|"]
    return L + [f"| {k} | {b['req']} | {fmt(b['out'])} | {fmt(b['cache_read'])} | {cell(b)} |" for k, b in rows]


def render_text(agg, top=5):
    t = agg["total"]
    L = table("By day (cost = API-equivalent)", sorted(agg["day"].items()), "day")
    L += ["", f"TOTAL: {t['req']} requests · {len(agg['session'])} sessions · ${cell(t)}", ""]
    L += table("By model", sorted(agg["model"].items(), key=lambda kv: -kv[1]["cost"]), "model")
    L += [""] + table(f"Top {top} sessions", sorted(agg["session"].items(), key=lambda kv: -kv[1]["cost"])[:top], "session")
    L += ["", "## 5 h windows (start = first request)"]
    L += [f"- {w['start']:%Y-%m-%d %H:%M} · {w['req']} requests · ${w['cost']:.2f}" for w in agg["windows"][-12:]]
    if agg["unpriced"]:
        L += ["", f"Warning: no price for {', '.join(sorted(agg['unpriced']))} (cost n/a; add them to the prices file)."]
    return "\n".join(L)


def week_bounds(label):
    if label:
        y, w = label.split("-W")
        mon = date.fromisocalendar(int(y), int(w), 1)
    else:
        today = date.today()
        mon = today - timedelta(days=today.weekday() + 7)
    return mon, mon + timedelta(days=7)


def render_report(label, mon, nxt, agg):
    sun = nxt - timedelta(days=1)
    L = ["---", "type: usage-report", f"week: {label}", f"from: {mon}", f"to: {sun}", "---",
         f"# Usage {label} ({mon} to {sun})", ""]
    if not agg["total"]["req"]:
        return "\n".join(L + ["No usage this week.", ""])
    return "\n".join(L + [render_text(agg), ""])


def common(ap):
    ap.add_argument("--repo", default=".", help="repo root holding kaizen.config.json")
    ap.add_argument("--source", help="comma list: claude,codex (default: from config)")
    ap.add_argument("--prices", help="prices JSON (default: from config, then the bundled file)")
    ap.add_argument("--claude-root")
    ap.add_argument("--codex-root")


def setup(a):
    cfg = read_config(a.repo)
    names = a.source.split(",") if a.source else cfg["sources"]
    bad = [n for n in names if n not in SOURCES]
    if bad:
        sys.exit(f"unknown source: {', '.join(bad)} (claude|codex)")
    prices = a.prices or cfg["prices"]
    if prices and not os.path.isabs(prices):
        prices = Path(a.repo) / prices
    return cfg, names, Pricing.load(prices), {"claude": a.claude_root, "codex": a.codex_root}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("usage")
    common(u)
    u.add_argument("--days", type=int)
    u.add_argument("--since")
    u.add_argument("--top", type=int, default=5)
    r = sub.add_parser("report")
    common(r)
    r.add_argument("--week", help="YYYY-WNN (default: last closed ISO week)")
    r.add_argument("--out", help="reports directory (default: reportsDir in config)")
    r.add_argument("--print", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cfg, names, pricing, roots = setup(a)

    if a.cmd == "usage":
        since = None
        if a.since:
            since = datetime.fromisoformat(a.since).astimezone()
        elif a.days:
            since = datetime.now().astimezone() - timedelta(days=a.days)
        recs = load_records(names, since, roots)
        print(render_text(aggregate(recs, pricing), a.top) if recs else "No data.")
        return 0

    mon, nxt = week_bounds(a.week)
    label = f"{mon.isocalendar()[0]}-W{mon.isocalendar()[1]:02d}"
    lo = datetime(mon.year, mon.month, mon.day).astimezone()
    hi = datetime(nxt.year, nxt.month, nxt.day).astimezone()
    recs = [x for x in load_records(names, lo, roots) if x["ts"] < hi]
    text = render_report(label, mon, nxt, aggregate(recs, pricing))
    if a.print:
        print(text)
        return 0
    out = Path(a.repo) / (a.out or cfg["reportsDir"]) / f"{label}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
