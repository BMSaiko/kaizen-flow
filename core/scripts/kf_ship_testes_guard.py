#!/usr/bin/env python3
"""Guarda «testes como contrato» do kf-ship: os testes existentes não podem ser apagados nem enfraquecidos.

Uso: python -I scripts/kf_ship_testes_guard.py <base>..<head> [--repo CAMINHO]
Compara os ficheiros de teste entre o merge-base de <base> e <head> e o <head> (como um PR): teste apagado ou com menos asserts = violação.
Testes novos e asserts novos são livres. Só leitura (git show/ls-tree/diff).
rc: 0 ok, 1 violação (uma linha por ficheiro), 3 sem testes no <head>, 4 git falhou, 64 uso
"""
import argparse
import re
from pathlib import Path as _P
import sys as _s
_s.path.insert(0, str(_P(__file__).resolve().parent))
from painel_backend import run_hidden  # noqa: E402

PADRAO_TESTE = re.compile(
    r"(^|/)(tests?|__tests__)/|(^|/)test_[^/]+\.py$|_test\.(py|go)$|\.(test|spec)\.[cm]?[jt]sx?$")
PADRAO_ASSERT = re.compile(r"\bassert\w*\b|\bexpect\s*\(|\bassert\.\w+\s*\(")


def is_teste(path):
    """True se `path` é um ficheiro de teste (convenções pytest, jest/vitest, go)."""
    return bool(PADRAO_TESTE.search(path))


def contar_asserts(texto):
    """Conta linhas com pelo menos um assert/expect."""
    return sum(1 for linha in texto.splitlines() if PADRAO_ASSERT.search(linha))


def verificar(antes, depois):
    """`antes`/`depois`: {caminho: texto} dos testes. Devolve a lista de violações (vazia = ok)."""
    out = []
    for path in sorted(p for p in antes if is_teste(p)):
        if path not in depois:
            out.append(f"{path}: teste apagado")
            continue
        a, d = contar_asserts(antes[path]), contar_asserts(depois[path])
        if d < a:
            out.append(f"{path}: asserts {a} → {d}")
    return out


class GitErro(Exception):
    pass


def _git(repo, *args):
    r = run_hidden(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise GitErro(r.stderr.strip() or "git falhou")
    return r.stdout


def _testes(repo, ref):
    nomes = _git(repo, "ls-tree", "-r", "--name-only", ref).splitlines()
    return [n for n in nomes if is_teste(n)]


def _conteudos(repo, ref, paths):
    return {p: _git(repo, "show", f"{ref}:{p}") for p in paths}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("intervalo")
    ap.add_argument("--repo", default=".")
    a = ap.parse_args(argv)
    base, sep, head = a.intervalo.partition("..")
    if not sep or not base or not head or base.startswith("-") or head.startswith("-"):
        print("uso: <base>..<head>")
        return 64
    try:
        base = _git(a.repo, "merge-base", base, head).strip()
        depois_paths = _testes(a.repo, head)
        if not depois_paths:
            print(f"sem testes em {head}: o contrato precisa de testes")
            return 3
        mudados = set(_git(a.repo, "diff", "--name-only", f"{base}..{head}").splitlines())
        antes_paths = [p for p in _testes(a.repo, base) if p in mudados]
        antes = _conteudos(a.repo, base, antes_paths)
        depois = _conteudos(a.repo, head, [p for p in antes_paths if p in depois_paths])
    except GitErro as e:
        print(f"git falhou: {e}")
        return 4
    violacoes = verificar(antes, depois)
    for v in violacoes:
        print(v)
    if violacoes:
        return 1
    print(f"testes-contrato ok ({len(antes_paths)} teste(s) alterado(s), {len(depois_paths)} no total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
