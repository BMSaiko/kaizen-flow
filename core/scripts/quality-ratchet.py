#!/usr/bin/env python3
"""Ratchet de qualidade: complexidade (ruff C901/PLR) e tipos (mypy) só podem descer.

Uso: quality-ratchet.py [--repo R] [--baseline F] [--so ruff|mypy] [--atualizar] [--diff BASE]
Compara as violações atuais com `quality-baseline.json` ({ficheiro: {regra: n}}): dívida antiga passa,
dívida nova (ficheiro/regra a subir) falha. `--atualizar` grava a baseline quando só desceu (nunca a sobe).
`--diff BASE`: ficheiros .py de core/scripts adicionados ou alterados face a BASE (git) que não constam de
`core/scripts/strict_modules.txt` falham (módulo tocado ou novo tem de ser strict); linhas `~ficheiro` são dívida tolerada; `--strict-lista` corre `mypy --strict` sobre a lista.
Regras ruff medidas: C901 (limite em ruff.toml), PLR0911/0912/0913/0915. Sem rede; ruff e mypy são ferramentas de dev.
rc: 0 sem regressão, 1 regressão, 2 ferramenta em falta ou saída ilegível
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REGRAS = "C901,PLR0911,PLR0912,PLR0913,PLR0915"
ERRO_MYPY = re.compile(r"^(?P<f>[^:\n]+):\d+(?::\d+)?: error: ")
Contagens = dict[str, dict[str, int]]


def _norm(p: str) -> str:
    return p.replace("\\", "/")


def contar_ruff(saida: str, repo: str) -> Contagens:
    out: Contagens = {}
    for d in json.loads(saida or "[]"):
        f = _norm(os.path.relpath(d["filename"], repo))
        out.setdefault(f, {}).setdefault(d["code"], 0)
        out[f][d["code"]] += 1
    return out


def contar_mypy(saida: str) -> Contagens:
    out: Contagens = {}
    for linha in saida.splitlines():
        m = ERRO_MYPY.match(linha)
        if m:
            f = _norm(m["f"])
            out.setdefault(f, {"mypy": 0})["mypy"] += 1
    return out


def comparar(atual: Contagens, base: Contagens) -> tuple[list[str], list[str]]:
    """(subidas, descidas) por ficheiro e regra."""
    pior: list[str] = []
    melhor: list[str] = []
    for f in sorted(set(atual) | set(base)):
        for regra in sorted(set(atual.get(f, {})) | set(base.get(f, {}))):
            a, b = atual.get(f, {}).get(regra, 0), base.get(f, {}).get(regra, 0)
            if a > b:
                pior.append(f"{f} {regra}: {b} -> {a}")
            elif a < b:
                melhor.append(f"{f} {regra}: {b} -> {a}")
    return pior, melhor


def _correr(cmd: list[str], repo: str) -> str:
    try:
        return subprocess.run(cmd, cwd=repo, capture_output=True, text=True, check=False).stdout
    except OSError as e:
        raise RuntimeError(f"{cmd[0]}: {e}") from e


def medir(repo: str, ferramentas: tuple[str, ...]) -> Contagens:
    total: Contagens = {}
    py = sys.executable
    saidas = []
    if "ruff" in ferramentas:
        saidas.append(contar_ruff(_correr([py, "-m", "ruff", "check", "--select", REGRAS, "--output-format", "json", "--no-cache", "."], repo), repo))
    if "mypy" in ferramentas:
        saidas.append(contar_mypy(_correr([py, "-m", "mypy", "--no-color-output", "--no-error-summary"], repo)))
    for s in saidas:
        for f, regras in s.items():
            total.setdefault(f, {}).update(regras)
    return total


STRICT_LISTA = "core/scripts/strict_modules.txt"


def ler_strict(repo: str) -> set[str]:
    f = Path(repo) / STRICT_LISTA
    if not f.is_file():
        return set()
    return {_norm(l.strip()) for l in f.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith(("#", "~"))}


def ler_toleradas(repo: str) -> set[str]:
    """Linhas `~ficheiro` de strict_modules.txt: dívida declarada, tocar não falha (não contam como strict)."""
    f = Path(repo) / STRICT_LISTA
    if not f.is_file():
        return set()
    return {_norm(l[1:].strip()) for l in f.read_text(encoding="utf-8").splitlines() if l.startswith("~")}


def tocados(repo: str, base: str) -> list[str]:
    """.py de core/scripts (sem testes) adicionados ou alterados face a `base`."""
    saida = _correr(["git", "diff", "--name-only", "--diff-filter=AMR", f"{base}...HEAD", "--", "core/scripts"], repo)
    return [f for f in map(_norm, saida.splitlines()) if f.endswith(".py") and not Path(f).name.startswith("test_")]


def nao_strict(repo: str, base: str) -> list[str]:
    ok = ler_strict(repo) | ler_toleradas(repo)
    return [f for f in tocados(repo, base) if f not in ok]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--baseline", default=None)
    ap.add_argument("--so", choices=("ruff", "mypy"), default=None)
    ap.add_argument("--atualizar", action="store_true")
    ap.add_argument("--diff", metavar="BASE", default=None, help="falha se um .py tocado face a BASE não está em strict_modules.txt")
    ap.add_argument("--strict-lista", action="store_true", help="mypy --strict sobre strict_modules.txt")
    args = ap.parse_args(argv)
    if args.diff or args.strict_lista:
        return _verificar_strict(args)
    bl = Path(args.baseline) if args.baseline else Path(args.repo) / "quality-baseline.json"
    ferramentas: tuple[str, ...] = (args.so,) if args.so else ("ruff", "mypy")
    try:
        inicial = not bl.exists()
        base: Contagens = {} if inicial else json.loads(bl.read_text(encoding="utf-8"))
        atual = medir(args.repo, ferramentas)
    except (RuntimeError, ValueError, KeyError) as e:
        print(f"quality-ratchet: {e}", file=sys.stderr)
        return 2
    if args.so:  # só compara a parte medida
        regras = {"ruff": set(REGRAS.split(",")), "mypy": {"mypy"}}[args.so]
        base = {f: {r: n for r, n in rs.items() if r in regras} for f, rs in base.items()}
    pior, melhor = comparar(atual, atual if inicial and args.atualizar else base)
    for linha in pior:
        print(f"SOBE  {linha}")
    for linha in melhor:
        print(f"DESCE {linha}")
    if pior:
        print(f"quality-ratchet: {len(pior)} regressão(ões); corrigir (não subir a baseline)", file=sys.stderr)
        return 1
    if args.atualizar and not args.so:
        bl.write_text(json.dumps(atual, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"baseline atualizada: {bl}")
    elif melhor:
        print("dívida desceu: correr com --atualizar para fixar a baseline")
    return 0


def _verificar_strict(args: argparse.Namespace) -> int:
    rc = 0
    if args.diff:
        try:
            falta = nao_strict(args.repo, args.diff)
        except RuntimeError as e:
            print(f"quality-ratchet: {e}", file=sys.stderr)
            return 2
        for f in falta:
            print(f"NAO-STRICT {f}: tocado ou novo; tipar e acrescentar a {STRICT_LISTA}")
        rc = 1 if falta else 0
    if args.strict_lista:
        lista = sorted(ler_strict(args.repo))
        saida = _correr([sys.executable, "-m", "mypy", "--strict", "--no-color-output", "--no-error-summary", *lista], args.repo) if lista else ""
        erros = [l for l in saida.splitlines() if ERRO_MYPY.match(l)]
        print("\n".join(erros))
        rc = 1 if erros else rc
    return rc


if __name__ == "__main__":
    sys.exit(main())
