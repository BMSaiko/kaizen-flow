#!/usr/bin/env python3
"""Cria um Super Prompt vazio (frontmatter + 8 secções) em <projeto>/sp/TODO/.

As secções ficam vazias de propósito: `sp-validate.py` aponta o que falta preencher.
Recusa slug já existente no projeto (em qualquer pasta) e projeto inexistente.
Nunca faz commit.

Uso:
  python -I scripts/sp-new.py --project <nome> --slug <slug> --priority P1|P2|P3 [--parent <slug>] [--depends-on <slug> ...]
  python -I scripts/sp-new.py --project <nome> --program <slug> --children a,b:a,c:a+b --priority P1|P2|P3

`--program` cria o SP-mãe (`kind: program`, `children:`) e os filhos (`parent`, `depends_on`) em sp/TODO/.
Em `--children`, `b:a` = b depende de a; `c:a+b` = c depende de a e b. Valida tudo antes de escrever.
"""
import argparse
import importlib.util
import re
import sys
from datetime import date
from pathlib import Path

_spec = importlib.util.spec_from_file_location("sp_list", Path(__file__).with_name("sp-list.py"))
sp_list = importlib.util.module_from_spec(_spec)
sys.modules["sp_list"] = sp_list
_spec.loader.exec_module(sp_list)

SECTIONS = (
    "1. Role", "2. Context", "3. Objective (single sentence)", "4. Success criteria (verifiable)",
    "5. Constraints / invariants", "6. Seams (public interfaces to test / change)",
    "7. Steps (numbered, ordered)", "8. Done-when",
)
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class SpNewError(Exception):
    pass


def check(root, project, slug, priority):
    if not SLUG_RE.fullmatch(slug):
        raise SpNewError(f"slug inválido '{slug}' (minúsculas, dígitos e hífens)")
    if priority not in ("P1", "P2", "P3"):
        raise SpNewError(f"prioridade inválida '{priority}' (P1|P2|P3)")
    if not (root / project).is_dir():
        raise SpNewError(f"projeto '{project}' não existe em {root}")
    if any(sp.slug == slug and sp.project == project for sp in sp_list.collect(root, include_done=True)):
        raise SpNewError(f"SP '{slug}' já existe no projeto '{project}'")


def create(root, project, slug, priority, today, parent=None, depends_on=(), extra=()):
    root = Path(root)
    check(root, project, slug, priority)
    stamp = f"{today.isoformat()}T00:00:00Z"
    head = [
        "---", "status: TODO", f"created: {stamp}", f"updated: {stamp}", "phase: SP",
        f"slug: {slug}", f"date: {today.isoformat()}", f"project: {project}", f"priority: {priority}",
    ]
    head += extra
    if parent:
        head.append(f"parent: {parent}")
    if depends_on:
        head.append(f"depends_on: [{', '.join(depends_on)}]")
    head.append("---")
    body = [f"# Super Prompt - {slug} ({today.isoformat()})", ""]
    for title in SECTIONS:
        body += [f"## {title}", "", ""]
    path = root / project / "sp" / "TODO" / f"{slug}-{today.isoformat()}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(head + body), encoding="utf-8")
    return path


def check_links(root, project, parent, depends_on):
    """CLI de SP avulso: `parent` e `depends_on` têm de ser slugs válidos de SPs existentes no projeto."""
    known = {sp.slug for sp in sp_list.collect(root, include_done=True) if sp.project == project}
    for link in [l for l in [parent, *depends_on] if l]:
        if not SLUG_RE.fullmatch(link):
            raise SpNewError(f"slug inválido '{link!r}' em --parent/--depends-on")
        if link not in known:
            raise SpNewError(f"'{link}' não existe no projeto '{project}'")


def parse_children(text):
    children = []
    for item in text.split(","):
        slug, _, deps = item.strip().partition(":")
        children.append((slug, [d for d in deps.split("+") if d]))
    return children


def create_program(root, project, slug, priority, today, children):
    root = Path(root)
    names = [name for name, _ in children]
    if not children:
        raise SpNewError("programa sem filhos (--children)")
    if len(set(names)) != len(names):
        raise SpNewError("filho repetido em --children")
    for name, deps in children:
        for dep in deps:
            if dep not in names:
                raise SpNewError(f"'{name}' depende de '{dep}', que não é filho do programa")
    if slug in names:
        raise SpNewError(f"o programa '{slug}' não pode ser filho de si próprio")
    for name in [slug, *names]:
        check(root, project, name, priority)
    graph = dict(children)
    for name in names:
        seen, stack = set(), [name]
        while stack:
            for dep in graph[stack.pop()]:
                if dep == name:
                    raise SpNewError(f"dependências cíclicas em '{name}'")
                if dep not in seen:
                    seen.add(dep)
                    stack.append(dep)
    extra = ["kind: program", "children:"]
    for name, deps in children:
        extra += [f"  - slug: {name}", f"    depends_on: [{', '.join(deps)}]", "    state: TODO"]
    paths = [create(root, project, slug, priority, today, extra=extra)]
    for name, deps in children:
        paths.append(create(root, project, name, priority, today, parent=slug, depends_on=deps))
    return paths


def main(argv=None):
    ap = argparse.ArgumentParser(description="Cria um SP vazio em sp/TODO")
    ap.add_argument("--project", required=True)
    ap.add_argument("--slug")
    ap.add_argument("--program", metavar="SLUG", help="cria um SP-mãe com os filhos de --children")
    ap.add_argument("--children", help="a,b:a,c:a+b (b depende de a; c de a e b)")
    ap.add_argument("--priority", required=True)
    ap.add_argument("--parent")
    ap.add_argument("--depends-on", nargs="*", default=[])
    ap.add_argument("--root", default=str(sp_list.DEFAULT_ROOT), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    try:
        if args.program:
            if not args.children:
                raise SpNewError("--program exige --children")
            paths = create_program(args.root, args.project, args.program, args.priority, date.today(),
                                   parse_children(args.children))
            print("\n".join(str(p) for p in paths))
        elif args.slug:
            check_links(args.root, args.project, args.parent, args.depends_on)
            print(create(args.root, args.project, args.slug, args.priority, date.today(), args.parent, args.depends_on))
        else:
            raise SpNewError("indicar --slug (ou --program com --children)")
    except SpNewError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
