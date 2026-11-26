#!/usr/bin/env python3
"""Move um Super Prompt entre sp/TODO, sp/Doing e sp/Done e atualiza o frontmatter.

Troca a pasta e os campos `status` e `updated`; o resto do ficheiro fica intacto.
Nunca faz commit. Usa `git mv` se o SP estiver tracked, senão renomeia.

Uso:
  python -I scripts/sp-move.py <slug> <todo|doing|done> [--project <nome>]
  python -I scripts/sp-move.py <slug> --start        # arranque: SP e mães (cadeia `parent`) em TODO passam a Doing
  python -I scripts/sp-move.py <filho> done --next   # programa: abre o próximo filho elegível; a mãe nunca é movida
  python -I scripts/sp-move.py --tipo dr|dp <slug> <todo|doing|done>   # move um DR/DP (substitui doc-move.py)
rc: 0 movido, 1 erro
"""
import contextlib
import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import doc_ops  # noqa: E402
import kaizen_engine  # noqa: E402
import wt_redirect  # noqa: E402
import kaizen_hooks  # noqa: E402

sp_list = kaizen_engine.load("sp-list")
sp_handoff = kaizen_engine.load("sp-handoff")

# opcional: o pacote kaizen-flow instala este script noutros repos sem sb-agent.py
sb_agent = None
if Path(__file__).with_name("sb-agent.py").is_file():
    sb_agent = kaizen_engine.load("sb-agent")

sp_metricas = None
if Path(__file__).with_name("sp-metricas.py").is_file():
    sp_metricas = kaizen_engine.load("sp-metricas")

DESTS = {"todo": "TODO", "doing": "Doing", "done": "Done"}


class SpMoveError(Exception):
    pass


def _rewrite_frontmatter(raw, status, updated):
    return kaizen_engine.rewrite_fields(raw, {"status": status, "updated": updated}, SpMoveError)


def _move_proofs(sp, dst):
    """Leva as provas `proofs/<slug>-*` do SP para a pasta de destino."""
    src_dir = sp.path.parent / "proofs"
    files = sorted(src_dir.glob(f"{sp.slug}-*")) if src_dir.is_dir() else []
    for f in files:
        kaizen_engine.relocate(f, dst.parent / "proofs" / f.name)
    if src_dir.is_dir() and not any(src_dir.iterdir()):
        src_dir.rmdir()
    return len(files)


def _agent_claim(slug, target):
    """Num worktree de agente: `doing` exige o claim do SP (reclama-o se livre); `done` liberta-o."""
    if sb_agent is None:
        return
    cwd = Path.cwd()
    try:
        agent = sb_agent.current_agent(cwd)
        if agent and target == "Doing":
            sb_agent.require_claim(cwd, slug)
        elif agent and target == "Done":
            sb_agent.release(cwd, slug, agent)
    except sb_agent.SbAgentError as exc:
        if target == "Doing":
            raise SpMoveError(str(exc))


def _resolver(root, slug, target, project):
    """O SP a mover e as cópias duplicadas em TODO (só ao fechar)."""
    matches = [sp for sp in sp_list.collect(root, include_done=True) if sp.slug == slug]
    if project:
        matches = [sp for sp in matches if sp.project == project]
    if not matches:
        raise SpMoveError(f"SP '{slug}' não encontrado; ver scripts/sp-list.py")
    dups = []
    if target == "Done" and len({sp.project for sp in matches}) == 1 and len(matches) > 1:
        # fechar: a cópia em TODO é resto de um fecho mal arrumado (a mãe fica duplicada); sai
        dups = [sp for sp in matches if sp.status == "TODO"]
        if len(dups) < len(matches):
            matches = [sp for sp in matches if sp.status != "TODO"]
    if len(matches) > 1:
        opts = ", ".join(f"{sp.project} ({sp.status})" for sp in matches)
        raise SpMoveError(f"SP '{slug}' ambíguo: {opts}; usar --project")
    return matches[0], dups


def _remover_dups(sp, dups):
    """A cópia desatualizada sai sempre, mesmo que o SP já esteja no destino."""
    for d in dups:
        if d.path != sp.path and d.path.exists():
            kaizen_engine.relocate(d.path, d.path.with_suffix(".md.dup"))
            d.path.with_suffix(".md.dup").unlink()


def _registar_metricas(root, dst, project):
    """Sufixo do resumo; métricas nunca bloqueiam o fecho."""
    if not sp_metricas:
        return ""
    try:
        return " (+métricas)" if sp_metricas.registar(root, dst, project) else ""
    except Exception as exc:
        return f" (métricas falharam: {exc})"


