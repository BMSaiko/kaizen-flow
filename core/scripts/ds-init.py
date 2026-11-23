#!/usr/bin/env python3
"""Cria o design system de um projeto: `DESIGN.md` e `design/tokens.json` (DTCG) a partir de uma paleta base.

Uso: python -I scripts/ds-init.py <projeto> [--dir DIR] [--primaria #hex] [--neutra #hex] [--force]
Nunca sobrescreve sem `--force`. Valida o que gera (um erro aqui é um bug do gerador).
rc: 0 criado · 1 já existe ou falha de validação · 2 uso
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ds_core  # noqa: E402

DESIGN_MD = """# {projeto}: design system

Fonte de verdade dos valores: `design/tokens.json` (W3C DTCG). Este ficheiro diz o porquê e o como; nunca repete valores.
Validar: `kaizen ds validate`. Exportar: `kaizen ds export` (gera `design/tokens.css` e `design/tailwind.preset.js`).

## Princípios
- (3 a 5 frases curtas que decidem conflitos de design: ex. clareza antes de ornamento)

## Voz e tom
- (como o produto fala: pessoa, registo, o que nunca diz)

## Layout
- Espaçamento só da escala `space.*` (múltiplos de 4px); sem valores soltos.
- Breakpoints `breakpoint.*`; desenhar do mais pequeno para o maior.
- Cor só por papel semântico (`color.light|dark.*`), nunca pela paleta crua.

## Acessibilidade (WCAG 2.2 AA)
- Texto >= 4.5:1; componentes de UI e foco >= 3:1; os pares estão em `$extensions.kaizen.contrast` e `ds-validate` falha se algum cair.
- Foco visível em todos os controlos; alvo de toque >= 24x24px; respeitar `prefers-reduced-motion`.

## Componentes
Para cada componente: finalidade, variantes, estados (repouso, hover, foco, ativo, desativado, erro, a carregar), tokens usados, regras de a11y.

| Componente | Variantes | Estados | Tokens |
|---|---|---|---|
| Botão | primário, secundário, fantasma | todos | `primary`, `on-primary`, `radius.md`, `space.2/4` |
| Campo de texto | normal, erro | todos | `border`, `text`, `danger`, `radius.md` |
| (acrescentar) | | | |
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description="Cria DESIGN.md e design/tokens.json")
    ap.add_argument("projeto")
    ap.add_argument("--dir", default=".")
    ap.add_argument("--primaria", default="#2563eb")
    ap.add_argument("--neutra", default="#64748b")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    base = Path(a.dir)
    alvos = [base / "DESIGN.md", base / "design" / "tokens.json"]
    if not a.force and (ja := [str(p) for p in alvos if p.exists()]):
        print(f"erro: já existe {', '.join(ja)} (usar --force)", file=sys.stderr)
        return 1
    try:
        tokens = ds_core.gerar(a.primaria, a.neutra)
    except ValueError as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    if falhas := ds_core.validar(tokens):
        print("erro: tokens gerados inválidos para esta paleta:\n" + "\n".join(falhas), file=sys.stderr)
        return 1
    (base / "design").mkdir(parents=True, exist_ok=True)
    alvos[1].write_text(json.dumps(tokens, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    alvos[0].write_text(DESIGN_MD.format(projeto=a.projeto), encoding="utf-8")
    print(f"criado {alvos[0]} e {alvos[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
