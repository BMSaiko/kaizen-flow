#!/usr/bin/env python3
"""Cria um Super Prompt vazio (frontmatter + 8 secções) em <projeto>/sp/TODO/.

As secções ficam vazias de propósito: `sp-validate.py` aponta o que falta preencher.
Recusa slug já existente no projeto (em qualquer pasta) e projeto inexistente.
Nunca faz commit.

Uso:
  python -I scripts/sp-new.py --project <nome> --slug <slug> --priority P1|P2|P3 [--modo auto|manual] [--commit|--push|--pr auto|pergunta|nunca] [--restricoes "<texto>"] [--gate "<cmd>" ...] [--prova "<cmd>"] [--permitir "<cmd>" ...] [--decisao "<texto>" ...] [--parent <slug>] [--depends-on <slug> ...]
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_hooks  # noqa: E402

_spec = importlib.util.spec_from_file_location("sp_list", Path(__file__).with_name("sp-list.py"))
sp_list = importlib.util.module_from_spec(_spec)
sys.modules["sp_list"] = sp_list
_spec.loader.exec_module(sp_list)

_gspec = importlib.util.spec_from_file_location("sp_gates", Path(__file__).with_name("sp-gates.py"))
sp_gates = importlib.util.module_from_spec(_gspec)
sys.modules["sp_gates"] = sp_gates
_gspec.loader.exec_module(sp_gates)

SECTIONS = (
    "1. Role", "2. Context", "3. Objective (single sentence)", "4. Success criteria (verifiable)",
    "5. Constraints / invariants", "6. Seams (public interfaces to test / change)",
    "7. Steps (numbered, ordered)", "8. Done-when",
)
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


AUTH_VALUES = ("auto", "pergunta", "nunca")
PERFIS = ("cauteloso", "normal", "autonomo")
PARAR_SE = ("gate-falha", "ambiguidade", "ficheiro-fora-de-escopo", "custo")


class SpNewError(Exception):
    pass


def check_auth(auth):
    """`auth`: dict opcional commit/push/pr/restricoes; valida valores e dependências."""
    auth = {k: v for k, v in (auth or {}).items() if v is not None}
    for key in ("commit", "push", "pr"):
        if key in auth and auth[key] not in AUTH_VALUES:
            raise SpNewError(f"{key} inválido '{auth[key]}' ({'|'.join(AUTH_VALUES)})")
    if "restricoes" in auth and any(c in auth["restricoes"] for c in ("\n", "\r")):
        raise SpNewError("restricoes tem de ser uma só linha")
    if auth.get("push") == "auto" and auth.get("commit") == "nunca":
        raise SpNewError("push auto exige commit ≠ nunca")
    if auth.get("pr") == "auto" and auth.get("push") != "auto":
        raise SpNewError("pr auto exige push auto")
    return auth


def check_perfil(perfil, gates=()):
    """`perfil`: dict opcional perfil/max_tentativas/max_requests/parar_se (lista); valida valores."""
    perfil = {k: v for k, v in (perfil or {}).items() if v is not None}
    if "perfil" in perfil and perfil["perfil"] not in PERFIS:
        raise SpNewError(f"perfil inválido '{perfil['perfil']}' ({'|'.join(PERFIS)})")
    for key in ("max_tentativas", "max_requests"):
        if key in perfil and (not isinstance(perfil[key], int) or perfil[key] < 1):
            raise SpNewError(f"{key} tem de ser um inteiro ≥ 1")
    bad = [x for x in perfil.get("parar_se", []) if x not in PARAR_SE]
    if bad:
        raise SpNewError(f"parar_se inválido {bad} ({'|'.join(PARAR_SE)})")
    if perfil.get("perfil") == "autonomo" and not gates:
        raise SpNewError("perfil autonomo exige gates")
    return perfil


def check_escopo(escopo, fora):
    """Globs do escopo: não vazios, sem `..`, sem vírgulas/colchetes (vão em lista inline)."""
    for g in list(escopo) + list(fora):
        if not g.strip() or ".." in g.replace("\\", "/").split("/") or any(c in g for c in ",[]"):
            raise SpNewError(f"glob de escopo inválido '{g}'")
    if fora and not escopo:
        raise SpNewError("fora_de_escopo exige escopo")
    return [g.strip() for g in escopo], [g.strip() for g in fora]


def check_gates(gates, prova):
    """`gates`: comandos do frontmatter; `prova`: comando/critério. Uma linha cada, sem proibidos."""
    for cmd in [*gates, prova or ""]:
        if "\n" in cmd or "\r" in cmd:
            raise SpNewError("gates e prova têm de ser uma só linha")
    found = sp_gates.problems([{"cmd": c} for c in gates])
    if prova is not None and not prova.strip():
        found.append("prova vazia")
    elif prova and sp_gates.forbidden(prova):
        found.append(f"prova proibida ({sp_gates.forbidden(prova)}): {prova}")
    if found:
        raise SpNewError("; ".join(found))


def check(root, project, slug, priority, modo="manual"):
    if not SLUG_RE.fullmatch(slug):
        raise SpNewError(f"slug inválido '{slug}' (minúsculas, dígitos e hífens)")
    if priority not in ("P1", "P2", "P3"):
        raise SpNewError(f"prioridade inválida '{priority}' (P1|P2|P3)")
    if modo not in ("auto", "manual"):
        raise SpNewError(f"modo inválido '{modo}' (auto|manual)")
    if not (root / project).is_dir():
        raise SpNewError(f"projeto '{project}' não existe em {root}")
    if any(sp.slug == slug and sp.project == project for sp in sp_list.collect(root, include_done=True)):
        raise SpNewError(f"SP '{slug}' já existe no projeto '{project}'")


def check_permitir(permitir):
    """Cada comando da allowlist: uma só linha, sem `;` e não proibido (irreversíveis perguntam sempre)."""
    for cmd in permitir:
        if not cmd.strip() or any(c in cmd for c in ("\n", "\r", ";")):
            raise SpNewError(f"permitir inválido (uma linha, sem ';'): {cmd!r}")
        if sp_gates.forbidden(cmd):
            raise SpNewError(f"permitir proibido ({sp_gates.forbidden(cmd)}): {cmd}")


def create(root, project, slug, priority, today, parent=None, depends_on=(), extra=(), modo="manual", auth=None, gates=(), prova=None, perfil=None, escopo=(), fora_de_escopo=(), permitir=(), decisoes=()):
    root = Path(root)
    check(root, project, slug, priority, modo)
    auth = check_auth(auth)
    check_gates(list(gates), prova)
    check_permitir(list(permitir))
    perfil = check_perfil(perfil, gates)
    escopo, fora_de_escopo = check_escopo(escopo, fora_de_escopo)
    stamp = f"{today.isoformat()}T00:00:00Z"
    head = [
        "---", "status: TODO", f"created: {stamp}", f"updated: {stamp}", "phase: SP",
        f"slug: {slug}", f"date: {today.isoformat()}", f"project: {project}", f"priority: {priority}",
        f"modo: {modo}",
    ]
    head += [f"{k}: {auth[k]}" for k in ("commit", "push", "pr", "restricoes") if k in auth]
    head += [f"{k}: {perfil[k]}" for k in ("perfil", "max_tentativas", "max_requests") if k in perfil]
    if "parar_se" in perfil:
        head.append(f"parar_se: [{', '.join(perfil['parar_se'])}]")
    if escopo:
        head.append(f"escopo: [{', '.join(escopo)}]")
    if fora_de_escopo:
        head.append(f"fora_de_escopo: [{', '.join(fora_de_escopo)}]")
    if gates:
        head.append("gates:")
        head += [f"  - cmd: {g.strip()}" for g in gates]
    if permitir:
        head.append("permitir: " + "; ".join(c.strip() for c in permitir))
    if prova is not None:
        head.append(f"prova: {prova.strip()}")
    head += extra
    if parent:
        head.append(f"parent: {parent}")
    if depends_on:
        head.append(f"depends_on: [{', '.join(depends_on)}]")
    head.append("---")
    body = [f"# Super Prompt - {slug} ({today.isoformat()})", ""]
    for title in SECTIONS:
        body += [f"## {title}", "", ""]
    if decisoes:
        body += ["## Decisões", ""] + [f"- {d.strip()}" for d in decisoes] + [""]
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


def create_program(root, project, slug, priority, today, children, modo="manual", auth=None):
    root = Path(root)
    auth = check_auth(auth)
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
        check(root, project, name, priority, modo)
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
    paths = [create(root, project, slug, priority, today, extra=extra, modo=modo, auth=auth)]
    for name, deps in children:
        paths.append(create(root, project, name, priority, today, parent=slug, depends_on=deps, modo=modo, auth=auth))
    return paths


def split(value):
    return [x.strip() for x in value.split(",") if x.strip()] if value else []


def main(argv=None):
    ap = argparse.ArgumentParser(description="Cria um SP vazio em sp/TODO")
    ap.add_argument("--project", required=True)
    ap.add_argument("--slug")
    ap.add_argument("--program", metavar="SLUG", help="cria um SP-mãe com os filhos de --children")
    ap.add_argument("--children", help="a,b:a,c:a+b (b depende de a; c de a e b)")
    ap.add_argument("--priority", required=True)
    ap.add_argument("--modo", default="manual", help="modo do michi: auto|manual (defeito manual)")
    ap.add_argument("--commit", help="commit: auto|pergunta|nunca")
    ap.add_argument("--push", help="push: auto|pergunta|nunca")
    ap.add_argument("--pr", help="pr: auto|pergunta|nunca")
    ap.add_argument("--restricoes", help="restrições extra do SP (uma linha)")
    ap.add_argument("--gate", action="append", default=[], help="gate executável (repetível), corrido por sp-gates.py")
    ap.add_argument("--prova", help="comando ou critério verificável da prova")
    ap.add_argument("--permitir", action="append", default=[], help="comando pré-aprovado (repetível; irreversíveis são recusados)")
    ap.add_argument("--decisao", action="append", default=[], help="decisão do grill (repetível), vai para ## Decisões")
    ap.add_argument("--perfil", help="perfil de execução: cauteloso|normal|autonomo")
    ap.add_argument("--max-tentativas", type=int, help="tentativas por gate (override do perfil)")
    ap.add_argument("--max-requests", type=int, help="máximo de pedidos (override do perfil)")
    ap.add_argument("--parar-se", help="lista separada por vírgulas: gate-falha,ambiguidade,ficheiro-fora-de-escopo,custo")
    ap.add_argument("--escopo", help="globs permitidos, separados por vírgulas (guard-escopo.js)")
    ap.add_argument("--fora-de-escopo", help="globs negados, separados por vírgulas")
    ap.add_argument("--parent")
    ap.add_argument("--depends-on", nargs="*", default=[])
    ap.add_argument("--root", default=str(sp_list.DEFAULT_ROOT), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    auth = {"commit": args.commit, "push": args.push, "pr": args.pr, "restricoes": args.restricoes}
    perfil = {"perfil": args.perfil, "max_tentativas": args.max_tentativas, "max_requests": args.max_requests,
              "parar_se": [x.strip() for x in args.parar_se.split(",") if x.strip()] if args.parar_se else None}
    try:
        if args.program:
            if not args.children:
                raise SpNewError("--program exige --children")
            paths = create_program(args.root, args.project, args.program, args.priority, date.today(),
                                   parse_children(args.children), args.modo, auth)
            print("\n".join(str(p) for p in paths))
        elif args.slug:
            check_links(args.root, args.project, args.parent, args.depends_on)
            print(create(args.root, args.project, args.slug, args.priority, date.today(), args.parent, args.depends_on, modo=args.modo, auth=auth, gates=args.gate, prova=args.prova, perfil=perfil, escopo=split(args.escopo), fora_de_escopo=split(args.fora_de_escopo), permitir=args.permitir, decisoes=args.decisao))
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
