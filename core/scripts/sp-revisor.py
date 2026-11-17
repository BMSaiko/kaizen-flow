"""Review independente do ciclo michi: painel `revisor` só de leitura, com modelo diferente do executor (sem `Agent`).

O painel abre `claude --model <M> --effort <E>` (papel `revisor` de `.claude/modelos.json`; se coincidir com o modelo do
executor do SP, usa o seguinte da cadeia e avisa) com permissões só de leitura: `git diff/log/show`, `Read`, `Grep`, `Glob`
e `Edit(<achados>)` (cobre `Write`) apenas no ficheiro de achados. A semente leva as secções 3-5 do SP, `git diff <base>...HEAD --stat`, a checklist
do tipo e o formato dos achados que `review_ciclo.py` consome. O painel grava `revisor-<slug> done` em `sp-estado.py`; o
executor espera com `--esperar` (sem polling por LLM). Conta para o teto global de painéis; sem vaga fica `pendente`.
`--inline` mantém o review na própria sessão (SP `michi_modelo: simples` ou sem backend): imprime a semente e marca
«review não independente» para o Report.

Uso:
  python -I scripts/sp-revisor.py --sp <SP.md> --base <ref> --achados <ficheiro> [--cwd <pasta>] [--checklist codigo|ui|docs]
      [--rever-so F ...] [--backend auto|wezterm|tmux] [--inline] [--dry-run]
  python -I scripts/sp-revisor.py --sp <SP.md> --esperar [--timeout 900]
rc: 0 painel aberto / done / inline / dry-run · 1 erro, bloqueado ou falhou · 2 sem vaga (pendente) · 3 timeout de --esperar
"""
import argparse
import re
from pathlib import Path as _P
import sys as _s
_s.path.insert(0, str(_P(__file__).resolve().parent))
from painel_backend import run_hidden  # noqa: E402
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import modelos  # noqa: E402
import sp_painel_estado as pe  # noqa: E402
from review_ciclo import CHECKLISTS, checklist  # noqa: E402
from sp_carregar import carregar  # noqa: E402

_autor = carregar(Path(__file__).resolve().parent / "sp-autor.py", "sp_autor")  # backend de lançamento comum

MODELOS = modelos.DEFAULT  # os testes trocam-no
PAPEL = "revisor"
RC_TIMEOUT = 3
FORMATO = "[bloqueante|menor] ficheiro:linha descrição | verificar: como confirmar a correção"
LEITURA = ["Read", "Grep", "Glob", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)", "Bash(git status:*)"]
SCRIPTS = Path(__file__).resolve().parent


def _py(script, scripts=None):
    """`python -I <vault>/scripts/<script>` com caminho absoluto: o painel pode correr num repo externo (`--cwd`).
    Caminho com espaços vai entre aspas (o prompt e a regra `Bash(...)` usam a mesma forma)."""
    caminho = (Path(scripts or SCRIPTS) / script).as_posix()
    return f'python -I "{caminho}"' if " " in caminho else f"python -I {caminho}"


# só estes dois scripts do vault (consumir a semente, gravar o estado); o painel continua só de leitura
SCRIPTS_PAINEL = [f"Bash({_py('sp-autor.py')}:*)", f"Bash({_py('sp-estado.py')}:*)"]


class RevisorErro(Exception):
    pass


def slug_de(sp):
    return Path(sp).stem


def _front(texto, chave):
    m = re.search(rf"^{re.escape(chave)}:\s*(.+?)\s*$", texto.split("\n---", 1)[0], re.M)
    return m.group(1).strip() if m else ""


def _nivel(sp):
    return _front(Path(sp).read_text(encoding="utf-8"), "michi_modelo") or "default"


def deve_inline(sp):
    """SP `michi_modelo: simples`: o review fica na própria sessão."""
    return _nivel(sp) == "simples"


def executor(sp, data):
    """Modelo do michi que executa o SP (`michi_modelo` do frontmatter)."""
    return modelos.michi(data, _nivel(sp))[0]["model"]


def comando(exec_modelo, achados, path=None):
    """(`claude --model <M> --effort <E> …` só de leitura, aviso|None). Modelo ≠ executor quando a cadeia o permite."""
    data = modelos.load(path or MODELOS)
    cad = modelos.cadeia(data, PAPEL)
    escolhido, aviso = cad[0], None
    if escolhido == exec_modelo:
        outro = next((m for m in cad if m != exec_modelo), None)
        if outro:
            aviso = f"aviso: revisor {escolhido} coincide com o executor; a usar {outro}"
            escolhido = outro
        else:
            aviso = f"aviso: cadeia do revisor só tem {escolhido}, igual ao executor: review não independente"
    p = modelos.papel(data, PAPEL)
    permitidas = [*LEITURA, *SCRIPTS_PAINEL, f"Edit({Path(achados).resolve()})"]  # a regra Edit(path) cobre Write; Write(path) não casa
    return (["claude", "--model", escolhido, "--effort", p.get("effort", "low"),
             "--allowedTools", *permitidas, "--disallowedTools", "NotebookEdit"], aviso)


