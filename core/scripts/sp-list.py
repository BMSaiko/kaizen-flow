#!/usr/bin/env python3
"""Lista os Super Prompts pendentes (TODO e Doing) do vault. Só leitura.

A pasta (TODO/ ou Doing/) é a fonte de verdade do estado; Done/ só com --all e
arquivo/ é sempre ignorada.

Uso:
  python -I scripts/sp-list.py                      # Doing antes de TODO, P1->P3, mais antigo primeiro
  python -I scripts/sp-list.py --sort priority      # priority | created | status
  python -I scripts/sp-list.py --reverse
  python -I scripts/sp-list.py --project atlas
  python -I scripts/sp-list.py --status doing       # todo | doing
  python -I scripts/sp-list.py --all                # inclui Done
  python -I scripts/sp-list.py --flat               # tabela plana (sem agrupar programas)
  python -I scripts/sp-list.py --tudo               # sem limite de 40 linhas (predefinido)
  # por omissão: programas agrupados (filhos sob o SP-mãe, com dependências por cumprir); --tree é sinónimo

Um programa é um SP-mãe (`kind: program`) com filhos que têm `parent: <slug-mãe>` e, opcionalmente,
`depends_on: [a, b]`. O estado de cada filho vem da pasta; dependências por cumprir só avisam.

Cabeçalho `Próximo:`/`Bloqueados` (`eligibility`) e limite de 40 linhas (`--tudo` levanta-o).

Fronteira com os vizinhos (não duplicar): `sp-list` = visão do conjunto de SPs (todos os projetos, árvore,
próximo elegível); `sp-estado.py` = um SP (passos, gates, git); `sp-painel.py` = sessões paralelas do sp-fila; `sp-organize.py` =
detetar/corrigir SPs fora do padrão; `sp-metricas.py` = linha de métricas por SP fechado. Aqui só leitura.
"""
import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402

_kc = kaizen_engine.load("kaizen_config")
REPO = Path(__file__).resolve().parent.parent


def default_root(repo=REPO):
    return _kc.sp_root(repo)


DEFAULT_ROOT = default_root()
FOLDERS = ("TODO", "Doing", "Done")
STATUS_ORDER = {"Doing": 0, "TODO": 1, "Done": 2}
DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


@dataclass
class Sp:
    slug: str
    status: str
    priority: str
    created: "date | None"
    project: str
    warning: str
    path: Path
    parent: str = ""
    depends_on: list = field(default_factory=list)
    kind: str = ""


parse_frontmatter = kaizen_engine.parse_frontmatter
parse_list = kaizen_engine.parse_list