def move(root, slug, dest, project=None):
    if dest.lower() not in DESTS:
        raise SpMoveError(f"destino inválido '{dest}' (todo|doing|done)")
    target = DESTS[dest.lower()]
    sp, dups = _resolver(root, slug, target, project)
    _remover_dups(sp, dups)
    if sp.status == target:
        return f"{slug}: já está em {target} ({sp.path})"
    if target == "Doing":
        _agent_claim(slug, target)
    dst = sp.path.parent.parent / target / sp.path.name
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_raw = _rewrite_frontmatter(sp.path.read_bytes(), target, updated)
    if dst.exists():
        raise SpMoveError(f"destino já ocupado por outro ficheiro: {dst}")
    ctx = {"slug": slug, "project": sp.project, "de": sp.status, "para": target, "path": str(sp.path)}
    try:
        kaizen_hooks.fire("sp.moved", ctx, phase="pre")
    except kaizen_hooks.HookBlocked as exc:
        raise SpMoveError(str(exc))
    kaizen_engine.relocate(sp.path, dst)
    dst.write_bytes(new_raw)
    n = _move_proofs(sp, dst)
    if sp.parent:  # o `state` do filho na mãe acompanha todo o movimento, não só --start/--next
        with contextlib.suppress(Exception):  # mãe em falta/ilegível: o movimento já está feito
            sp_handoff.sync_program_ready(root, dst)
    if target == "Done":
        _agent_claim(slug, target)
    extra = f" (+{n} provas)" if n else ""
    if target == "Done":
        extra += _registar_metricas(root, dst, sp.project)
    ctx["path"] = str(dst)
    avisos = "".join(f"\naviso: {w}" for w in kaizen_hooks.fire("sp.moved", ctx, phase="post"))
    return f"{slug}: {sp.status} → {target} ({dst}){extra}{avisos}"


def _find(root, slug, project):
    return next(sp for sp in sp_list.collect(root, include_done=True) if sp.slug == slug and sp.project == project)


def advance(root, slug, project=None):
    """Fecha o filho e, se pertence a um programa, abre o próximo elegível (um só em Doing). Nunca move a mãe."""
    sps = sp_list.collect(root, include_done=True)
    kid = next((sp for sp in sps if sp.slug == slug and (not project or sp.project == project)), None)
    if kid and kid.parent and not any(sp.project == kid.project and sp.slug == kid.parent for sp in sps):
        raise SpMoveError(f"SP-mãe '{kid.parent}' não encontrado em {kid.project}; nada foi movido")
    out = [move(root, slug, "done", project)]
    sps = sp_list.collect(root, include_done=True)
    child = next(sp for sp in sps if sp.slug == slug and (not project or sp.project == project))
    if not child.parent:
        return "\n".join(out)
    ready, line = sp_handoff.sync_program_ready(root, child.path)
    doing = [sp for sp in sps if sp.project == child.project and sp.parent == child.parent and sp.status == "Doing"]
    if ready and doing:
        out.append(f"próximo elegível: {ready.slug}, não aberto: {doing[0].slug} já está em Doing")
    elif ready:
        out.append(move(root, ready.slug, "doing", child.project))
        opened = _find(root, ready.slug, child.project)
        sp_handoff.sync_program_ready(root, opened.path)
        out.append(f"/michi {opened.path}")
    else:
        out.append(line)
    return "\n".join(out)


def start(root, slug, project=None):
    """Arranque: move o SP e a cadeia `parent` (só os que estão em TODO) para Doing. Nunca toca em irmãos nem filhos."""
    sps = sp_list.collect(root, include_done=True)
    kid = next((sp for sp in sps if sp.slug == slug and (not project or sp.project == project)), None)
    if kid is None:
        return move(root, slug, "doing", project)  # levanta o erro habitual (não encontrado/ambíguo)
    chain, seen, cur = [kid], {kid.slug}, kid
    while cur.parent and cur.parent not in seen:
        cur = next((sp for sp in sps if sp.project == kid.project and sp.slug == cur.parent), None)
        if cur is None:
            break
        chain.append(cur)
        seen.add(cur.slug)
    out = [move(root, sp.slug, "doing", sp.project) for sp in reversed(chain) if sp.status == "TODO" or sp is kid]
    if kid.parent:
        opened = _find(root, slug, kid.project)
        sp_handoff.sync_program_ready(root, opened.path)
    return "\n".join(out)


