"""Valida um Research Brief do DR: Scope Gate, Orçamento, Síntese ≤25 linhas com fontes `ficheiro:linha`.

Uso: python -I scripts/dr-check.py <brief.md>   (rc 0 ok, 1 erros)
rc: 0 ok, 1 há erros, 2 número de argumentos errado
"""
import re
import sys
from pathlib import Path

MAX_LINHAS = 25
MIN_FONTES = 3
GATES = {"Full", "Delta", "Skipped"}
FONTE = re.compile(r"`[^`\s]+:\d+(?:-\d+)?`")


def check(path):
    t = Path(path).read_text(encoding="utf-8")
    erros = []
    m = re.search(r"Scope Gate:\*\*\s*(\S+)", t)
    if not m or m.group(1) not in GATES:
        erros.append("Scope Gate em falta ou inválido (Full/Delta/Skipped)")
    o = re.search(r"Orçamento:\*\*[ \t]*(\S.*)", t)
    if not o:
        erros.append("Orçamento em falta (nº de leituras/greps e porque parou)")
    s = re.search(r"^## Síntese\s*\n(.*?)(?=^## |\Z)", t, re.S | re.M)
    if not s:
        erros.append("secção ## Síntese em falta")
        return erros
    linhas = [x for x in s.group(1).splitlines() if x.strip()]
    if len(linhas) > MAX_LINHAS:
        erros.append(f"Síntese com {len(linhas)} linhas (máx {MAX_LINHAS})")
    n = len(FONTE.findall(s.group(1)))
    if n < MIN_FONTES:
        erros.append(f"Síntese com {n} fontes `ficheiro:linha` (mín {MIN_FONTES})")
    return erros


def main(argv):
    if len(argv) != 1:
        print(__doc__)
        return 2
    erros = check(argv[0])
    for e in erros:
        print("ERRO:", e)
    if not erros:
        print("OK")
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
