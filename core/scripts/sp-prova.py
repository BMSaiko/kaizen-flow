#!/usr/bin/env python3
"""Grava uma prova/relatório em `sp/proofs/` a partir de um ficheiro, sem heredocs.

Uso: python -I scripts/sp-prova.py <nome> --arquivo <origem> [--project P] [--root R]

O painel escreve o texto com a ferramenta Write (num ficheiro temporário) e chama
este script; assim não há `$` nem crases numa linha de comando que peça aprovação.
Copia bytes (preserva CRLF); recusa nomes com separadores e não sobrescreve sem --forcar.
"""
import argparse
import importlib.util
import re
import shutil
import sys
from pathlib import Path

_cspec = importlib.util.spec_from_file_location("kaizen_config", Path(__file__).with_name("kaizen_config.py"))
_cfg = importlib.util.module_from_spec(_cspec)
_cspec.loader.exec_module(_cfg)

NOME_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def destino(root, nome, project):
    if not NOME_OK.match(nome) or ".." in nome:
        raise ValueError(f"nome inválido: {nome!r}")
    if not nome.endswith(".md"):
        nome += ".md"
    return _cfg.sp_root(root) / project / "sp" / "proofs" / nome


def gravar(root, nome, origem, project="kaizenflow", forcar=False):
    src = Path(origem)
    if not src.is_file():
        raise FileNotFoundError(f"origem não existe: {src}")
    dst = destino(root, nome, project)
    if dst.exists() and not forcar:
        raise FileExistsError(f"já existe: {dst} (usar --forcar)")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return dst


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("nome")
    ap.add_argument("--arquivo", required=True, help="ficheiro com o texto")
    ap.add_argument("--project", default="kaizenflow")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--forcar", action="store_true")
    args = ap.parse_args(argv)
    try:
        dst = gravar(args.root, args.nome, args.arquivo, args.project, args.forcar)
    except (ValueError, FileNotFoundError, FileExistsError) as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    print(dst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
