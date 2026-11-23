#!/usr/bin/env python3
"""Exporta `design/tokens.json` para `design/tokens.css` (custom properties, claro/escuro) e `design/tailwind.preset.js`.

Uso: python -I scripts/ds-export.py [--dir DIR] [--out DIR]
Recusa exportar tokens que não passam em ds-validate.
rc: 0 exportado · 1 tokens inválidos · 2 uso
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ds_core  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Exporta tokens.css e preset Tailwind")
    ap.add_argument("--dir", default=".")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    f = Path(a.dir) / "design" / "tokens.json"
    try:
        raiz = json.loads(f.read_text(encoding="utf-8"))
    except OSError as e:
        print(f"erro: não consegui ler {f}: {e.strerror}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"erro: {f} não é JSON válido: {e}", file=sys.stderr)
        return 2
    if falhas := ds_core.validar(raiz):
        print("\n".join(falhas))
        print("erro: tokens inválidos, nada exportado (corrigir com ds-validate.py)", file=sys.stderr)
        return 1
    out = Path(a.out) if a.out else f.parent
    out.mkdir(parents=True, exist_ok=True)
    (out / "tokens.css").write_text(ds_core.css(raiz), encoding="utf-8")
    (out / "tailwind.preset.js").write_text(ds_core.tailwind(raiz), encoding="utf-8")
    print(f"exportado {out / 'tokens.css'} e {out / 'tailwind.preset.js'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
