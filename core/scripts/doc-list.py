#!/usr/bin/env python3
"""Lista DRs ou DPs por estado (pasta TODO/Doing/Done), com idade da última modificação. Só leitura.

Uso:
  python -I scripts/doc-list.py <dr|dp> [--all]   # sem --all, omite Done
"""
import argparse
import sys
import time
from pathlib import Path

import importlib.util as _ilu

_cspec = _ilu.spec_from_file_location("kaizen_config", Path(__file__).with_name("kaizen_config.py"))
_kc = _ilu.module_from_spec(_cspec)
_cspec.loader.exec_module(_kc)
REPO = Path(__file__).resolve().parent.parent


def default_root(repo=REPO):
    return _kc.docs_root(repo)


DEFAULT_ROOT = default_root()
ORDER = ("Doing", "TODO", "Done")


def collect(root, kind, include_done=False):
    folders = ORDER if include_done else ORDER[:2]
    rows = []
    for path in Path(root).rglob("*.md"):
        parts = path.relative_to(root).parts
        if len(parts) < 3 or parts[-3] != kind or parts[-2] not in folders or "arquivo" in parts:
            continue
        rows.append((ORDER.index(parts[-2]), path.stem, parts[-2], path))
    return sorted(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lista DRs/DPs por estado")
    ap.add_argument("kind", choices=("dr", "dp"))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    print("# Estado Slug (idade)")
    for i, (_, slug, status, path) in enumerate(collect(args.root, args.kind, args.all), 1):
        days = int((time.time() - path.stat().st_mtime) // 86400)
        print(f"{i} {status} {slug} ({days}d)")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
