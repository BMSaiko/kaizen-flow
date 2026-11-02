#!/usr/bin/env python3
"""Sobe a prioridade dos SPs (TODO/Doing) parados há muito tempo. Só sobe, nunca desce.

Idade = dias desde `updated` (fallback `created`). P3->P2 aos 14 dias, P2->P1 aos 28.
`priority_base` (guardado no frontmatter à primeira subida) torna a operação idempotente.

Uso:
  python -I scripts/sp-envelhecer.py              # dry-run (lista as subidas)
  python -I scripts/sp-envelhecer.py --apply      # escreve
  python -I scripts/sp-envelhecer.py --hook       # SessionStart: --apply, no máximo 1x/dia (selo)
"""
import argparse
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_list_mod  # noqa: E402  (carrega sp-list.py)

REPO = Path(__file__).resolve().parent.parent
STEP_DAYS = 14
ORDER = ["P3", "P2", "P1"]


def target(base, age):
    steps = max(age, 0) // STEP_DAYS
    return ORDER[min(ORDER.index(base) + steps, 2)]


def age_days(path, sp, today):
    raw = path.read_text(encoding="utf-8")
    m = re.search(r"^updated:\s*(.+)$", raw, re.M)
    d = sp_list_mod.parse_date(m.group(1)) if m else None
    d = d or sp.created
    return (today - d).days if d else 0, raw


def plan(root, today):
    out = []
    for sp in sp_list_mod.collect(root):
        age, raw = age_days(sp.path, sp, today)
        m = re.search(r"^priority_base:\s*(P[123])\s*$", raw, re.M)
        base = m.group(1) if m else sp.priority
        new = target(base, age)
        if ORDER.index(new) > ORDER.index(sp.priority):
            out.append((sp, sp.priority, new, base, age))
    return out


def apply(sp, new, base):
    raw = sp.path.read_bytes().decode("utf-8")
    raw = re.sub(r"^priority:.*$", f"priority: {new}", raw, count=1, flags=re.M)
    if not re.search(r"^priority_base:", raw, re.M):
        raw = re.sub(r"^(priority: .*)$", rf"\1\npriority_base: {base}", raw, count=1, flags=re.M)
    sp.path.write_bytes(raw.encode("utf-8"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--hook", action="store_true")
    ap.add_argument("--root", default=str(sp_list_mod.DEFAULT_ROOT))
    ap.add_argument("--stamp", default=str(REPO / ".sp-envelhecer.stamp"))
    args = ap.parse_args(argv)
    today = date.today()
    stamp = Path(args.stamp)
    if args.hook:
        if stamp.exists() and stamp.read_text().strip() == str(today):
            return 0
        args.apply = True
    rows = plan(args.root, today)
    for sp, old, new, base, age in rows:
        print(f"{sp.slug}: {old} -> {new} ({age}d parado)")
        if args.apply:
            apply(sp, new, base)
    if not rows:
        print("nada a subir")
    if args.hook:
        stamp.write_text(str(today))
    return 0


if __name__ == "__main__":
    sys.exit(main())