def _seccao(texto, numero):
    m = re.search(rf"^## {numero}\..*?(?=^## |\Z)", texto, re.M | re.S)
    return m.group(0).strip() if m else ""


def _git_diff(base, cwd):
    r = run_hidden(["git", "diff", f"{base}...HEAD", "--stat"], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise RevisorErro(f"git diff {base}...HEAD falhou: {r.stderr.strip()}")
    return r.stdout.strip()


def semente(sp, base, cwd, diff=None, checklist_tipo="codigo", rever_so=None):
    """Texto efémero que o painel lê (`--consume`): critérios do SP, diff, checklist e formato dos achados."""
    texto = Path(sp).read_text(encoding="utf-8")
    secoes = "\n\n".join(s for s in (_seccao(texto, n) for n in (3, 4, 5)) if s)
    stat = (diff or _git_diff)(base, cwd)
    escopo = f"Rever só: {', '.join(rever_so)}" if rever_so else "Rever o diff todo."
    return "\n".join([
        f"# Review independente de {slug_de(sp)}", "",
        "Só lês: nunca corrijas, não faças commit, não edites nada. As correções são do executor.",
        "Critérios: bloqueante = bug, regressão, falha de segurança ou teste em falta; menor = estilo e nomes.", "",
        secoes, "",
        f"## Diff (`git diff {base}...HEAD --stat`)", stat or "(vazio)", "", escopo, "",
        f"## Checklist ({checklist_tipo})", checklist(checklist_tipo), "",
        "## Formato dos achados (uma linha cada; ficheiro vazio = sem achados)", FORMATO, "",
    ])


def prompt(sp, semente_path, achados):
    """Prompt numa só linha (o Enter submete-o)."""
    slug = slug_de(sp)
    return (f"És o painel revisor de {slug}. Primeiro corre `{_py('sp-autor.py')} --consume \"{semente_path}\"` "
            "(semente: critérios, diff e formato; lida e apagada). Revê o diff só em leitura e escreve os achados, uma linha cada, "
            f"em {achados} (ficheiro vazio se não houver nenhum); não corrijas código, sem commit, sem abrir outros painéis. "
            f"No fim corre `{_py('sp-estado.py')} {_autor.chave(slug, PAPEL)} done --msg '<N bloqueantes, M menores>'` "
            "(ou bloqueado/falhou com o motivo) e fecha este painel com `wezterm cli kill-pane --pane-id $WEZTERM_PANE` (não uses /quit).")


def _rearmar(slug, estado_root=None):
    """Iteração nova do review: o painel `revisor-<slug>` da anterior (done/falhou/bloqueado) volta a `pendente`
    pelas transições válidas, para o painel novo arrancar e o `--esperar` não ler o `done` antigo."""
    k = _autor.chave(slug, PAPEL)
    try:
        fila = pe.procurar(k, root=estado_root)
        atual = pe.ler(fila, k, root=estado_root)["estado"]
    except pe.ErroEstado:
        return
    if atual == "done":
        pe.transitar(k, "bloqueado", msg="nova iteração do review", fila=fila, root=estado_root)
        atual = "bloqueado"
    if atual in ("bloqueado", "falhou"):
        pe.transitar(k, "pendente", msg="nova iteração do review", fila=fila, root=estado_root)


def lancar(sp, base, achados, backend, cwd, estado_root=None, run=None, sleep=time.sleep, diff=None,
           checklist_tipo="codigo", rever_so=None, modelos_path=None):
    """Abre o painel revisor; devolve o dict de `sp-autor.lancar` + `aviso`. Apaga achados antigos antes de abrir."""
    sp, achados = Path(sp), Path(achados)
    if not sp.is_file():
        raise RevisorErro(f"SP inexistente: {sp}")
    data = modelos.load(modelos_path or MODELOS)
    cmd, aviso = comando(executor(sp, data), achados, modelos_path)
    sem = achados.with_name(f"{achados.stem}.semente.md")
    sem.write_text(semente(sp, base, cwd, diff, checklist_tipo, rever_so), encoding="utf-8")
    achados.unlink(missing_ok=True)
    _rearmar(slug_de(sp), estado_root)
    res = _autor.lancar(sp, sem, backend, cwd, estado_root=estado_root, run=run, sleep=sleep, rotulo=PAPEL,
                        prompt_fn=lambda s, p: prompt(s, p, achados), cmd=cmd)
    if res["estado"] != "a-correr":
        sem.unlink(missing_ok=True)  # nada a consumir: não deixar a semente órfã
    return {**res, "aviso": aviso}


def esperar_estado(slug, timeout=900, intervalo=5, estado_root=None, sleep=time.sleep, agora=time.monotonic):
    """Como `esperar`, mas devolve `(rc, ultimo_estado)`; estado `None` = painel sem registo."""
    k, limite = _autor.chave(slug, PAPEL), agora() + timeout
    while True:
        try:
            e = pe.ler(pe.procurar(k, root=estado_root), k, root=estado_root)["estado"]
        except pe.ErroEstado:
            e = None
        if e == "done":
            return 0, e
        if e in ("bloqueado", "falhou"):
            return 1, e
        if agora() >= limite:
            return RC_TIMEOUT, e
        sleep(intervalo)


def esperar(slug, timeout=900, intervalo=5, estado_root=None, sleep=time.sleep, agora=time.monotonic):
    """Bloqueia até `revisor-<slug>` ficar final. 0 done · 1 bloqueado/falhou/desconhecido · RC_TIMEOUT."""
    return esperar_estado(slug, timeout, intervalo, estado_root, sleep, agora)[0]


def main(argv=None, diff=None):
    ap = argparse.ArgumentParser(description="Review independente num painel revisor só de leitura (sem Agent).")
    ap.add_argument("--sp", required=True, help="SP (.md) a rever")
    ap.add_argument("--base", default="master", help="ref base do diff (defeito: master)")
    ap.add_argument("--achados", help="ficheiro de achados que o revisor escreve (entrada de review_ciclo.py)")
    ap.add_argument("--cwd", default=str(Path.cwd()), help="pasta do painel (a worktree; defeito: cwd)")
    ap.add_argument("--checklist", default="codigo", choices=sorted(CHECKLISTS))
    ap.add_argument("--rever-so", nargs="+", metavar="F", help="re-review: só estes ficheiros (saída «Rever só» de review_ciclo.py)")
    ap.add_argument("--backend", default="auto", help="auto|wezterm|tmux")
    ap.add_argument("--modelos", help="modelos.json alternativo")
    ap.add_argument("--inline", action="store_true", help="review na própria sessão (imprime a semente; não independente)")
    ap.add_argument("--esperar", action="store_true", help="bloqueia até o revisor acabar (rc 3 = timeout)")
    ap.add_argument("--timeout", type=int, default=900, help="segundos de --esperar (defeito 900)")
    ap.add_argument("--dry-run", action="store_true", help="mostra título, comando e prompt sem abrir")
    args = ap.parse_args(argv)
    global MODELOS
    if args.modelos:
        MODELOS = Path(args.modelos)
    try:
        if args.esperar:
            rc, estado = esperar_estado(slug_de(args.sp), args.timeout)
            print({0: "revisor done", 1: "revisor bloqueado ou falhou",
                   RC_TIMEOUT: f"timeout ({args.timeout}s, ultimo estado: {estado or 'desconhecido'})"}[rc])
            return rc
        if not args.achados:
            ap.error("indicar --achados (ou --esperar)")
        if args.inline or deve_inline(args.sp):
            print("review não independente (inline): registar no Report\n")
            print(semente(args.sp, args.base, args.cwd, diff, args.checklist, args.rever_so))
            return 0
        data = modelos.load(MODELOS)
        cmd, aviso = comando(executor(args.sp, data), args.achados, MODELOS)
        if aviso:
            print(aviso, file=sys.stderr)
        if args.dry_run:
            print(f"{_autor.titulo(slug_de(args.sp), PAPEL)} · {' '.join(cmd)} · {args.cwd}\n"
                  f"{prompt(args.sp, Path(args.achados).with_name(Path(args.achados).stem + '.semente.md'), args.achados)}")
            return 0
        import painel_backend
        backend = painel_backend.escolher(args.backend)
        if backend is None:
            print(f"aviso: {painel_backend.falta(args.backend)}; a cair em --inline (review não independente)", file=sys.stderr)
            print(semente(args.sp, args.base, args.cwd, diff, args.checklist, args.rever_so))
            return 0
        res = lancar(args.sp, args.base, args.achados, backend, args.cwd, run=painel_backend.run_hidden, diff=diff,
                     checklist_tipo=args.checklist, rever_so=args.rever_so)
    except (RevisorErro, _autor.SpAutorErro, modelos.ModelosError, pe.ErroEstado) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
    if res["estado"] == "pendente":
        print("sem vaga: esperar ou usar --inline (review não independente)", file=sys.stderr)
    print(f"{res['chave']} · {res['estado']} · {res['modelo']}" + (f" · {res['msg']}" if res["msg"] else ""))
    return {"a-correr": 0, "pendente": 2}.get(res["estado"], 1)


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    sys.exit(main())
