"""Carrega scripts/sp-list.py (nome com hífen) como módulo.

Uso: módulo importado por os testes e scripts que usam sp-list.py; sem execução direta
rc: n/a
"""
import sys
from pathlib import Path
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
from sp_carregar import carregar  # noqa: E402

_m = carregar(Path(__file__).resolve().parent / "sp-list.py", "sp_list", fresco=True)
globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})
