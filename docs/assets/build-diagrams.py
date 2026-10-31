"""Regenera os SVG de docs/assets. Uso: python -I docs/assets/build-diagrams.py docs/assets"""
import sys
out = sys.argv[1] if len(sys.argv) > 1 else "."
C = dict(blue="#38bdf8", violet="#a78bfa", amber="#fbbf24", green="#34d399", red="#f87171", grey="#94a3b8")


def head(w, h, title, desc, t, sub):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-labelledby="t d">\n'
            f'  <title id="t">{title}</title>\n  <desc id="d">{desc}</desc>\n  <rect width="{w}" height="{h}" rx="24" fill="#0f172a"/>\n'
            '  <g font-family="Segoe UI, Helvetica, Arial, sans-serif">\n'
            f'<text x="{w/2}" y="62" text-anchor="middle" font-size="40" font-weight="700" fill="#f8fafc">{t}</text>\n'
            f'<text x="{w/2}" y="96" text-anchor="middle" font-size="20" fill="#cbd5e1">{sub}</text>\n')


def box(x, y, w, h, col, t, s, dash=False):
    d = ' stroke-dasharray="8 6"' if dash else ''
    cx = x + w / 2
    r = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="#1e293b" stroke="{C[col]}" stroke-width="2"{d}/>'
    ty = y + h / 2 - 2 if s else y + h / 2 + 8
    r += f'<text x="{cx}" y="{ty}" text-anchor="middle" font-size="22" font-weight="600" fill="{C[col]}">{t}</text>'
    if s:
        r += f'<text x="{cx}" y="{y + h / 2 + 22}" text-anchor="middle" font-size="15" fill="#cbd5e1">{s}</text>'
    return r + '\n'


def panel(x, y, w, h, col, t, lines, dash=False):
    d = ' stroke-dasharray="8 6"' if dash else ''
    r = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="#1e293b" stroke="{C[col]}" stroke-width="2"{d}/>'
    r += f'<text x="{x + w / 2}" y="{y + 34}" text-anchor="middle" font-size="22" font-weight="700" fill="{C[col]}">{t}</text>'

    for i, l in enumerate(lines):
        r += txt(x + w / 2, y + 62 + i * 24, l, 16)
    return r


def arrow(x1, y, x2):
    return f'<path d="M{x1} {y}H{x2 - 8}" stroke="#94a3b8" stroke-width="3" stroke-linecap="round"/><path d="M{x2} {y}l-10-6v12z" fill="#94a3b8"/>\n'


def varrow(x, y1, y2):
    return f'<path d="M{x} {y1}V{y2 - 8}" stroke="#94a3b8" stroke-width="3" stroke-linecap="round"/><path d="M{x} {y2}l-6-10h12z" fill="#94a3b8"/>\n'


def elbow(x1, y1, ymid, x2, y2):
    return (f'<path d="M{x1} {y1}V{ymid}H{x2}V{y2 - 8}" stroke="#94a3b8" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="M{x2} {y2}l-6-10h12z" fill="#94a3b8"/>\n')


def txt(x, y, s, size=16, fill="#cbd5e1", anchor="middle", w=None):
    wt = f' font-weight="{w}"' if w else ''
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}"{wt} fill="{fill}">{s}</text>\n'


foot = '  </g>\n</svg>\n'
xs = [85, 355, 625, 895]
W = 220
H = 86
aw = 290
ax = [85, 455, 825]


def save(name, s):
    open(f"{out}/{name}", "w", encoding="utf-8", newline="\n").write(s + foot)


# ---------- michi-cycle
s = head(1200, 710, "michi cycle",
         "michi cycle: dr, grill, dp, da, gates, pentest, review-ciclo, pr-fase, report, reflect and commit proposal, with proof per phase, handoff per phase and a kaizen loop.",
         "michi", "The cycle that executes an SP")
rows = [(130, [("1 · dr", "blue", "research"), ("2 · grill", "blue", "align"), ("3 · dp", "violet", "TDD-shaped plan"), ("4 · da", "violet", "act, proof per phase")]),
        (290, [("5 · gates", "amber", "build, tests, lint"), ("6 · pentest", "amber", "diff-local, findings → SPs"), ("7 · review-ciclo", "amber", "fix and review, capped"), ("8 · pr-fase", "amber", "PR from SP + proofs")]),
        (450, [("9 · report", "green", "what, verified, open"), ("10 · reflect", "green", "patch the workflow"), ("11 · commit", "green", "proposal, never auto"), ("↻ kaizen", "grey", "next cycle is cheaper")])]
