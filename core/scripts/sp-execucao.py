#!/usr/bin/env python3
"""Lê ou grava `execucao:` (sequencial|paralelo) no frontmatter de um SP-mãe (`kind: program`).

Escreve em bytes (mantém CRLF) e, no checkout principal, na worktree do SP (como o sp-move.py).
Idempotente: o mesmo valor não reescreve o ficheiro. Sem valor, imprime o modo atual ou `por escolher`.

Uso:
  python -I scripts/sp-execucao.py <slug-mãe> [sequencial|paralelo] [--project P]
rc: 0 ok, 1 erro (não é mãe, valor inválido, SP em falta)
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402
import wt_redirect  # noqa: E402

sp_list = kaizen_engine.load("sp-list")
MODOS = ("sequencial", "paralelo")


class SpExecucaoError(Exception):
    pass


def _mae(root, slug, project):
    found = [s for s in sp_list.collect(root, include_done=True) if s.slug == slug and (not project or s.project == project)]
    if not found:
        raise SpExecucaoError(f"SP '{slug}' não encontrado; ver scripts/sp-list.py")
    if len(found) > 1:
        raise SpExecucaoError(f"SP '{slug}' ambíguo; usar --project")
    sp = found[0]
    fm = kaizen_engine.parse_frontmatter(sp.path.read_text(encoding="utf-8"))
    if fm.get("kind") != "program":
        raise SpExecucaoError(f"'{slug}' não é um programa (falta kind: program)")
    return sp, fm


def ler(root, slug, project=None):
    _, fm = _mae(root, slug, project)
    return fm.get("execucao") or "por escolher"


def gravar(root, slug, modo, project=None):
    if modo not in MODOS:
        raise SpExecucaoError(f"execucao '{modo}' inválido ({'|'.join(MODOS)})")
    sp, fm = _mae(root, slug, project)
    if fm.get("execucao") == modo:
        return f"{slug}: execucao já é {modo}"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = sp.path.read_bytes().decode("utf-8").splitlines(keepends=True)
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    eol = lines[0][len(lines[0].rstrip("\r\n")):] or "\n"
    done = False
    for i in range(1, end):
        if lines[i].startswith("execucao:"):
            lines[i], done = f"execucao: {modo}{eol}", True
        elif lines[i].startswith("updated:"):
            lines[i] = f"updated: {stamp}{eol}"
    if not done:
        lines.insert(end, f"execucao: {modo}{eol}")
    sp.path.write_bytes("".join(lines).encode("utf-8"))
    return f"{slug}: execucao = {modo}"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lê ou grava execucao: de um SP-mãe")
    ap.add_argument("slug")
    ap.add_argument("modo", nargs="?")
    ap.add_argument("--project")
    ap.add_argument("--root", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    args.root = args.root or str(sp_list.DEFAULT_ROOT)
    args.slug = sp_list.normalize_ref(args.root, args.slug)
    if argv is None and args.modo and args.root == str(sp_list.DEFAULT_ROOT):
        rc = wt_redirect.redirect(__file__, args.slug, sys.argv[1:])
        if rc is not None:
            return rc
    try:
        print(gravar(args.root, args.slug, args.modo, args.project) if args.modo else ler(args.root, args.slug, args.project))
    except SpExecucaoError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import kf_errlog
    sys.exit(kf_errlog.executar("sp-execucao", main))