def parse_date(value):
    m = DATE_RE.search(value or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def collect(root, include_done=False):
    folders = FOLDERS if include_done else FOLDERS[:2]
    sps = []
    for path in sorted(Path(root).rglob("*.md")):
        parts = path.relative_to(root).parts
        if "arquivo" in parts or len(parts) < 3 or parts[-3] != "sp" or parts[-2] not in folders:
            continue
        if path.name == "MOC.md":
            continue
        try:
            fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            print(f"aviso: {path.name} ignorado ({exc.__class__.__name__})", file=sys.stderr)
            continue
        folder = parts[-2]
        warning = "⚠ status≠pasta" if fm.get("status") and fm["status"] != folder else ""
        priority = fm.get("priority", "").upper()
        sps.append(Sp(
            slug=fm.get("slug") or path.stem,
            status=folder,
            priority=priority if priority in ("P1", "P2", "P3") else "P3",
            created=parse_date(fm.get("created")),
            project=fm.get("project") or "-",
            warning=warning,
            path=path,
            parent=fm.get("parent", ""),
            depends_on=parse_list(fm.get("depends_on")),
            kind=fm.get("kind", ""),
        ))
    return sps


def sort_sps(sps, key="status", reverse=False):
    def created_key(sp):
        return (sp.created is None, sp.created or date.min)

    keys = {
        "status": lambda sp: (STATUS_ORDER[sp.status], sp.priority, created_key(sp)),
        "priority": lambda sp: (sp.priority, STATUS_ORDER[sp.status], created_key(sp)),
        "created": lambda sp: (created_key(sp), STATUS_ORDER[sp.status], sp.priority),
    }
    return sorted(sps, key=keys[key], reverse=reverse)


def render(sps):
    today = date.today()
    rows = [("#", "Estado", "Prio", "Criado", "Projeto", "Slug")]
    for i, sp in enumerate(sps, 1):
        criado = f"{sp.created} ({(today - sp.created).days}d)" if sp.created else "?"
        slug = f"{sp.slug} {sp.warning}".strip()
        rows.append((str(i), sp.status, sp.priority, criado, sp.project, slug))
    widths = [max(len(r[c]) for r in rows) for c in range(6)]
    return "\n".join(" ".join(cell.ljust(widths[c]) for c, cell in enumerate(r)).rstrip() for r in rows)


def build_tree(sps):
    """Agrupa por `parent`. `sps` deve incluir Done (para saber que dependências estão cumpridas).

    Devolve ([(mãe, [(filho, dependências_por_cumprir)])], soltos). Função pura, sem FS.
    """
    done = {(sp.project, sp.slug) for sp in sps if sp.status == "Done"}
    mothers = {(sp.project, sp.slug): sp for sp in sps if sp.kind == "program"}
    mothers.update({(sp.project, sp.parent): next((m for m in sps if m.project == sp.project and m.slug == sp.parent), None)
                    for sp in sps if sp.parent})
    by_slug = {(sp.project, sp.slug): sp for sp in sps}

    def depth(sp, seen=()):
        if sp.slug in seen:
            return 0
        return 1 + max((depth(by_slug[(sp.project, d)], seen + (sp.slug,)) for d in sp.depends_on
                        if (sp.project, d) in by_slug), default=-1)

    def unmet(sp):
        return [d for d in sp.depends_on if (sp.project, d) not in done]

    groups, used = [], set()
    for key, mother in sorted(mothers.items(), key=lambda kv: kv[0]):
        if mother is None:
            continue
        kids = sorted((sp for sp in sps if sp.project == mother.project and sp.parent == mother.slug
                             and sp.slug != mother.slug),
                      key=lambda sp: (depth(sp), sp.created is None, sp.created or date.min, sp.slug))
        groups.append((mother, [(sp, unmet(sp)) for sp in kids]))
        used.update({(mother.project, mother.slug), *((sp.project, sp.slug) for sp in kids)})
    loose = [sp for sp in sps if (sp.project, sp.slug) not in used]
    return groups, loose


ICONS = {"Doing": "▶", "TODO": "○", "Done": "✔"}


def fmt_created(sp):
    return f"{sp.created} ({(date.today() - sp.created).days}d)" if sp.created else "?"


def _color():
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ or "FORCE_COLOR" in os.environ


def paint(text, *codes):
    return f"[{';'.join(codes)}m{text}[0m" if codes and _color() else text


STATUS_STYLE = {"Doing": ("1", "32"), "TODO": (), "Done": ("2",)}
PRIO_STYLE = {"P1": ("1", "31"), "P2": ("33",), "P3": ("2",)}


def bar(feitos, total, width=10):
    n = round(width * feitos / total) if total else 0
    return "▰" * n + "▱" * (width - n)


def short_unmet(unmet, keep=2):
    return ", ".join(unmet[:keep]) + (f" +{len(unmet) - keep}" if len(unmet) > keep else "")


def render_tree(groups, loose, visible):
    """Vista agrupada: mãe com progresso e filhos sob `├─`/`└─`; SPs soltos no fim. Colunas alinhadas."""
    rows = []  # (ícone, estado, prio, rótulo, criado, projeto, nota)
    for mother, kids in groups:
        shown = [(sp, unmet) for sp, unmet in kids if visible(sp)]
        if not shown and not visible(mother):
            continue
        feitos = sum(sp.status == "Done" for sp, _ in kids)
        nota = f"{bar(feitos, len(kids))} {feitos}/{len(kids)} feitos"
        if kids and feitos == len(kids) and mother.status != "Done":
            nota += " · pronto para fechar"
        if rows:
            rows.append(None)
        rows.append((ICONS[mother.status], mother.status, mother.priority, mother.slug, fmt_created(mother), mother.project, nota))
        for i, (sp, unmet) in enumerate(shown):
            ramo = "└─" if i == len(shown) - 1 else "├─"
            nota = f"aguarda: {short_unmet(unmet)}" if unmet and sp.status != "Done" else ""
            rows.append((ICONS[sp.status], sp.status, sp.priority, f"{ramo} {sp.slug}", fmt_created(sp), "", nota))
    if loose and rows and rows[-1] is not None:
        rows.append(None)
    rows += [(ICONS[sp.status], sp.status, sp.priority, sp.slug, fmt_created(sp), sp.project, sp.warning) for sp in loose if visible(sp)]
    if rows and rows[-1] is None:
        rows.pop()
    real = [r for r in rows if r]
    if not real:
        return ""
    w_slug = max(len(r[3]) for r in real)
    w_date = max(len(r[4]) for r in real)
    w_proj = max(len(r[5]) for r in real)
    lines = []
    for r in rows:
        if r is None:
            lines.append("")
            continue
        icon, status, prio, label, created, proj, nota = r
        mae = not label.startswith(("├─", "└─")) and bool(proj) and nota.endswith("feitos") or "pronto para fechar" in nota
        lines.append("  ".join([
            paint(f"{icon} {status:<5}", *STATUS_STYLE[status]),
            paint(prio, *PRIO_STYLE.get(prio, ())),
            paint(f"{label:<{w_slug}}", *(("1",) if mae else ())),
            paint(f"{created:<{w_date}}", "2"),
            paint(f"{proj:<{w_proj}}", "36"),
            paint(nota, "2") if nota.startswith("aguarda") else nota,
        ]).rstrip())
    return "\n".join(lines)


def eligibility(sps):
    """Elegíveis e bloqueados entre os SPs pendentes. `sps` inclui Done (dependências cumpridas).

    Elegível = TODO/Doing, não-mãe (`kind: program` é só agrupador) e com todas as `depends_on` em Done
    (mesmo projeto). Bloqueado = o resto, com as dependências em falta (inexistentes também contam).
    Ordem: Doing antes de TODO, P1->P3, mais antigo primeiro. Função pura, sem FS.
    """
    done = {(sp.project, sp.slug) for sp in sps if sp.status == "Done"}
    pending = [sp for sp in sort_sps(sps) if sp.status != "Done" and sp.kind != "program"]
    eligible, blocked = [], []
    for sp in pending:
        unmet = [d for d in sp.depends_on if (sp.project, d) not in done]
        (blocked.append((sp, unmet)) if unmet else eligible.append(sp))
    return eligible, blocked


MAX_LINES = 40
MAX_BLOCKED = 5


def next_block(sps, tudo=False):
    """Linhas de cabeçalho: próximo SP elegível e bloqueados com a dependência em falta."""
    eligible, blocked = eligibility(sps)
    if not eligible and not blocked:
        return []
    if eligible:
        sp = eligible[0]
        lines = [f"Próximo: {sp.slug} ({ICONS[sp.status]} {sp.status}, {sp.priority}, {sp.project})"]
    else:
        lines = ["Próximo: nenhum elegível"]
    if blocked:
        lines.append(f"Bloqueados ({len(blocked)}):")
        shown = blocked if tudo else blocked[:MAX_BLOCKED]
        lines += [f"  {sp.slug} ← {', '.join(unmet)}" for sp, unmet in shown]
        if len(shown) < len(blocked):
            lines.append(f"  … +{len(blocked) - len(shown)} (--tudo)")
    return lines


def clip(lines, budget, tudo=False):
    """Corta `lines` a `budget` linhas, com aviso de `--tudo`, salvo se `tudo`."""
    if tudo or len(lines) <= budget:
        return lines
    return lines[:max(budget - 1, 0)] + [f"… +{len(lines) - budget + 1} linhas (--tudo)"]


def summary(sps):
    todo = sum(sp.status == "TODO" for sp in sps)
    doing = sum(sp.status == "Doing" for sp in sps)
    avisos = sum(bool(sp.warning) for sp in sps)
    return f"{todo} TODO, {doing} Doing, {avisos} {'aviso' if avisos == 1 else 'avisos'}"


def main_tree(args):
    sps = collect(args.root, include_done=True)
    if args.project:
        sps = [sp for sp in sps if sp.project == args.project]
    groups, loose = build_tree(sps)
    loose = sort_sps(loose, args.sort, args.reverse)
    order = {id(sp): i for i, sp in enumerate(sort_sps([m for m, _ in groups], args.sort, args.reverse))}
    groups.sort(key=lambda g: order[id(g[0])])

    def visible(sp):
        return (args.all or sp.status != "Done") and (not args.status or sp.status.lower() == args.status)

    head = next_block(sps, args.tudo)
    foot = summary([sp for sp in sps if visible(sp)])
    body = render_tree(groups, loose, visible).splitlines() or [""]
    head = head + [""] if head else []
    budget = MAX_LINES - len(head) - 1  # resumo
    print("\n".join(head + clip(body, budget, args.tudo) + [foot]))
    return 0


def tree_closed(root, slug, repo, project=None):
    """Checklist mecânica do fecho de uma árvore de SPs. Devolve (rc, linhas): 0 fechada, 1 falhas, 2 slug desconhecido."""
    sps = collect(root, include_done=True)
    if project:
        sps = [sp for sp in sps if sp.project == project]
    by_slug = {sp.slug: sp for sp in sps}
    node = by_slug.get(slug)
    if node is None:
        return 2, [f"slug desconhecido: {slug}"]
    top, seen = node, {node.slug}
    while top.parent in by_slug and top.parent not in seen:
        top = by_slug[top.parent]
        seen.add(top.slug)
    tree, queue = [], [top]
    while queue:
        cur = queue.pop(0)
        tree.append(cur)
        queue += [sp for sp in sps if sp.parent == cur.slug and sp not in tree and sp not in queue]
    falhas = [f"por fechar: {sp.slug} ({sp.status})" for sp in tree if sp.status != "Done"]
    falhas += [f"{sp.slug}: {sp.warning}" for sp in tree if sp.warning]
    done = {sp.slug for sp in tree if sp.status == "Done"}
    falhas += [f"{sp.slug}: dependência por cumprir ({d})" for sp in tree for d in sp.depends_on if d not in done and d in by_slug]
    if not list(Path(repo).glob("COMMIT_*.md")):
        falhas.append("sem COMMIT_*.md gerado")
    falhas += [f"{sp.slug}: dependência inexistente ({d})" for sp in tree for d in sp.depends_on if d not in by_slug]
    linhas = [f"árvore de {top.slug}: {', '.join(sp.slug for sp in tree)}"]
    linhas += [f"✘ {f}" for f in falhas]
    linhas.append("ÁRVORE FECHADA" if not falhas else "ÁRVORE NÃO FECHADA: não propor commit")
    return (1 if falhas else 0), linhas


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lista SPs pendentes (TODO e Doing)")
    ap.add_argument("--tree-closed", metavar="SLUG", help="checklist de fecho da árvore a que o SP pertence (rc 0 fechada, 1 falhas, 2 slug desconhecido)")
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent), help=argparse.SUPPRESS)
    ap.add_argument("--sort", choices=("priority", "created", "status"), default="status")
    ap.add_argument("--reverse", action="store_true")
    ap.add_argument("--project")
    ap.add_argument("--status", choices=("todo", "doing"))
    ap.add_argument("--all", action="store_true", help="inclui Done")
    ap.add_argument("--flat", action="store_true", help="tabela plana (sem agrupar programas)")
    ap.add_argument("--tudo", action="store_true", help="sem limite de 40 linhas (nem de bloqueados)")
    ap.add_argument("--tree", action="store_true", help="(predefinido) agrupa os filhos sob o SP-mãe")
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    if args.tree_closed:
        rc, linhas = tree_closed(args.root, args.tree_closed, args.repo, args.project)
        print("\n".join(linhas))
        return rc
    if not args.flat:
        return main_tree(args)
    sps = collect(args.root, include_done=args.all)
    if args.project:
        sps = [sp for sp in sps if sp.project == args.project]
    if args.status:
        sps = [sp for sp in sps if sp.status.lower() == args.status]
    sps = sort_sps(sps, args.sort, args.reverse)
    print(render(sps))
    print(summary(sps))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
