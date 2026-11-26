#!/usr/bin/env python3
"""E2E real do motor herdr do sp-fila numa sessão herdr isolada: 2 projetos, 3 painéis, teto e retoma.

Sobe `herdr --session <nome> server` e aponta `HERDR_SOCKET_PATH` ao socket dessa sessão (a sessão por defeito nunca é tocada),
abre 3 painéis em 2 repos de teste com o `HerdrBackend`, ocupa as 3 vagas na fila (a 4.ª é recusada), mata um painel e
confirma que `sp_fila_nucleo.retomar` adota 2 e marca 1 como falhado, de forma idempotente. No fim pára e apaga a sessão.

Uso: python -I core/scripts/herdr-e2e-multiprojeto.py --isolado [--manter]
rc: 0 = tudo verde; 1 = falhou um passo; 2 = sem `herdr` ou sem `--isolado`
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import painel_backend  # noqa: E402
import sp_fila_nucleo as nucleo  # noqa: E402
import sp_painel_estado as pe  # noqa: E402

SLUGS = ("sp-a1", "sp-a2", "sp-b1")


def _passo(ok, texto):
    print(("ok   " if ok else "FALHA ") + texto)
    if not ok:
        raise SystemExit(1)


def _esperar(cond, tentativas=40, pausa=0.25):
    for _ in range(tentativas):
        if cond():
            return True
        time.sleep(pausa)
    return False


def _repo(raiz, nome):
    d = raiz / nome
    d.mkdir()
    subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
    return d


def correr(manter=False):
    sessao = f"kf-e2e-{os.getpid()}"
    tmp = Path(tempfile.mkdtemp(prefix="kf-e2e-"))
    codigo = tmp / "code"
    codigo.mkdir()
    repos = {"a": _repo(codigo, "proj-a"), "b": _repo(codigo, "proj-b")}
    srv = subprocess.Popen(["herdr", "--session", sessao, "server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        socket = Path.home() / ".config/herdr/sessions" / sessao / "herdr.sock"
        _passo(_esperar(socket.exists), f"servidor isolado `{sessao}` a correr")
        os.environ.update(HERDR_SOCKET_PATH=str(socket), SB_CODE_ROOT=str(codigo), SP_FILA_ROOT=str(tmp / "fila"))
        for k in ("HERDR_PANE_ID", "HERDR_TAB_ID", "HERDR_WORKSPACE_ID"):
            os.environ.pop(k, None)
        ops = nucleo.ops_herdr()
        _passo(ops.paineis() == [], "sessão isolada começa vazia (a sessão por defeito não é vista)")

        backend = painel_backend.HerdrBackend()
        panes = [backend.abrir(["sleep", "300"], repos[k], projeto=f"proj-{k}") for k in ("a", "a", "b")]
        _passo(all(panes) and len(set(panes)) == 3, f"3 painéis abertos: {panes}")
        _passo(_esperar(lambda: len(ops.paineis()) == 3), "herdr lista 3 painéis")
        labels = {w.get("label") for w in ops.json(["workspace", "list"]).get("workspaces") or []}
        _passo(labels == {"proj-a", "proj-b"}, f"1 workspace por projeto: {sorted(labels)}")

        fila = pe.criar_fila(programa="e2e", modo="paralelo", ordem=[*SLUGS, "sp-c1"])
        for slug, pane in zip(SLUGS, panes):
            _passo(pe.reclamar_vaga(slug, fila=fila, pane=pane), f"vaga ocupada por {slug}")
        _passo(pe.reclamar_vaga("sp-c1", fila=fila) is False, "4.ª vaga recusada (teto 3)")

        backend.fechar(panes[2])
        _passo(_esperar(lambda: len(ops.paineis()) == 2), "painel fechado desaparece do herdr")
        estado = {"fila_paineis": fila, "sessoes": {s: {} for s in SLUGS}, "falhados": []}
        r = nucleo.retomar(estado, ops=ops)
        _passo(sorted(r["adotados"]) == ["sp-a1", "sp-a2"] and r["mortos"] == ["sp-b1"], f"retoma: {r}")
        _passo(pe.ler(fila, "sp-b1")["estado"] == "falhou" and estado["falhados"] == ["sp-b1"], "painel morto marcado `falhou`")
        _passo(nucleo.retomar(estado, ops=ops) == {"adotados": ["sp-a1", "sp-a2"], "mortos": []}, "retoma idempotente")
        _passo(pe.reclamar_vaga("sp-c1", fila=fila), "vaga libertada reutilizada por sp-c1")
        print("e2e: tudo verde")
    finally:
        if not manter:
            subprocess.run(["herdr", "--session", sessao, "server", "stop"], capture_output=True, timeout=30, check=False)
            subprocess.run(["herdr", "session", "delete", sessao], capture_output=True, timeout=30, check=False)
        srv.terminate()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--isolado", action="store_true", help="obrigatório: corre numa sessão herdr própria, nunca na do utilizador")
    ap.add_argument("--manter", action="store_true", help="não parar nem apagar a sessão no fim (depuração)")
    args = ap.parse_args(argv)
    if not args.isolado:
        print("recusado: sem --isolado (o e2e nunca corre na sessão do utilizador)", file=sys.stderr)
        return 2
    if subprocess.run(["which", "herdr"], capture_output=True).returncode != 0:
        print("sem `herdr` no PATH", file=sys.stderr)
        return 2
    try:
        correr(args.manter)
    except SystemExit as e:
        return int(e.code or 0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
