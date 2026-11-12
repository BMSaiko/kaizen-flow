#!/usr/bin/env python3
"""Hook PostToolUse (Write|Edit): valida o SP acabado de gravar em sp/TODO|Doing|Done.

Lê o JSON do hook no stdin. Fora de um SP, não faz nada (rc 0). Se o SP for inválido,
escreve os problemas no stderr e devolve rc 2 para o Claude os ver.

Uso: configurado como hook PostToolUse (`.claude/settings.json`), sem argumentos.
rc: 0 sem problemas ou fora de um SP, 2 SP inválido
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
from sp_carregar import carregar  # noqa: E402

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

mod = carregar(Path(__file__).with_name("sp-validate.py"), "sp_validate", registar=False)
errors = mod.validate(path.read_text(encoding="utf-8"), path.parent.name)
if errors:
    print(f"{path.name}: " + "; ".join(errors), file=sys.stderr)
    sys.exit(2)
