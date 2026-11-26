#!/usr/bin/env python3
"""Valida `design/tokens.json`: schema DTCG, `{alias}` resolúveis, contraste WCAG (texto 4.5:1, UI 3:1) e escalas.

Uso: python -I scripts/ds-validate.py [--dir DIR | FICHEIRO.json]
Sem argumentos lê `design/tokens.json` do diretório atual. Falhas: `[categoria] caminho: mensagem`, uma por linha.
rc: 0 válido · 1 falhas · 2 uso (ficheiro em falta ou JSON inválido)
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ds_core  # noqa: E402


def carregar(ficheiro):
    return json.loads(Path(ficheiro).read_text(encoding="utf-8"))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Valida design/tokens.json")
    ap.add_argument("ficheiro", nargs="?")
    ap.add_argument("--dir", default=".")
    a = ap.parse_args(argv)
    f = Path(a.ficheiro) if a.ficheiro else Path(a.dir) / "design" / "tokens.json"
    try:
        raiz = carregar(f)
    except OSError as e:
        print(f"erro: não consegui ler {f}: {e.strerror}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"erro: {f} não é JSON válido: {e}", file=sys.stderr)
        return 2
    falhas = ds_core.validar(raiz)
    if falhas:
        print("\n".join(falhas))
        print(f"{len(falhas)} falha(s)")
        return 1
    print(f"ok: {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
