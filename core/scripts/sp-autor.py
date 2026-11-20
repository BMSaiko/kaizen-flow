"""Preenche um SP vazio num painel `sp-autor` (sem `Agent`): modelo do papel, semente efémera, estado em ficheiro.

O painel abre `claude --model <M> --effort <E>` (papel `sp-autor` de `.claude/modelos.json`) no cwd dado, recebe o
título `sp-autor <slug>` e um prompt numa linha: ler a semente com `--consume` (imprime e só depois apaga, como o
`/handoff`), preencher o SP pela skill `super-prompt` §Gerar, gravar `done` com `sp-estado.py sp-autor-<slug>` e
fechar. Conta para o teto global de painéis (`sp_painel_estado.MAX_PARALELO`); sem vaga fica `pendente` e nada abre.
A sessão que pediu fica livre: segue com `sp-estado.py --listar` ou o vigia. Ao lançar guarda-se o título da tab de
origem (`origem_titulo`, mais `origem_pane` como pista); o painel corre `--avisar <slug>` antes do `done` e a origem
recebe uma linha com o caminho do SP (resolvida pelo título; origem ausente = só registo, rc 0).

Uso:
  python -I scripts/sp-autor.py --sp <SP.md vazio> --semente <ficheiro> [--cwd <pasta>] [--backend auto|herdr|wezterm|tmux|background] [--dry-run]
  python -I scripts/sp-autor.py --consume <semente>
  python -I scripts/sp-autor.py --avisar <slug> [--sp <SP.md>] [--backend auto|herdr|wezterm|tmux|background]
rc: 0 painel aberto (ou dry-run / consume ok) · 1 erro · 2 sem vaga (pendente)
"""
import argparse
import contextlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import modelos  # noqa: E402
from handoff_pane import consume_ficheiro  # noqa: E402
from painel_backend import enviar_prompt  # noqa: E402
import painel_backend  # noqa: E402
import sp_painel_estado as pe  # noqa: E402

MODELOS = modelos.DEFAULT  # os testes trocam-no
PAPEL = "sp-autor"
FILA = "sp-autor"  # fila própria dos painéis sp-autor (reusada)


class SpAutorErro(Exception):
    pass


def slug_de(sp):
    return Path(sp).stem


def chave(slug, rotulo=PAPEL):
    """Nome no estado das filas (não colide com o michi do mesmo SP)."""
    return f"{rotulo}-{slug}"


def titulo(slug, rotulo=PAPEL):
    return f"{rotulo} {slug}"


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
            f"`python -I scripts/sp-autor.py --avisar {slug} --sp \"{sp}\"` (avisa o painel que te lançou; se falhar segue) e depois "
            f"`python -I scripts/sp-estado.py {chave(slug)} done --msg '<resumo numa linha>'` "
            f"(ou bloqueado/falhou com o motivo) e fecha este painel com "
            f"`python -I scripts/sp-autor.py --fechar {slug}` (backend ativo: herdr, wezterm ou tmux; não uses /quit).")


def consume(path, out=print):
    """Imprime a semente e só depois a apaga (se imprimir falhar, o ficheiro fica)."""
    p = Path(path)
    if not p.is_file():
        raise SpAutorErro(f"semente inexistente: {p}")
    consume_ficheiro(p, out)


def _fila(root):
    fid = pe.fila_id(FILA)
    if (pe.raiz(root) / fid).exists():  # verifica a pasta, não o texto do erro de `criar_fila`
        return fid
    return pe.criar_fila(FILA, root=root)


def origem_atual(backend, env=None):
    """(título da tab, pane-id) do painel de `$HERDR_PANE_ID`/`$WEZTERM_PANE`/`$TMUX_PANE`; (None, None) sem variável, (None, id) sem título. Nunca levanta."""
    pane = painel_backend.painel_atual(env)[1]
    if not pane:
        return None, None
    try:
        return backend.titulos().get(str(pane)), str(pane)
    except Exception:  # noqa: BLE001 — a origem é um extra, nunca impede o lançamento
        return None, str(pane)


def _linha(texto):
    return " ".join(str(texto).split())


def avisar(slug, backend, sp=None, estado_root=None, rotulo=PAPEL):
    """Envia ao painel de origem (pelo título guardado ao lançar; o pane-id só confirma) uma linha a dizer que o SP está pronto.
    Devolve `enviado` ou `origem-ausente` (nada enviado, `aviso` no estado). Nunca envia a outro painel nem ao próprio."""
    k = chave(slug, rotulo)
    fila = pe.procurar(k, root=estado_root)
    st = pe.ler(fila, k, root=estado_root)
    alvo = st.get("origem_titulo")
    destino = None
    if alvo:
        proprio = str(st.get("pane") or "")
        cand = sorted(p for p, t in backend.titulos().items() if t == alvo and str(p) != proprio)
        pista = st.get("origem_pane")
        destino = pista if pista in cand else (cand[0] if cand else None)
    if destino is not None:
        caminho = _linha(sp) if sp else f"vault, SP {slug}"
        msg = f"[sp-autor] SP {_linha(slug)} preenchido: {caminho}. Próximo: sp-resumo.py {_linha(slug)} e aprovação (super-prompt §Gerar 3-5)."
        if backend.enviar(destino, msg):
            pe.registar(fila, k, root=estado_root, aviso="enviado")
            return "enviado"
    pe.registar(fila, k, root=estado_root, aviso="aviso: origem ausente")
    return "origem-ausente"


