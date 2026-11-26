#!/usr/bin/env python3
"""Ratchet de qualidade: complexidade (ruff C901/PLR) e tipos (mypy) só podem descer.

Uso: quality-ratchet.py [--repo R] [--baseline F] [--so ruff|mypy|eslint|tsc] [--atualizar]
Compara as violações atuais com `quality-baseline.json` ({ficheiro: {regra: n}}): dívida antiga passa,
dívida nova (ficheiro/regra a subir) falha. `--atualizar` grava a baseline quando só desceu (nunca a sobe).
JS: eslint (por regra, `eslint.config.js`) e `tsc --checkJs` (contagem "tsc"), via npx; em falta = rc 2.
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
ERRO_TSC = re.compile(r"^(?P<f>[^(\n]+)\(\d+,\d+\): error TS\d+")
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


def contar_eslint(saida: str, repo: str) -> Contagens:
    out: Contagens = {}
    for d in json.loads(saida or "[]"):
        f = _norm(os.path.relpath(d["filePath"], repo))
        for m in d.get("messages", []):
            regra = m.get("ruleId") or "eslint-parse"
            out.setdefault(f, {}).setdefault(regra, 0)
            out[f][regra] += 1
    return out


def contar_tsc(saida: str) -> Contagens:
    out: Contagens = {}
    for linha in saida.splitlines():
        m = ERRO_TSC.match(linha)
        if m:
            out.setdefault(_norm(m["f"]), {"tsc": 0})["tsc"] += 1
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


def _tool(regra: str) -> str:
    if regra in ("mypy", "tsc"):
        return regra
    return "ruff" if regra in REGRAS.split(",") else "eslint"


def _ferramentas(so: str | None, repo: str) -> tuple[str, ...]:
    if so:
        return (so,)
    js = ("eslint", "tsc") if (Path(repo) / "node_modules").is_dir() else ()
    return ("ruff", "mypy", *js)


def medir(repo: str, ferramentas: tuple[str, ...]) -> Contagens:
    total: Contagens = {}
    py = sys.executable
    saidas = []
    if "ruff" in ferramentas:
        saidas.append(contar_ruff(_correr([py, "-m", "ruff", "check", "--select", REGRAS, "--output-format", "json", "--no-cache", "."], repo), repo))
    if "mypy" in ferramentas:
        saidas.append(contar_mypy(_correr([py, "-m", "mypy", "--no-color-output", "--no-error-summary"], repo)))
    npx = "npx.cmd" if os.name == "nt" else "npx"
    if "eslint" in ferramentas:
        saidas.append(contar_eslint(_correr([npx, "--no-install", "eslint", ".", "-f", "json"], repo), repo))
    if "tsc" in ferramentas:
        saidas.append(contar_tsc(_correr([npx, "--no-install", "tsc", "-p", ".", "--pretty", "false"], repo)))
    for s in saidas:
        for f, regras in s.items():
            total.setdefault(f, {}).update(regras)
    return total


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--baseline", default=None)
    ap.add_argument("--so", choices=("ruff", "mypy", "eslint", "tsc"), default=None)
    ap.add_argument("--atualizar", action="store_true")
    args = ap.parse_args(argv)
    bl = Path(args.baseline) if args.baseline else Path(args.repo) / "quality-baseline.json"
    ferramentas = _ferramentas(args.so, args.repo)
    try:
        inicial = not bl.exists()
        base: Contagens = {} if inicial else json.loads(bl.read_text(encoding="utf-8"))
        atual = medir(args.repo, ferramentas)
    except (RuntimeError, ValueError, KeyError) as e:
        print(f"quality-ratchet: {e}", file=sys.stderr)
        return 2
    medidas = set(ferramentas)  # só compara e grava o que foi medido; o resto da baseline fica intacta
    resto = {f: {r: n for r, n in rs.items() if _tool(r) not in medidas} for f, rs in base.items()}
    base = {f: {r: n for r, n in rs.items() if _tool(r) in medidas} for f, rs in base.items()}
    # ferramenta nova (sem entradas na baseline): `--atualizar` semeia-a; sem ele, tudo conta como dívida nova
    novas = {t for t in medidas & {"eslint", "tsc"} if not any(_tool(r) == t for rs in base.values() for r in rs)}
    if args.atualizar and novas:
        for f, rs in atual.items():
            base.setdefault(f, {}).update({r: n for r, n in rs.items() if _tool(r) in novas})
    pior, melhor = comparar(atual, base)
    for linha in pior:
        print(f"SOBE  {linha}")
    for linha in melhor:
        print(f"DESCE {linha}")
    if pior:
        print(f"quality-ratchet: {len(pior)} regressão(ões); corrigir (não subir a baseline)", file=sys.stderr)
        return 1
    if args.atualizar:
        for f, rs in resto.items():
            if rs:
                atual.setdefault(f, {}).update(rs)
        bl.write_text(json.dumps(atual, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"baseline atualizada: {bl}")
    elif melhor:
        print("dívida desceu: correr com --atualizar para fixar a baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
