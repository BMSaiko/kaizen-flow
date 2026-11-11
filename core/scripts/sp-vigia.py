"""Vigia de uma fila de painéis (processo destacado, sem LLM).

Uso:
  python -I scripts/sp-vigia.py <fila-id> [--intervalo 10] [--uma-vez]

Arranca sozinho com `sp-fila.py` em paralelo; `sp-fila.py --parar` termina-o. Pidfile, log e memória
(`vigia.pid`, `vigia.log`, `vigia.json`) ficam na pasta da fila de painéis. Um só vigia por fila.
rc: 0 fim da fila (ou --uma-vez), 1 erro
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sp_painel_estado as pe  # noqa: E402
import sp_vigia as sv  # noqa: E402


def main(argv=None, contexto=None):
    ap = argparse.ArgumentParser(description="Vigia de uma fila de painéis do sp-fila")
    ap.add_argument("fila")
    ap.add_argument("--intervalo", type=float, default=sv.INTERVALO)
    ap.add_argument("--uma-vez", action="store_true", help="um só tick (diagnóstico)")
    args = ap.parse_args(argv)
    pasta = pe.raiz() / args.fila
    if not pasta.is_dir():
        print(f"erro: fila de painéis desconhecida: {args.fila}", file=sys.stderr)
        return 1
    pidf, logf, memf = sv.caminhos(pasta)
    if not sv.reclamar_pidfile(pidf, os.getpid(), pe.pid_vivo):
        print(f"erro: já há um vigia vivo para {args.fila}", file=sys.stderr)
        return 1
    try:
        ctx = contexto or sv.ContextoReal(args.fila, logf)
        ctx.log(f"vigia {os.getpid()} a vigiar {args.fila} (intervalo {args.intervalo}s)")
        try:
            res = sv.correr(ctx, memf, intervalo=args.intervalo, uma_vez=args.uma_vez)
        except Exception:  # destacado, o stderr perde-se: o traceback vai para o log
            import traceback
            ctx.log("vigia morreu:\n" + traceback.format_exc())
            raise
        ctx.log(f"vigia termina: {res}")
    finally:
        try:
            if pidf.read_text(encoding="utf-8").strip() == str(os.getpid()):
                pidf.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
