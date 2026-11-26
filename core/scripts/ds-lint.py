#!/usr/bin/env python3
"""Deteta literais de cor, espaçamento e tipografia fora dos tokens do design system (CSS/SCSS/TSX/JSX/HTML/Vue/Svelte).

Cor só por `var(--token)`; espaçamento (margin, padding, gap, top/left/...) só por `var(--space-*)` (0 e `auto` passam);
`font-size`/`font-family` só por token. Ignora `design/`, `node_modules`, builds e linhas com `ds-lint-ignore`.

Uso: python -I scripts/ds-lint.py [--dir D]
Saída: `ficheiro:linha: mensagem`, uma por achado.
rc: 0 limpo · 1 literais encontrados
"""
import argparse
import re
import sys
from pathlib import Path

EXT = {".css", ".scss", ".sass", ".less", ".tsx", ".jsx", ".html", ".vue", ".svelte"}
IGNORAR = {"node_modules", "dist", "build", "out", "coverage", ".git", "design", ".next", ".svelte-kit", "target"}
COR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|hwb|oklch|lab)\(", re.I)
PROP_ESPACO = r"(?:margin|padding|gap|row-gap|column-gap|top|right|bottom|left|inset|margin-\w+|padding-\w+)"
ESPACO = re.compile(rf"(?<![\w-]){PROP_ESPACO}['\"]?\s*:\s*[^;}}\n]*?(?<![\w.#-])(-?\d*\.?\d+)(px|rem|em)\b", re.I)
TAM_FONTE = re.compile(r"(?<![\w-])font-size['\"]?\s*:\s*[^;}\n]*?(?<![\w.#-])\d*\.?\d+(?:px|rem|em|pt)\b", re.I)
FAMILIA = re.compile(r"(?<![\w-])font-family['\"]?\s*:\s*(?!\s*var\()(?!\s*inherit\b)(?!\s*['\"]?\s*\$)[^;}\n]+", re.I)
PROP_FONTE_CAMEL = re.compile(r"\bfontFamily\s*:\s*['\"][^'\"]+['\"]")


def _sem_tokens(linha):
    """Remove `var(...)` para que o conteúdo dos tokens não dispare falsos positivos."""
    return re.sub(r"var\([^)]*\)", "var()", linha)


def _achados_linha(linha):
    l2 = _sem_tokens(linha)
    achados = []
    if COR.search(l2):
        achados.append("cor literal: usar `var(--color-*)`")
    m = ESPACO.search(l2)
    if m and float(m.group(1)) != 0:
        achados.append(f"espaçamento literal ({m.group(1)}{m.group(2)}): usar `var(--space-*)`")
    if TAM_FONTE.search(l2):
        achados.append("tamanho de fonte literal: usar `var(--font-size-*)`")
    if FAMILIA.search(l2) or PROP_FONTE_CAMEL.search(l2):
        achados.append("font-family literal: usar `var(--font-*)`")
    return achados


def _ficheiros(raiz):
    for p in sorted(Path(raiz).rglob("*")):
        rel = p.relative_to(raiz)
        if p.is_file() and p.suffix.lower() in EXT and not (set(rel.parts[:-1]) & IGNORAR) \
                and p.name not in ("tokens.css",):
            yield p, rel


def lint(raiz):
    """[(ficheiro relativo, linha, mensagem)] dos literais fora dos tokens."""
    saida = []
    for p, rel in _ficheiros(raiz):
        try:
            linhas = p.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for n, linha in enumerate(linhas, 1):
            if "ds-lint-ignore" in linha:
                continue
            saida += [(rel.as_posix(), n, msg) for msg in _achados_linha(linha)]
    return saida


def main(argv=None):
    ap = argparse.ArgumentParser(description="Literais fora dos tokens do design system")
    ap.add_argument("--dir", default=".")
    a = ap.parse_args(argv)
    achados = lint(a.dir)
    for f, n, msg in achados:
        print(f"{f}:{n}: {msg}")
    if achados:
        print(f"{len(achados)} literal(is) fora dos tokens")
        return 1
    print("ok: sem literais fora dos tokens")
    return 0


if __name__ == "__main__":
    sys.exit(main())
