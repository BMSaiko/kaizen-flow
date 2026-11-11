"""Preenche um SP vazio num painel `sp-autor` (sem `Agent`): modelo do papel, semente efémera, estado em ficheiro.

O painel abre `claude --model <M> --effort <E>` (papel `sp-autor` de `.claude/modelos.json`) no cwd dado, recebe o
título `sp-autor <slug>` e um prompt numa linha: ler a semente com `--consume` (imprime e só depois apaga, como o
`/handoff`), preencher o SP pela skill `super-prompt` §Gerar, gravar `done` com `sp-estado.py sp-autor-<slug>` e
fechar. Conta para o teto global de painéis (`sp_painel_estado.MAX_PARALELO`); sem vaga fica `pendente` e nada abre.
A sessão que pediu fica livre: segue com `sp-estado.py --listar` ou o vigia.

Uso:
  python -I scripts/sp-autor.py --sp <SP.md vazio> --semente <ficheiro> [--cwd <pasta>] [--backend auto|wezterm|tmux] [--dry-run]
  python -I scripts/sp-autor.py --consume <semente>
rc: 0 painel aberto (ou dry-run / consume ok) · 1 erro · 2 sem vaga (pendente)
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import modelos  # noqa: E402
import sp_painel_estado as pe  # noqa: E402

MODELOS = modelos.DEFAULT  # os testes trocam-no
PAPEL = "sp-autor"
FILA = "sp-autor"  # fila própria dos painéis sp-autor (reusada)


class SpAutorErro(Exception):
    pass


def slug_de(sp):
    return Path(sp).stem


def chave(slug):
    """Nome no estado das filas (não colide com o michi do mesmo SP)."""
    return f"{PAPEL}-{slug}"


def titulo(slug):
    return f"{PAPEL} {slug}"


def comando(path=None):
    """`claude --model <M> --effort <E>` do papel `sp-autor`."""
    p = modelos.papel(modelos.load(path or MODELOS), PAPEL)
    return ["claude", "--model", p["model"], "--effort", p.get("effort", "medium")]


def prompt(sp, semente):
    """Prompt numa só linha (o Enter submete-o)."""
    slug = slug_de(sp)
    return (f"És o painel sp-autor de {slug}. Primeiro corre `python -I scripts/sp-autor.py --consume \"{semente}\"` "
            f"(semente: decisões e contexto; lida e apagada). Preenche as 8 secções de {sp} pela skill super-prompt §Gerar, "
            "sem fazer o trabalho do SP, sem commit, sem abrir outros painéis. No fim corre "
            f"`python -I scripts/sp-estado.py {chave(slug)} done --msg '<resumo numa linha>'` "
            f"(ou bloqueado/falhou com o motivo) e fecha com /quit.")


def consume(path, out=print):
    """Imprime a semente e só depois a apaga (se imprimir falhar, o ficheiro fica)."""
    p = Path(path)
    if not p.is_file():
        raise SpAutorErro(f"semente inexistente: {p}")
    out(p.read_bytes().decode("utf-8"))
    p.unlink()


def _fila(root):
    fid = pe.fila_id(FILA)
    if (pe.raiz(root) / fid).exists():  # verifica a pasta, não o texto do erro de `criar_fila`
        return fid
    return pe.criar_fila(FILA, root=root)


def _enviar(backend, pane, texto, run, sleep):
    if backend.nome in ("wezterm", "tmux"):
        import handoff_spawn  # tarde: só para painéis reais
        handoff_spawn._wait_prompt(backend.nome, pane, run, sleep)
        handoff_spawn._send_line(backend.nome, pane, texto, run, sleep)
    elif not backend.enviar(pane, texto):
        raise RuntimeError(f"painel {pane}: o envio do prompt falhou")


def lancar(sp, semente, backend, cwd, estado_root=None, run=None, sleep=time.sleep):
    """Abre o painel; devolve {estado: a-correr|pendente|falhou, chave, pane, modelo, msg}."""
    sp, semente = Path(sp), Path(semente)
    if not sp.is_file():
        raise SpAutorErro(f"SP inexistente: {sp}")
    if not semente.is_file():
        raise SpAutorErro(f"semente inexistente: {semente}")
    cmd = comando()
    k, modelo = chave(slug_de(sp)), cmd[2]
    res = {"estado": None, "chave": k, "pane": None, "modelo": modelo, "msg": None}
    fila = _fila(estado_root)
    pe.registar(fila, k, root=estado_root, modelo=modelo, worktree=str(cwd))
    if not pe.reclamar_vaga(k, fila=fila, root=estado_root, modelo=modelo):
        return {**res, "estado": "pendente", "msg": f"sem vaga: {pe.MAX_PARALELO} painéis ativos no total"}
    pane = None
    try:
        pane = backend.abrir(cmd, str(cwd))
        f = getattr(backend, "titulo", None)
        if f:
            f(pane, titulo(slug_de(sp)))
        _enviar(backend, pane, prompt(sp, semente), run, sleep)
        pe.registar(fila, k, root=estado_root, pane=str(pane))
    except Exception as e:  # noqa: BLE001 — liberta a vaga e fecha o que abriu
        msg = f"erro a lançar {k}: {e}"
        pe.transitar(k, "falhou", msg=msg, fila=fila, root=estado_root)
        if pane is not None:
            try:
                backend.fechar(pane)
            except Exception:  # noqa: BLE001
                pass
        return {**res, "estado": "falhou", "pane": pane, "msg": msg}
    return {**res, "estado": "a-correr", "pane": str(pane)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Preenche um SP vazio num painel sp-autor (sem Agent).")
    ap.add_argument("--sp", help="SP vazio (.md) a preencher")
    ap.add_argument("--semente", help="ficheiro efémero com decisões e contexto (o painel lê e apaga)")
    ap.add_argument("--consume", metavar="SEMENTE", help="imprime a semente e apaga-a (usado pelo painel)")
    ap.add_argument("--cwd", default=str(Path(__file__).resolve().parent.parent), help="pasta do painel (defeito: o repo)")
    ap.add_argument("--backend", default="auto", help="auto|wezterm|tmux")
    ap.add_argument("--modelos", help="modelos.json alternativo")
    ap.add_argument("--dry-run", action="store_true", help="mostra título, modelo e prompt sem abrir")
    args = ap.parse_args(argv)
    global MODELOS
    if args.modelos:
        MODELOS = Path(args.modelos)
    try:
        if args.consume:
            consume(args.consume)
            return 0
        if not (args.sp and args.semente):
            ap.error("indicar --sp e --semente (ou --consume)")
        if args.dry_run:
            print(f"{titulo(slug_de(args.sp))} · {' '.join(comando())} · {args.cwd}\n{prompt(args.sp, args.semente)}")
            return 0
        import painel_backend
        backend = painel_backend.escolher(args.backend)
        res = lancar(args.sp, args.semente, backend, args.cwd, run=painel_backend.run_hidden)
    except (SpAutorErro, modelos.ModelosError, pe.ErroEstado) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
    print(f"{res['chave']} · {res['estado']} · {res['modelo']}" + (f" · {res['msg']}" if res["msg"] else ""))
    return {"a-correr": 0, "pendente": 2}.get(res["estado"], 1)


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    sys.exit(main())
