"""Carrega scripts/sp-list.py (nome com hífen) como módulo."""
import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("sp_list", Path(__file__).resolve().parent / "sp-list.py")
_m = importlib.util.module_from_spec(_spec)
sys.modules["sp_list"] = _m
_spec.loader.exec_module(_m)
globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})
