"""`kaizen term ls`: lista única de painéis com SP, fase do michi, estado e fila (só leitura).

Cruza o estado em disco (`sp_painel_estado.filas`) com os painéis vivos do backend (`painel_backend`). Um SP ativo
(`a-correr`/`pergunta`) cujo painel não existe no backend aparece como `morto`; sem backend a coluna `vivo` fica
vazia e um aviso vai para stderr. Nunca escreve estado nem fecha painéis; o backend é chamado com timeout.

Uso: python -I scripts/kf_term_ls.py [--json] [--fila FILA]
rc: 0 ok (mesmo sem backend ou sem estado), 2 argumento inválido
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import painel_backend as pb  # noqa: E402
import sp_painel_estado as pe  # noqa: E402

TIMEOUT_S = 5
CAMPOS = ("painel", "slug", "fila", "fase", "estado", "pergunta", "vivo")
COLUNAS = (("PAINEL", "painel"), ("SP", "slug"), ("FASE", "fase"), ("ESTADO", "estado"), ("FILA", "fila"))


def _com_timeout(run):
    def _run(*args, **kwargs):
        kwargs.setdefault("timeout", TIMEOUT_S)
        return run(*args, **kwargs)
    return _run


def backend_por_config(repo=None):
    """(backend, aviso): o backend escolhido por `painelBackend` ou (None, o que falta). Sem escrita."""
    try:
        import kaizen_config
        cfg = kaizen_config.painel_backend(repo or Path.cwd())
    except Exception:  # noqa: BLE001 - config ilegível: deteção automática
        cfg = "auto"
    b = pb.escolher(cfg, run=_com_timeout(pb.run_hidden))
    return (b, None) if b else (None, pb.falta(cfg))


def _vivos(backend):
    """(ids vivos ou None, aviso ou None); o backend falhar ou demorar nunca rebenta a listagem."""
    if backend is None:
        return None, None
    try:
        return {str(k) for k in backend.listar()}, None
    except subprocess.TimeoutExpired:
        return None, f"backend {backend.nome}: timeout a listar painéis ({TIMEOUT_S} s)"
    except (pb.BackendError, OSError, subprocess.SubprocessError, ValueError) as e:
        return None, f"backend {backend.nome}: {e}"


def _linha(sp, vivos):
    pane = sp.get("pane")
    pane = None if pane in (None, "") else str(pane)
    ativo = sp.get("estado") in pe.ATIVOS
    if vivos is None:
        vivo = None
    elif pane in vivos:
        vivo = "vivo"
    else:
        vivo = "morto" if ativo else None  # SP acabado sem painel é o normal, só os ativos denunciam painel morto
    return {"painel": pane, "slug": sp.get("slug"), "fila": sp.get("fila"), "fase": sp.get("fase"),
            "estado": sp.get("estado"), "pergunta": sp.get("pergunta"), "vivo": vivo}


def linhas(root=None, backend=None, fila=None, vivos=None):
    """Uma linha por SP de todas as filas (ou só de `fila`); `vivos` (ids) dispensa chamar o backend."""
    if vivos is None:
        vivos, _ = _vivos(backend)
    return [_linha(sp, vivos) for f in pe.filas(root) if fila in (None, f["fila"]) for sp in f["sps"]]


def _texto(rows):
    if not rows:
        return "sem SPs registados"
    tab = [[c for c, _ in COLUNAS]]
    for r in rows:
        v = r["vivo"]
        estado = r["estado"] if v != "morto" else f"{r['estado']} (morto)"
        tab.append([("-" if r[k] is None else str(r[k])) if k != "estado" else estado for _, k in COLUNAS])
    larg = [max(len(l[i]) for l in tab) for i in range(len(COLUNAS))]
    return "\n".join("  ".join(c.ljust(larg[i]) for i, c in enumerate(l)).rstrip() for l in tab)


def main(argv=None, root=None, backend=False, aviso=None):
    """`backend=False`: escolher pela config; `None`: sem backend (com `aviso`); instância: usar essa."""
    p = argparse.ArgumentParser(prog="kaizen term ls", description="Painéis com SP, fase, estado e fila (só leitura).")
    p.add_argument("--json", action="store_true", help="saída JSON (contrato estável)")
    p.add_argument("--fila", help="só os SPs desta fila")
    a = p.parse_args(argv)
    if backend is False:
        backend, aviso = backend_por_config()
    vivos, erro = _vivos(backend)
    if backend is None:
        erro = aviso or "sem backend de painéis"
    if erro:
        print(f"aviso: {erro}; estado dos painéis não verificado", file=sys.stderr)
    rows = linhas(root, fila=a.fila, vivos=vivos)
    print(json.dumps(rows, ensure_ascii=False, indent=2) if a.json else _texto(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
