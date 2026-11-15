"""Vigia uma fila de painéis do sp-fila e imprime uma linha por transição (para o Monitor do LLM).

Uso:
  python -I scripts/sp-fila-vigiar.py <fila-id> [--intervalo 10] [--uma-vez]

Só leitura: lê o estado dos SPs, `vigia.log` e o pid do vigia. Termina sozinho no fim da fila.
rc: 0 fila acabou (ou --uma-vez), 1 vigia morreu com a fila por acabar ou fila desconhecida
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sp_fila_vigiar  # noqa: E402

if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(sp_fila_vigiar.main())
