#!/usr/bin/env python3
"""Hook PostToolUse (Write|Edit): valida o SP acabado de gravar em sp/TODO|Doing|Done.

Lê o JSON do hook no stdin. Fora de um SP, não faz nada (rc 0). Se o SP for inválido,
escreve os problemas no stderr e devolve rc 2 para o Claude os ver.
"""
import importlib.util
import json
import sys
from pathlib import Path

try:
    data = json.load(sys.stdin)
    path = Path(data.get("tool_input", {}).get("file_path", ""))
except (ValueError, OSError):
    sys.exit(0)

parts = path.parts
if path.suffix != ".md" or "sp" not in parts or path.parent.name not in ("TODO", "Doing", "Done") or path.name.startswith("_"):
    sys.exit(0)
if not path.is_file():
    sys.exit(0)

spec = importlib.util.spec_from_file_location("sp_validate", Path(__file__).with_name("sp-validate.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
errors = mod.validate(path.read_text(encoding="utf-8"), path.parent.name)
if errors:
    print(f"{path.name}: " + "; ".join(errors), file=sys.stderr)
    sys.exit(2)