for y, items in rows:
    for i, (t, c, sub) in enumerate(items):
        s += box(xs[i], y, W, H, c, t, sub, dash=(t == "↻ kaizen"))
        if i < len(items) - 1:
            s += arrow(xs[i] + W + 2, y + H // 2, xs[i + 1] - 2)
s += elbow(1005, 130 + H + 2, 252, 195, 290) + txt(600, 246, "phase done → proof + reflect", 14, "#94a3b8")
s += elbow(1005, 290 + H + 2, 412, 195, 450) + txt(600, 406, "checks green → report", 14, "#94a3b8")
s += panel(85, 570, 1030, 100, "grey", "Between phases", ["context guard at 100K → handoff (progress saved in the SP, fresh session) · sp-fechar = gates + done + COMMIT file", "hooks fire on every phase start/end, failed gate, commit and close"], dash=True)
save("michi-cycle.svg", s)

# ---------- sp-workflow
s = head(1200, 720, "SP workflow",
         "Super Prompt workflow: brainstorm, swot, grill-me and dr feed an 8-section SP that moves TODO, Doing, Done, closes with sp-fechar, and can be run by sp-fila sequentially or in parallel.",
         "SP workflow", "From an idea to a Super Prompt, then through its lifecycle")
s += txt(85, 138, "1. BUILD  (/sp, outside michi)", 16, "#94a3b8", "start", 600)
for i, (t, sub) in enumerate([("brainstorm", "ideas"), ("swot", "stress-test"), ("grill-me", "align what, why, how"), ("dr", "real code paths")]):
    s += box(xs[i], 150, W, 80, "blue", t, sub)
    if i < 3:
        s += arrow(xs[i] + W + 2, 190, xs[i + 1] - 2)
s += elbow(1005, 232, 262, 600, 290)
s += box(200, 290, 800, 90, "violet", "Super Prompt: 8 fixed sections", "role · context · objective · success criteria · constraints · seams · steps · done-when")
s += txt(85, 420, "2. LIFECYCLE  (sp-new, sp-move, sp-fechar, sp-list)", 16, "#94a3b8", "start", 600)
for i, (t, c, sub) in enumerate([("TODO", "grey", "sp-new"), ("Doing", "violet", "/michi SP"), ("Done", "green", "sp-fechar")]):
    s += box(xs[i], 432, W, 80, c, t, sub)
    if i < 2:
        s += arrow(xs[i] + W + 2, 472, xs[i + 1] - 2)
s += txt(870, 462, "gates + done + COMMIT file in one step", 15, "#cbd5e1", "start")
s += txt(870, 486, "handoff appends ## Progresso, fresh context", 15, "#cbd5e1", "start")
s += txt(85, 552, "3. RUN MANY  (/sp-fila)", 16, "#94a3b8", "start", 600)
s += box(85, 564, 500, 110, "amber", "sequential", "one clean session per eligible SP, stops on first failure")
s += box(615, 564, 500, 110, "amber", "parallel  --concorrencia N", "N panes, one worktree each, watcher, nothing pushed")
save("sp-workflow.svg", s)

# ---------- architecture
s = head(1200, 640, "Architecture",
         "kaizen-flow architecture: the core (skills, commands, scripts) is rendered by the claude, codex and agents-md adapters into the target project.",
         "Architecture", "One core, rendered per harness into your project")
s += panel(200, 130, 800, 110, "violet", "core", ["skills (michi, dp, da, dr, pentest, pr-fase…) · commands (/sp, /sp-fila, /handoff…)", "scripts (sp-*.py, context-guard, kaizen_hooks, pentest, review_ciclo)"])
for x, (t, sub) in zip(ax, [("adapter claude", ".claude/skills, commands + hooks"), ("adapter codex", "Codex CLI layout"), ("adapter agents-md", "AGENTS.md for any harness")]):
    s += box(x, 320, aw, 90, "blue", t, sub)
    s += varrow(600, 242, 320) if x == 455 else elbow(600, 242, 282, x + aw // 2, 320)
s += panel(85, 500, 1030, 100, "green", "your project", ["SPs (TODO/Doing/Done) · scripts/ · kaizen-hooks.json · config; no telemetry, stdlib only"])
for x in ax:
    s += varrow(x + aw // 2, 412, 500)
save("architecture.svg", s)

# ---------- sp-fila parallel
s = head(1200, 680, "sp-fila parallel",
         "sp-fila parallel mode: the orchestrator opens up to N panes, each running one SP in its own worktree, while a watcher reports state changes and brings blocked panes to the user.",
         "sp-fila --concorrencia N", "Up to N stories at once, each isolated")
s += box(400, 120, 400, 84, "amber", "sp-fila.py", "picks eligible SPs (auto, gates, deps met)")
for i, x in enumerate(ax):
    s += box(x, 290, aw, 90, "violet", f"pane {i + 1} · /michi SP-{i + 1}", "own session")
    s += varrow(600, 206, 290) if i == 1 else elbow(600, 206, 248, x + aw // 2, 290)
    s += box(x, 430, aw, 70, "grey", f"worktree {i + 1}", "own branch, no clashes")
    s += varrow(x + aw // 2, 382, 430)
s += box(85, 560, 640, 84, "blue", "watcher  --vigiar --destacado", "reports each state change: running, closed, blocked, dead")
s += box(755, 560, 360, 84, "red", "blocked pane", "brought to you, never auto-approved")
s += arrow(727, 602, 753)
s += txt(600, 534, "each branch merges via its own PR; the queue pushes nothing", 15, "#94a3b8")
save("sp-fila-parallel.svg", s)
