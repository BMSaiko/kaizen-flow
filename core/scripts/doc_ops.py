"""Operações sobre DRs/DPs (listar e mover entre TODO/Doing/Done), partilhadas por sp-list e sp-move.

Chamado por `sp-list.py --tipo dr|dp` e `sp-move.py --tipo dr|dp`; `doc-list.py` e `doc-move.py`
são aliases finos obsoletos que reexportam este módulo.

Uso: módulo importado por sp-list.py e sp-move.py (`--tipo dr|dp`); sem execução direta
rc: n/a (listar devolve 0; erros por exceção)
"""
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402

_kc = kaizen_engine.load("kaizen_config")
REPO = Path(__file__).resolve().parent.parent

TYPES = ("dr", "dp")
ORDER = ("Doing", "TODO", "Done")
DESTS = {"todo": "TODO", "doing": "Doing", "done": "Done"}


def default_root(repo=REPO):
    return _kc.docs_root(repo)


DEFAULT_ROOT = default_root()


class DocMoveError(Exception):
    pass


def collect(root, kind, include_done=False):
    folders = ORDER if include_done else ORDER[:2]
    rows = []
    for path in Path(root).rglob("*.md"):
        parts = path.relative_to(root).parts
        if len(parts) < 3 or parts[-3] != kind or parts[-2] not in folders or "arquivo" in parts:
            continue
        rows.append((ORDER.index(parts[-2]), path.stem, parts[-2], path))
    return sorted(rows)


def listar(root, kind, include_done=False):
    """Imprime os DRs/DPs por estado, com idade em dias da última modificação."""
    print("# Estado Slug (idade)")
    for i, (_, slug, status, path) in enumerate(collect(root, kind, include_done), 1):
        days = int((time.time() - path.stat().st_mtime) // 86400)
        print(f"{i} {status} {slug} ({days}d)")
    return 0


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
