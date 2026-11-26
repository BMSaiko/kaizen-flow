#!/usr/bin/env python3
"""`kaizen quality`: o único gate de qualidade (local e CI); rc≠0 em qualquer falha.

Uso: kf_quality.py [--repo R] [--base REF] [--so ETAPA ...] [--lista]
Etapas, por ordem: lint (ruff), ratchet (ruff C901/PLR + mypy vs baseline), strict (mypy --strict na lista),
strict-diff (módulo tocado tem de ser strict), testes (npm test com cobertura e limiares),
protegidos (testes existentes não apagados nem enfraquecidos), cobertura-diff (linhas do diff).
As etapas com diff precisam de BASE (defeito `origin/<ramo_principal>`; sem ela são saltadas, e com `--base` explícito falham).
Ferramentas em falta (ruff, mypy, node, pytest) falham a etapa: nunca saltam em silêncio.
rc: 0 tudo ok, 1 alguma etapa falhou, 2 uso
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent

ETAPAS_DIFF = ("strict-diff", "protegidos", "cobertura-diff")
ETAPAS = ("lint", "ratchet", "strict", "strict-diff", "testes", "protegidos", "cobertura-diff")


def comando(etapa: str, repo: Path, base: str | None) -> tuple[list[str], dict[str, str]]:
    """Linha de comando (e ambiente extra) de uma etapa."""
    py = sys.executable
    ratchet = [py, str(AQUI / "quality-ratchet.py"), "--repo", str(repo)]
    por_etapa: dict[str, tuple[list[str], dict[str, str]]] = {
        "lint": ([py, "-m", "ruff", "check", "."], {}),
        "ratchet": (ratchet, {}),
        "strict": ([*ratchet, "--strict-lista"], {}),
        "strict-diff": ([*ratchet, "--diff", str(base)], {}),
        "testes": ([shutil.which("node") or "node", str(repo / "bin" / "run-tests.js")], {"KAIZEN_COVERAGE": "1"}),
        "protegidos": ([py, str(AQUI / "kf_ship_testes_guard.py"), f"{base}..HEAD", "--repo", str(repo)], {}),
        "cobertura-diff": ([py, str(AQUI / "sp-cobertura-diff.py"), "--repo", str(repo), "--base", str(base)], {}),
    }
    return por_etapa[etapa]


def ramo_principal(repo: Path) -> str:
    """`desenvolvimento.ramo_principal` de kaizen.config.json (defeito main)."""
    try:
        dev = json.loads((repo / "kaizen.config.json").read_text(encoding="utf-8")).get("desenvolvimento")
    except (OSError, ValueError):
        return "main"
    ramo = dev.get("ramo_principal") if isinstance(dev, dict) else None
    return ramo.strip() if isinstance(ramo, str) and ramo.strip() else "main"


def base_por_defeito(repo: Path) -> str | None:
    """`origin/<ramo_principal>` ou `<ramo_principal>` se existirem; senão None."""
    ramo = ramo_principal(repo)
    for ref in (f"origin/{ramo}", ramo):
        r = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd=repo, capture_output=True)
        if r.returncode == 0:
            return ref
    return None


def correr(etapa: str, repo: Path, base: str | None) -> int:
    cmd, extra = comando(etapa, repo, base)
    try:
        return subprocess.run(cmd, cwd=repo, env={**os.environ, **extra}).returncode
    except OSError as e:
        print(f"quality: {etapa}: ferramenta em falta ({e})", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", default=None)
    ap.add_argument("--so", nargs="+", choices=ETAPAS, default=None, help="só estas etapas")
    ap.add_argument("--lista", action="store_true", help="listar as etapas e sair")
    a = ap.parse_args(argv)
    if a.lista:
        print("\n".join(ETAPAS))
        return 0
    repo = Path(a.repo).resolve()
    base = a.base or base_por_defeito(repo)
    escolhidas = [e for e in ETAPAS if a.so is None or e in a.so]
    falhas: list[str] = []
    for etapa in escolhidas:
        if etapa in ETAPAS_DIFF and base is None:
            print(f"== {etapa}: saltada (sem base; usar --base REF)")
            continue
        print(f"== {etapa}", flush=True)
        if correr(etapa, repo, base) != 0:
            falhas.append(etapa)
    if falhas:
        print(f"quality: FALHOU em {', '.join(falhas)}", file=sys.stderr)
        return 1
    print("quality: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