def avisos_fecho(root, slug, project=None):
    """Linhas de aviso com o que o `sp-fechar` vai exigir e o SP ainda não tem (`gates:`, `## Decisões`); [] se estiver tudo."""
    achados = sp_list.encontrar(sp_list.collect(root, include_done=True), slug, project)
    if len(achados) != 1:
        return []
    texto = achados[0].path.read_text(encoding="utf-8")
    fm = sp_list.parse_frontmatter(texto)
    falta = []
    if not re.search(r"(?m)^gates:\s*$", texto.split("\n---", 2)[0]) and not fm.get("gates"):
        falta.append("`gates:` executáveis no frontmatter")
    if not re.search(r"(?m)^## Decisões\s*$", texto):
        falta.append("`## Decisões` (o grill registado)")
    return [f"aviso: o sp-fechar vai exigir {x}" for x in falta]


def aviso_diff(root, slug, project=None, run=subprocess.run):
    """Aviso se o SP tem diff por commitar (a worktree do michi nasce do HEAD e herdaria o SP vazio); [] se limpo, sem git ou sem SP."""
    achados = sp_list.encontrar(sp_list.collect(root, include_done=True), slug, project)
    if len(achados) != 1:
        return []
    caminho = achados[0].path
    try:
        dentro = run(["git", "-C", str(caminho.parent), "rev-parse", "--is-inside-work-tree"], capture_output=True)
        if dentro.returncode != 0:  # fora de um repo o `git diff` cairia em --no-index
            return []
        r = run(["git", "-C", str(caminho.parent), "diff", "--quiet", "HEAD", "--", caminho.name], capture_output=True)
    except OSError:
        return []
    if r.returncode != 1:  # 0 limpo; >1 fora de um repo git ou erro
        return []
    rel = caminho.relative_to(root).as_posix() if root and caminho.is_relative_to(Path(root)) else caminho.as_posix()
    return [f"aviso: o SP {rel} tem alterações por commitar; a worktree do michi nasce do HEAD e herda-o vazio: "
            f"git add \"{rel}\" && git commit -m 'vault: SP {slug}'"]


def _mover_doc(ap, args):
    """`--tipo dr|dp`: move um DR/DP."""
    if not args.slug or not args.dest or args.start or args.next or args.project:
        ap.error("--tipo dr|dp exige <slug> <todo|doing|done> e não aceita --start, --next nem --project")
    try:
        print(doc_ops.move(args.root or doc_ops.DEFAULT_ROOT, args.tipo, args.slug, args.dest))
    except doc_ops.DocMoveError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    return 0


def _executar(args):
    if args.start:
        if args.dest.lower() != "doing" or args.next:
            raise SpMoveError("--start não se combina com outro destino nem com --next")
        avisos_diff = aviso_diff(args.root, args.slug, args.project)  # antes de mover: o caminho é o de TODO
        print(start(args.root, args.slug, args.project))
        for linha in avisos_diff:
            print(linha, file=sys.stderr)
        for linha in avisos_fecho(args.root, args.slug, args.project):
            print(linha, file=sys.stderr)
    elif args.next:
        if args.dest.lower() != "done":
            raise SpMoveError(f"--next só se usa com 'done'; corre sp-move.py {args.slug} done --next")
        print(advance(args.root, args.slug, args.project))
    else:
        print(move(args.root, args.slug, args.dest, args.project))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Move um SP entre TODO, Doing e Done")
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--slug", dest="slug_opt", help="alias de slug posicional")
    ap.add_argument("dest", nargs="?", help="todo | doing | done")
    ap.add_argument("--project")
    ap.add_argument("--next", action="store_true", help="com done: abre o próximo filho elegível do programa")
    ap.add_argument("--start", action="store_true", help="arranque: move o SP e as mães em TODO para Doing")
    ap.add_argument("--tipo", choices=("sp", *doc_ops.TYPES), default="sp", help="sp (predefinido) | dr | dp: move um DR/DP")
    ap.add_argument("--root", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.tipo != "sp":
        return _mover_doc(ap, args)
    args.root = args.root or str(sp_list.DEFAULT_ROOT)
    if args.slug_opt:
        args.slug, args.dest = args.slug_opt, args.dest or args.slug
    if args.start and not args.dest:
        args.dest = "doing"
    if not args.slug or not args.dest:
        ap.error("falta o slug (posicional ou --slug); ver scripts/sp-list.py")
    args.slug = sp_list.normalize_ref(args.root, args.slug)
    if argv is None and args.root == str(sp_list.DEFAULT_ROOT):
        rc = wt_redirect.redirect(__file__, args.slug, sys.argv[1:])
        if rc is not None:
            return rc
    try:
        _executar(args)
    except SpMoveError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    import kf_errlog
    sys.exit(kf_errlog.executar("sp-move", main))
