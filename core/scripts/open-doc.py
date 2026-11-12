"""Lista documentos markdown do vault para o seletor do WezTerm (Ctrl+Shift+M).

Uso: python -I scripts/open-doc.py [--limit N]
Saída: uma linha por documento, `rótulo<TAB>caminho absoluto`. SPs em Doing/TODO
primeiro, depois o resto dos .md por data de modificação (mais recente primeiro).
rc: 0 ok
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {".git", "node_modules", ".venv", "__pycache__"}


def walk():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for name in files:
            if name.lower().endswith(".md"):
                path = os.path.join(base, name)
                yield path, os.path.getmtime(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=1500)
    args = ap.parse_args()
    sps, rest = [], []
    for path, mtime in walk():
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        parts = rel.split("/")
        if "sp" in parts and parts[-2] in ("Doing", "TODO"):
            sps.append((parts[-2] != "Doing", -mtime, "SP " + parts[-2] + " · " + parts[-1], path))
        else:
            rest.append((-mtime, rel, path))
    out = [(label, path) for _, _, label, path in sorted(sps)]
    out += [(rel, path) for _, rel, path in sorted(rest)[: args.limit]]
    sys.stdout.reconfigure(encoding="utf-8")
    for label, path in out:
        print(label + "\t" + path)


if __name__ == "__main__":
    main()
