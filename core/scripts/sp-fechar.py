#!/usr/bin/env python3
"""Fecha um SP numa só chamada: gates -> context-budget -> sp-move done -> COMMIT_*.md.

Pára sem mover o SP se um gate (ou o orçamento de contexto) falhar. Nunca faz commit nem push.
O COMMIT_*.md lista o stage explícito (um `git add` por caminho, sem o próprio COMMIT_*.md).

Uso:
  python -I scripts/sp-fechar.py <slug> [--project P] [--next] [--msg "assunto"]
                                 [--sem-budget] [--sem-commit] [--commit-dir DIR]
RC 0 = fechado; 1 = gate/orçamento vermelho (SP fica em Doing); 2 = erro de uso.
"""
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402

sp_list = kaizen_engine.load("sp-list")
sp_gates = kaizen_engine.load("sp-gates")
sp_move = kaizen_engine.load("sp-move")

HERE = Path(__file__).resolve().parent
SECRETS = (".env", ".key", ".pem", ".p12", ".pfx", "id_rsa", ".kdbx", "secrets.", ".secrets")


class FecharError(Exception):
    pass


def find_doing(root, slug, project=None):
    found = [sp for sp in sp_list.collect(root, include_done=True)
             if sp.slug == slug and (not project or sp.project == project)]
    if not found:
        raise FecharError(f"SP '{slug}' não encontrado")
    if len(found) > 1:
        raise FecharError(f"SP '{slug}' ambíguo; usar --project")
    if found[0].status != "Doing":
        raise FecharError(f"SP '{slug}' está em {found[0].status}, não em Doing")
    return found[0]


def run_gates(sp):
    """Devolve (rc, texto). rc 0 = verdes ou sem gates."""
    gates = sp_gates.parse_gates(sp.path.read_text(encoding="utf-8"))
    if not gates:
        return 0, "gates: nenhum declarado"
    bad = sp_gates.problems(gates)
    if bad:
        return 2, "\n".join(bad)
    results = sp_gates.run(gates)
    ok = all(r["rc"] == 0 for r in results) and len(results) == len(gates)
    return (0 if ok else 1), sp_gates.summary(results)


def run_budget():
    # opcional: o pacote kaizen-flow não leva o script do orçamento (glob evita referência dura)
    script = next(iter(HERE.glob("context-budg*.py")), None)
    if script is None:
        return 0, "context-budget: ausente (ignorado)"
    r = subprocess.run([sys.executable, "-I", str(script)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-3:])
    return r.returncode, f"context-budget rc={r.returncode}\n{tail}"


def changed_paths(cwd):
    """Caminhos alterados/novos segundo o git, sem COMMIT_*.md nem segredos. Vazio fora de repo git."""
    r = subprocess.run(["git", "-C", str(cwd), "status", "--porcelain", "-uall"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return []
    paths = []
    for line in r.stdout.splitlines():
        p = line[3:].split(" -> ")[-1].strip().strip('"')
        name = Path(p).name
        if name.startswith("COMMIT_") or any(s in name for s in SECRETS):
            continue
        paths.append(p)
    return sorted(set(paths))


def write_commit(cwd, slug, subject, paths):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(cwd) / f"COMMIT_{stamp}.md"
    stage = "\n".join(f"git add {p}" for p in paths)
    out.write_text(
        f"## Mensagem\n\n```\n{subject}\n\nFecha o SP {slug} (gates verdes, sp-fechar.py).\n```\n\n"
        f"## Stage\n\n```\n{stage}\n```\n\n"
        f"## Fora do commit\n\nNada além do que o git status mostrava; rever antes de confirmar.\n",
        encoding="utf-8")
    return out


def fechar(root, slug, project=None, nxt=False, msg=None, budget=True, commit=True, commit_dir="."):
    """Corre o fecho. Devolve (rc, linhas)."""
    sp = find_doing(root, slug, project)
    lines = []
    rc, text = run_gates(sp)
    lines.append(text)
    if rc:
        return rc, lines + [f"{slug}: gate vermelho, SP continua em Doing"]
    if budget:
        rc, text = run_budget()
        lines.append(text)
        if rc:
            return 1, lines + [f"{slug}: orçamento de contexto excedido, SP continua em Doing"]
    if nxt:
        lines.append(sp_move.advance(root, slug, sp.project))
    else:
        lines.append(sp_move.move(root, slug, "done", sp.project))
    if commit:
        paths = changed_paths(commit_dir)
        if paths:
            lines.append(f"COMMIT: {write_commit(commit_dir, slug, msg or f'vault: fecha {slug}', paths)}")
        else:
            lines.append("COMMIT: nada para stage (sem alterações ou fora de repo git)")
    return 0, lines


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fecha um SP: gates, orçamento, Done e COMMIT_*.md")
    ap.add_argument("slug")
    ap.add_argument("--project")
    ap.add_argument("--next", action="store_true", help="abre o próximo filho elegível do programa")
    ap.add_argument("--msg", help="assunto do commit (defeito: vault: fecha <slug>)")
    ap.add_argument("--sem-budget", action="store_true")
    ap.add_argument("--sem-commit", action="store_true")
    ap.add_argument("--commit-dir", default=".", help="repo onde gerar o COMMIT_*.md (defeito: cwd)")
    ap.add_argument("--root", default=str(sp_list.DEFAULT_ROOT), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    try:
        rc, lines = fechar(args.root, args.slug, args.project, args.next, args.msg,
                           not args.sem_budget, not args.sem_commit, args.commit_dir)
    except (FecharError, sp_move.SpMoveError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return rc


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
