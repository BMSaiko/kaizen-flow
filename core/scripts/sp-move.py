#!/usr/bin/env python3
"""Move um Super Prompt entre sp/TODO, sp/Doing e sp/Done e atualiza o frontmatter.

Troca a pasta e os campos `status` e `updated`; o resto do ficheiro fica intacto.
Nunca faz commit. Usa `git mv` se o SP estiver tracked, senão renomeia.

Uso:
  python -I scripts/sp-move.py <slug> <todo|doing|done> [--project <nome>]
  python -I scripts/sp-move.py <filho> done --next   # programa: abre o próximo filho elegível; a mãe nunca é movida
"""
import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
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


def _relocate(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    tracked = subprocess.run(
        ["git", "-C", str(src.parent), "ls-files", "--error-unmatch", src.name],
        capture_output=True,
    ).returncode == 0
    if tracked:
        subprocess.run(["git", "-C", str(src.parent), "mv", str(src), str(dst)], check=True, capture_output=True)
    else:
        src.rename(dst)


def _move_proofs(sp, dst):
    """Leva as provas `proofs/<slug>-*` do SP para a pasta de destino."""
    src_dir = sp.path.parent / "proofs"
    files = sorted(src_dir.glob(f"{sp.slug}-*")) if src_dir.is_dir() else []
    for f in files:
        _relocate(f, dst.parent / "proofs" / f.name)
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


def move(root, slug, dest, project=None):
    if dest.lower() not in DESTS:
        raise SpMoveError(f"destino inválido '{dest}' (todo|doing|done)")
    target = DESTS[dest.lower()]
    matches = [sp for sp in sp_list.collect(root, include_done=True) if sp.slug == slug]
    if project:
        matches = [sp for sp in matches if sp.project == project]
    if not matches:
        raise SpMoveError(f"SP '{slug}' não encontrado")
    if len(matches) > 1:
        opts = ", ".join(f"{sp.project} ({sp.status})" for sp in matches)
        raise SpMoveError(f"SP '{slug}' ambíguo: {opts}; usar --project")
    sp = matches[0]
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
    _relocate(sp.path, dst)
    dst.write_bytes(new_raw)
    n = _move_proofs(sp, dst)
    if target == "Done":
        _agent_claim(slug, target)
    extra = f" (+{n} provas)" if n else ""
    if target == "Done" and sp_metricas:
        try:
            if sp_metricas.registar(root, dst, sp.project):
                extra += " (+métricas)"
        except Exception as exc:  # métricas nunca bloqueiam o fecho
            extra += f" (métricas falharam: {exc})"
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


def main(argv=None):
    ap = argparse.ArgumentParser(description="Move um SP entre TODO, Doing e Done")
    ap.add_argument("slug")
    ap.add_argument("dest", help="todo | doing | done")
    ap.add_argument("--project")
    ap.add_argument("--next", action="store_true", help="com done: abre o próximo filho elegível do programa")
    ap.add_argument("--root", default=str(sp_list.DEFAULT_ROOT), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if argv is None and args.root == str(sp_list.DEFAULT_ROOT):
        rc = wt_redirect.redirect(__file__, args.slug, sys.argv[1:])
        if rc is not None:
            return rc
    try:
        if args.next:
            if args.dest.lower() != "done":
                raise SpMoveError("--next só se usa com 'done'")
            print(advance(args.root, args.slug, args.project))
        else:
            print(move(args.root, args.slug, args.dest, args.project))
    except SpMoveError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
