#!/usr/bin/env python3
"""Aprova um SP: grava `aprovado: <ISO8601>` e `grill: <n rondas>` no frontmatter (o portão da fila).

Num programa (`--programa`) grava na mãe e em todos os filhos. Idempotente. `--verificar` não escreve:
rc 1 se o SP está por aprovar (usado pelo `/michi` em auto antes de arrancar).

Uso:
  python -I scripts/sp-aprovar.py <slug> [--programa] [--rondas N] [--project P]
  python -I scripts/sp-aprovar.py <slug> --verificar
rc: 0 ok, 1 erro ou por aprovar
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402
import sp_aprovacao  # noqa: E402
import wt_redirect  # noqa: E402

sp_list = kaizen_engine.load("sp-list")


class SpAprovarError(Exception):
    pass


def _achar(root, slug, project=None):
    found = [s for s in sp_list.collect(root, include_done=True) if s.slug == slug and (not project or s.project == project)]
    if not found:
        raise SpAprovarError(f"SP '{slug}' não encontrado; ver scripts/sp-list.py")
    if len(found) > 1:
        raise SpAprovarError(f"SP '{slug}' ambíguo; usar --project")
    return found[0]


def _fm(sp):
    return sp_list.parse_frontmatter(sp.path.read_bytes().decode("utf-8"))


def verificar(root, slug, project=None):
    """(rc, mensagem): rc 1 se o SP está por aprovar."""
    sp = _achar(root, slug, project)
    if sp_aprovacao.por_aprovar(_fm(sp)):
        return 1, (f"{slug}: por aprovar. Correr `python -I scripts/sp-resumo.py {slug}`, mostrar o resumo ao user "
                   f"e, com o «sim», `python -I scripts/sp-aprovar.py {slug} --rondas N`")
    return 0, f"{slug}: aprovado"


def aprovar(root, slug, rondas, programa=False, project=None):
    if rondas < sp_aprovacao.RONDAS_MINIMAS:
        raise SpAprovarError(f"grill-me obrigatório: mínimo {sp_aprovacao.RONDAS_MINIMAS} ronda (--rondas)")
    sp = _achar(root, slug, project)
    alvo = [sp]
    if programa:
        alvo += [s for s in sp_list.collect(root, include_done=True) if s.project == sp.project and s.parent == slug]
    feitos = []
    for s in alvo:
        fm = _fm(s)
        if fm.get("aprovado") and fm.get("grill") == str(rondas):
            continue
        sp_aprovacao.gravar_campos(s.path, {"aprovado": sp_aprovacao.agora(), "grill": rondas})
        feitos.append(s.slug)
    return f"{slug}: aprovado ({len(feitos)} SP gravados, grill {rondas})"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Aprova um SP (portão de criação)")
    ap.add_argument("slug")
    ap.add_argument("--programa", action="store_true", help="grava também em todos os filhos")
    ap.add_argument("--rondas", type=int, default=0, help="rondas de grill-me feitas (mínimo 1)")
    ap.add_argument("--verificar", action="store_true", help="só verifica; rc 1 se por aprovar")
    ap.add_argument("--project")
    ap.add_argument("--root", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    args.root = args.root or str(sp_list.DEFAULT_ROOT)
    args.slug = sp_list.normalize_ref(args.root, args.slug)
    if argv is None and not args.verificar and args.root == str(sp_list.DEFAULT_ROOT):
        rc = wt_redirect.redirect(__file__, args.slug, sys.argv[1:])
        if rc is not None:
            return rc
    try:
        if args.verificar:
            rc, msg = verificar(args.root, args.slug, args.project)
            print(msg, file=sys.stderr if rc else sys.stdout)
            return rc
        print(aprovar(args.root, args.slug, args.rondas, args.programa, args.project))
    except SpAprovarError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import kf_errlog
    sys.exit(kf_errlog.executar("sp-aprovar", main))