def fechar(slug, backend, estado_root=None, rotulo=PAPEL, env=None):
    """Fecha o painel do papel pelo backend ativo (herdr/wezterm/tmux): pane guardado no estado ao lançar, senão o atual.
    Devolve o id fechado ou None (nada a fechar)."""
    k = chave(slug, rotulo)
    try:
        pane = pe.ler(pe.procurar(k, root=estado_root), k, root=estado_root).get("pane")
    except pe.ErroEstado:
        pane = None
    if not pane:
        pane = painel_backend.painel_atual(env)[1]
    if not pane:
        return None
    backend.fechar(str(pane))
    return str(pane)


def lancar(sp, semente, backend, cwd, estado_root=None, run=None, sleep=time.sleep, rotulo=PAPEL, prompt_fn=None, foco=False, cmd=None, origem=None):
    """Abre o painel (`rotulo` dá chave e título; `prompt_fn(sp, semente)` substitui o prompt do sp-autor; `foco` ativa-o; `cmd` substitui o comando do papel sp-autor; `origem` = (título, pane) de quem lança, do ambiente se None); devolve {estado: a-correr|pendente|falhou, chave, pane, modelo, msg}."""
    sp, semente = Path(sp), Path(semente)
    if not sp.is_file():
        raise SpAutorErro(f"SP inexistente: {sp}")
    if not semente.is_file():
        raise SpAutorErro(f"semente inexistente: {semente}")
    cmd = cmd or comando()
    k, modelo = chave(slug_de(sp), rotulo), cmd[2]
    res = {"estado": None, "chave": k, "pane": None, "modelo": modelo, "msg": None}
    fila = _fila(estado_root)
    o_titulo, o_pane = origem if origem is not None else origem_atual(backend)
    reg = pe.registar(fila, k, root=estado_root, modelo=modelo, worktree=str(cwd), origem_titulo=o_titulo, origem_pane=o_pane)
    if reg.get("estado") == "falhou":  # EC-022: relançar depois de um painel falhado (semente ainda por ler)
        pe.transitar(k, "pendente", fila=fila, root=estado_root)
    if not pe.reclamar_vaga(k, fila=fila, root=estado_root, modelo=modelo):
        return {**res, "estado": "pendente", "msg": f"sem vaga: {pe.MAX_PARALELO} painéis ativos no total"}
    pane = None
    try:
        pane = backend.abrir(cmd, str(cwd))
        f = getattr(backend, "titulo", None)
        if f:
            f(pane, titulo(slug_de(sp), rotulo))
        enviar_prompt(backend, pane, (prompt_fn or prompt)(sp, semente), run, sleep)
        if foco and getattr(backend, "foco", None):
            backend.foco(pane)
        pe.registar(fila, k, root=estado_root, pane=str(pane))
    except Exception as e:  # noqa: BLE001 — liberta a vaga e fecha o que abriu
        msg = f"erro a lançar {k}: {e}"
        pe.transitar(k, "falhou", msg=msg, fila=fila, root=estado_root)
        if pane is not None:
            with contextlib.suppress(Exception):  # noqa: BLE001
                backend.fechar(pane)
        return {**res, "estado": "falhou", "pane": pane, "msg": msg}
    return {**res, "estado": "a-correr", "pane": str(pane)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Preenche um SP vazio num painel sp-autor (sem Agent).")
    ap.add_argument("--sp", help="SP vazio (.md) a preencher")
    ap.add_argument("--semente", help="ficheiro efémero com decisões e contexto (o painel lê e apaga)")
    ap.add_argument("--consume", metavar="SEMENTE", help="imprime a semente e apaga-a (usado pelo painel)")
    ap.add_argument("--avisar", metavar="SLUG", help="avisa o painel que lançou o sp-autor (usado pelo painel; rc 0 mesmo sem origem)")
    ap.add_argument("--fechar", metavar="SLUG", help="fecha o painel do papel pelo backend ativo (usado pelo painel no fim)")
    ap.add_argument("--papel", default=PAPEL, help="papel do painel a fechar (sp-autor|revisor)")
    ap.add_argument("--cwd", default=str(Path(__file__).resolve().parent.parent), help="pasta do painel (defeito: o repo)")
    ap.add_argument("--backend", default="auto", help="auto (usa painelBackend)|herdr|wezterm|tmux|background")
    ap.add_argument("--modelos", help="modelos.json alternativo")
    ap.add_argument("--dry-run", action="store_true", help="mostra título, modelo e prompt sem abrir")
    args = ap.parse_args(argv)
    global MODELOS
    if args.modelos:
        MODELOS = Path(args.modelos)
    if args.fechar:
        try:
            print(f"{chave(args.fechar, args.papel)} · fechar · {fechar(args.fechar, painel_backend.escolher_por_config(args.backend), rotulo=args.papel) or 'nada'}")
        except Exception as e:  # noqa: BLE001
            print(f"erro a fechar: {e}", file=sys.stderr)
            return 1
        return 0
    if args.avisar:
        try:
            import painel_backend
            print(f"{chave(args.avisar)} · aviso · {avisar(args.avisar, painel_backend.escolher_por_config(args.backend), sp=args.sp)}")
        except Exception as e:  # noqa: BLE001 — falhar a avisar nunca muda o resultado do sp-autor
            print(f"aviso falhou (ignorado): {e}", file=sys.stderr)
        return 0
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
        backend = painel_backend.escolher_por_config(args.backend)
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
