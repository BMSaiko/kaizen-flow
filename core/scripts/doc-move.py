#!/usr/bin/env python3
"""Move um DR ou DP entre <tipo>/TODO, Doing e Done e atualiza `status`/`updated`.

Aceita frontmatter sem `updated` (acrescenta) ou sem frontmatter (cria). Nunca faz commit.
Usa `git mv` se o ficheiro estiver tracked, senão renomeia.

Uso:
  python -I scripts/doc-move.py <dr|dp> <slug> <todo|doing|done>
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402

_kc = kaizen_engine.load("kaizen_config")
REPO = Path(__file__).resolve().parent.parent


def default_root(repo=REPO):
    return _kc.docs_root(repo)


DEFAULT_ROOT = default_root()
DESTS = {"todo": "TODO", "doing": "Doing", "done": "Done"}
TYPES = ("dr", "dp")


class DocMoveError(Exception):
    pass


def find(root, kind, slug):
    found = []
    for path in Path(root).rglob(f"{slug}.md"):
        parts = path.relative_to(root).parts
        if len(parts) >= 3 and parts[-3] == kind and parts[-2] in DESTS.values() and "arquivo" not in parts:
            found.append(path)
    return found


def rewrite(raw, status, updated):
    text = raw.decode("utf-8")
    lines = text.splitlines(keepends=True)
    eol = "\r\n" if lines and lines[0].endswith("\r\n") else "\n"
    if not lines or lines[0].strip() != "---":
        return (f"---{eol}status: {status}{eol}updated: {updated}{eol}---{eol}" + text).encode("utf-8")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise DocMoveError("frontmatter sem fecho")
    seen = set()
    for i in range(1, end):
        key = lines[i].partition(":")[0].strip()
        if key in ("status", "updated"):
            lines[i] = f"{key}: {status if key == 'status' else updated}{eol}"
            seen.add(key)
    extra = [f"{k}: {v}{eol}" for k, v in (("status", status), ("updated", updated)) if k not in seen]
    lines[end:end] = extra
    return "".join(lines).encode("utf-8")


def move(root, kind, slug, dest):
    if kind not in TYPES:
        raise DocMoveError(f"tipo inválido '{kind}' (dr|dp)")
    if dest.lower() not in DESTS:
        raise DocMoveError(f"destino inválido '{dest}' (todo|doing|done)")
    target = DESTS[dest.lower()]
    matches = find(root, kind, slug)
    if not matches:
        raise DocMoveError(f"{kind.upper()} '{slug}' não encontrado")
    if len(matches) > 1:
        raise DocMoveError(f"{kind.upper()} '{slug}' ambíguo: " + ", ".join(str(m) for m in matches))
    src = matches[0]
    if src.parent.name == target:
        return f"{slug}: já está em {target} ({src})"
    dst = src.parent.parent / target / src.name
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_raw = rewrite(src.read_bytes(), target, updated)
    kaizen_engine.relocate(src, dst)
    dst.write_bytes(new_raw)
    return f"{slug}: {src.parent.name} → {target} ({dst})"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Move um DR/DP entre TODO, Doing e Done")
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
