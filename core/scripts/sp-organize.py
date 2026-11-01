#!/usr/bin/env python3
"""Deteta e corrige Super Prompts fora do padrão. Dry-run por defeito.

Padrão: `<projeto>/sp/{TODO,Doing,Done}/<slug>-<YYYY-MM-DD>.md`, com `status:` = pasta e
`project:` = pasta do projeto. Só move/renomeia/corrige frontmatter; nunca apaga nem faz commit.
Ignora `arquivo/`, `_sessions/`, `MOC.md` e anexos `-DP`/`-REPORT`. Colisões ficam por resolver.

Uso:
  python -I scripts/sp-organize.py [--project P] [--apply]
rc=0 se nada a fazer (ou tudo aplicado); rc=1 se há desvios por aplicar ou bloqueados.
"""
import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402

sp_list = kaizen_engine.load("sp-list")

SKIP_DIRS = {"arquivo", "_sessions"}
ATTACHMENT_RE = re.compile(r"-(DP|REPORT)$")


@dataclass
class Action:
    source: Path
    target: Path
    fixes: dict
    reason: str
    blocked: str = ""


def set_field(text, key, value):
    return re.sub(rf"^{key}:.*$", f"{key}: {value}", text, count=1, flags=re.M)


def plan(root, project=None):
    root = Path(root)
    actions = []
    for path in sorted(root.rglob("*.md")):
        parts = path.relative_to(root).parts
        if (SKIP_DIRS & set(parts) or path.name == "MOC.md" or ATTACHMENT_RE.search(path.stem)
                or "sp" not in parts[:-1]):
            continue
        idx = parts.index("sp")
        try:
            fm = sp_list.parse_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        if fm.get("phase") != "SP":
            continue
        folder_proj = parts[idx - 1] if idx >= 1 else None
        proj = folder_proj or fm.get("project", "")
        rest = parts[idx + 1:-1]
        folder = rest[0] if len(rest) == 1 and rest[0] in sp_list.FOLDERS else None
        if project and proj != project:
            continue
        status = folder or fm.get("status", "")
        if status not in sp_list.FOLDERS:
            actions.append(Action(path, path, {}, "pasta/estado desconhecido", "manual"))
            continue
        if not proj or not (root / proj).is_dir():
            actions.append(Action(path, path, {}, "projeto inexistente", "manual"))
            continue
        reasons, fixes = [], {}
        if not folder:
            reasons.append("fora de sp/{TODO,Doing,Done}")
        if not folder_proj:
            reasons.append("SP sem projeto na raiz")
        if fm.get("status") and fm["status"] != status:
            fixes["status"] = status
            reasons.append(f"status {fm['status']}≠{status}")
        if fm.get("project") and fm["project"] != proj:
            fixes["project"] = proj
            reasons.append(f"project {fm['project']}≠{proj}")
        name = path.name
        if fm.get("slug") and fm.get("date"):
            expected = f"{fm['slug']}-{fm['date']}.md"
            if name != expected:
                name = expected
                reasons.append("nome fora do padrão")
        if not reasons:
            continue
        target = root / proj / "sp" / status / name
        blocked = "destino já existe" if target != path and target.exists() else ""
        actions.append(Action(path, target, fixes, "; ".join(reasons), blocked))
    return actions


def apply(action):
    if action.blocked:
        return
    text = action.source.read_text(encoding="utf-8")
    for key, value in action.fixes.items():
        text = set_field(text, key, value)
    action.target.parent.mkdir(parents=True, exist_ok=True)
    if action.target == action.source:
        action.source.write_text(text, encoding="utf-8")
        return
    action.target.write_text(text, encoding="utf-8")
    action.source.unlink()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deteta/corrige SPs fora do padrão (dry-run por defeito)")
    ap.add_argument("--project")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--root", default=str(sp_list.DEFAULT_ROOT), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    root = Path(args.root)
    actions = plan(root, args.project)
    if not actions:
        print("nada a fazer")
        return 0
    pending = 0
    for a in actions:
        src = a.source.relative_to(root)
        dst = a.target.relative_to(root)
        if a.blocked:
            print(f"BLOQUEADO ({a.blocked}) {src} :: {a.reason}")
            pending += 1
        elif args.apply:
            apply(a)
            print(f"aplicado {src} -> {dst} :: {a.reason}")
        else:
            print(f"{src} -> {dst} :: {a.reason}")
            pending += 1
    return 1 if pending else 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
