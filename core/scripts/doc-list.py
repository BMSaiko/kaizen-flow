#!/usr/bin/env python3
"""OBSOLETO: alias fino de `sp-list.py --tipo dr|dp` (mantido para quem usa o nome antigo).

Uso:
  python -I scripts/doc-list.py <dr|dp> [--all]   # = sp-list.py --tipo <dr|dp> [--all]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import doc_ops  # noqa: E402

collect, default_root, DEFAULT_ROOT, ORDER = doc_ops.collect, doc_ops.default_root, doc_ops.DEFAULT_ROOT, doc_ops.ORDER


def main(argv=None):
    ap = argparse.ArgumentParser(description="OBSOLETO: usa sp-list.py --tipo dr|dp")
    ap.add_argument("kind", choices=doc_ops.TYPES)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    return doc_ops.listar(args.root, args.kind, args.all)


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
