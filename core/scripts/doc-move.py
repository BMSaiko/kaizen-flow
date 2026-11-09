#!/usr/bin/env python3
"""OBSOLETO: alias fino de `sp-move.py --tipo dr|dp` (mantido para quem usa o nome antigo).

Uso:
  python -I scripts/doc-move.py <dr|dp> <slug> <todo|doing|done>   # = sp-move.py --tipo <dr|dp> <slug> <dest>
rc: 0 movido, 1 erro
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import doc_ops  # noqa: E402

DocMoveError, find, rewrite, move = doc_ops.DocMoveError, doc_ops.find, doc_ops.rewrite, doc_ops.move
default_root, DEFAULT_ROOT, DESTS, TYPES = doc_ops.default_root, doc_ops.DEFAULT_ROOT, doc_ops.DESTS, doc_ops.TYPES


def main(argv=None):
    ap = argparse.ArgumentParser(description="OBSOLETO: usa sp-move.py --tipo dr|dp")
    ap.add_argument("kind", help="dr | dp")
    ap.add_argument("slug")
    ap.add_argument("dest", help="todo | doing | done")
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    try:
        print(move(args.root, args.kind.lower(), args.slug, args.dest))
    except DocMoveError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
