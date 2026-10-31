#!/usr/bin/env python3
"""Vista unificada das sessões paralelas do sp-fila: SP, worktree, painel, fase, requests, resultado. Só leitura.

Junta o estado da fila (`~/.claude/sp-fila-estado.json`) com a pasta de cada SP (TODO/Doing/Done).

Uso:
  python -I scripts/sp-painel.py
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLUNAS = ["SP", "WORKTREE", "PAINEL", "FASE", "REQUESTS", "RESULTADO"]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def vista(estado_path, root=None):
    estado_path = Path(estado_path)
    if not estado_path.exists():
        return "sem fila em curso (arrancar com `sp-fila.py --concorrencia N`)"
    estado = json.loads(estado_path.read_text(encoding="utf-8"))
    sp_list = _load("sp_list_painel", "sp-list.py")
    fase = {sp.slug: sp.status for sp in sp_list.collect(Path(root) if root else sp_list.default_root(), include_done=True)}
    linhas = [[slug, s.get("worktree", "-"), s.get("painel", "-"), fase.get(slug, "?"), str(s.get("requests", "-")), "em curso"]
              for slug, s in estado.get("sessoes", {}).items()]
    for chave, resultado in (("feitos", "feito"), ("falhados", "falhado")):
        linhas += [[slug, "-", "-", fase.get(slug, "?"), "-", resultado] for slug in estado.get(chave, [])]
    tabela = [COLUNAS] + linhas
    larguras = [max(len(r[i]) for r in tabela) for i in range(len(COLUNAS))]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, larguras)).rstrip() for r in tabela)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sp_fila_estado = Path.home() / ".claude" / "sp-fila-estado.json"
    ap = argparse.ArgumentParser(description="Vista unificada das sessões paralelas")
    ap.add_argument("--estado", default=str(sp_fila_estado), help=argparse.SUPPRESS)
    ap.add_argument("--root", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    print(vista(args.estado, args.root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
