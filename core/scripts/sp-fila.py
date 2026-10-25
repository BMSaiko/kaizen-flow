#!/usr/bin/env python3
"""Fila autónoma de SPs: escolhe o próximo SP elegível e lança-o (modo auto, sessão limpa).

Elegível = TODO, `modo: auto`, com `gates:`, dependências em Done, autorizações suficientes. Ordem:
prioridade, depois idade, com `depends_on` a mandar. Nunca faz push/PR: isso é do fecho de cada SP.

Uso:
  python -I scripts/sp-fila.py --dry-run [--max N] [--ate HH:MM] [--projeto P]   # ordem e exclusões
  python -I scripts/sp-fila.py [--max N] [--ate HH:MM] [--projeto P] [--orcamento N]   # arranca a fila
  python -I scripts/sp-fila.py --seguinte    # no fecho de cada SP da fila: regista e lança o seguinte
  python -I scripts/sp-fila.py --parar       # abandona a fila (apaga o estado)

O estado vive em `~/.claude/sp-fila-estado.json`; no fim (fila vazia, limite ou erro) escreve o
relatório em `knowledge/infra/reports/sp-fila/` e apaga o estado. Um SP lançado que não chegou a Done
conta como falhado: os dependentes ficam de fora e só continuam os independentes.
"""
import argparse
import importlib.util
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_spec = importlib.util.spec_from_file_location("sp_list", Path(__file__).with_name("sp-list.py"))
sp_list = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("sp_list", sp_list)
_spec.loader.exec_module(sp_list)

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
ESTADO = Path.home() / ".claude" / "sp-fila-estado.json"
RELATORIOS = REPO / "knowledge" / "infra" / "reports" / "sp-fila"
REQ_POR_SP = 50  # teto de requests por sessão (AGENTS.md); cada SP lançado gasta-o por inteiro
ORCAMENTO = 200
MAX_DEFEITO = 5


def load(root, project=None):
    """[(Sp, frontmatter)] de todos os SPs (incluindo Done, para saber as dependências cumpridas)."""
    items = []
    for sp in sp_list.collect(root, include_done=True):
        if project and sp.project != project:
            continue
        fm = sp_list.parse_frontmatter(sp.path.read_text(encoding="utf-8"))
        items.append((sp, fm))
    return items


def autorizacao(fm):
    """Motivo de exclusão por autorizações insuficientes, ou ''."""
    commit, push, pr = (fm.get(k, "") for k in ("commit", "push", "pr"))
    if push == "pergunta" or pr == "pergunta":
        return "autorização insuficiente (push/pr «pergunta» precisa do user)"
    if push == "auto" and commit == "nunca":
        return "autorização insuficiente (push auto com commit nunca)"
    if pr == "auto" and push != "auto":
        return "autorização insuficiente (pr auto sem push auto)"
    return ""


def estatico(sp, fm):
    if sp.status == "Doing":
        return "já em Doing"
    if sp.kind == "program":
        return "programa (SP-mãe, só agrupador)"
    if fm.get("modo") != "auto":
        return f"modo {fm.get('modo') or 'em falta'} (só `modo: auto`)"
    if "gates" not in fm:
        return "sem gates no frontmatter"
    return autorizacao(fm)


def plan(items, maximo=None):
    """(fila ordenada, [(slug, motivo)]). Função pura, sem FS."""
    done = {sp.slug for sp, _ in items if sp.status == "Done"}
    excluidos, cand = [], {}
    for sp, fm in items:
        if sp.status == "Done":
            continue
        why = estatico(sp, fm)
        if why:
            excluidos.append((sp.slug, why))
        else:
            cand[sp.slug] = sp

    def chave(sp):
        return (sp.priority, sp.created is None, sp.created or sp_list.date.min, sp.slug)

    fila, feitos = [], set(done)
    while True:
        prontos = [sp for sp in cand.values() if sp.slug not in feitos and all(d in feitos for d in sp.depends_on)]
        if not prontos:
            break
        sp = min(prontos, key=chave)
        fila.append(sp)
        feitos.add(sp.slug)

    resto = {s: sp for s, sp in cand.items() if s not in feitos}
    bloqueados = {s: [d for d in sp.depends_on if d not in feitos and d not in resto] for s, sp in resto.items()}
    bloqueados = {s: ds for s, ds in bloqueados.items() if ds}
    mudou = True
    while mudou:
        mudou = False
        for s, sp in resto.items():
            if s not in bloqueados and (ds := [d for d in sp.depends_on if d in bloqueados]):
                bloqueados[s], mudou = ds, True
    for s in sorted(resto):
        if s in bloqueados:
            excluidos.append((s, f"dependência em falta ({', '.join(bloqueados[s])})"))
        else:
            excluidos.append((s, "ciclo de dependências"))
    return (fila[:maximo] if maximo else fila), sorted(excluidos)


def limite(estado, agora):
    """Motivo para parar a fila, ou None."""
    if len(estado["feitos"]) + len(estado["falhados"]) >= estado["max"]:
        return f"atingido o máximo de {estado['max']} SPs"
    if estado.get("ate"):
        h, m = (int(x) for x in estado["ate"].split(":"))
        if (agora.hour, agora.minute) >= (h, m):
            return f"atingida a hora limite {estado['ate']}"
    if estado["usados"] + REQ_POR_SP > estado["orcamento"]:
        return f"orçamento de requests esgotado ({estado['usados']}/{estado['orcamento']})"
    return None


def render_plan(fila, excluidos):
    linhas = ["Ordem de execução:"]
    linhas += [f"  {i}. {sp.slug} ({sp.project}, {sp.priority}, {sp.created or '?'})" for i, sp in enumerate(fila, 1)] or ["  (vazia)"]
    linhas.append("Excluídos:")
    linhas += [f"  - {slug}: {why}" for slug, why in excluidos] or ["  (nenhum)"]
    return "\n".join(linhas)


def commits_desde(inicio, run):
    out = run(["git", "-C", str(REPO), "log", f"--since={inicio}", "--format=%h %s"], capture_output=True,
              text=True, encoding="utf-8").stdout or ""
    return [ln for ln in out.splitlines() if ln.strip()]


def relatorio(estado, fila, excluidos, motivo, rel_dir, run, agora):
    rel_dir.mkdir(parents=True, exist_ok=True)
    path = rel_dir / f"fila-{agora:%Y-%m-%d-%H%M}.md"
    commits = commits_desde(estado["inicio"], run)
    listar = lambda xs: [f"- {x}" for x in xs] or ["- nenhum"]
    linhas = ["---", "type: report", "tags: [sp-fila]", f"date: {agora:%Y-%m-%d}", "---",
              f"# Fila de SPs ({agora:%Y-%m-%d %H:%M})", "", f"Fim: {motivo}.", "",
              "## Feitos", *listar(estado["feitos"]), "", "## Falhados", *listar(estado["falhados"]), "",
              "## Saltados", *listar(f"{s}: {w}" for s, w in excluidos), "", "## Commits", *listar(commits), "",
              "## Próximos passos"]
    passos = [f"inspecionar o SP falhado `{s}` (continua em Doing) e correr `/michi` à mão" for s in estado["falhados"]]
    passos += [f"por correr: `{sp.slug}`" for sp in fila if sp.slug not in estado["falhados"]]
    passos += ["rever os saltados e, se fizer sentido, dar-lhes `modo: auto` e `gates:`"] if excluidos else []
    linhas += listar(passos) + [""]
    path.write_text("\n".join(linhas), encoding="utf-8")
    return path


def seguinte(root, estado_path, rel_dir, run=subprocess.run, agora=None):
    """Regista o SP lançado, respeita os limites e lança o seguinte. Devolve {acao, ...}."""
    agora = agora or datetime.now()
    estado = json.loads(Path(estado_path).read_text(encoding="utf-8"))
    items = load(root, estado.get("projeto"))
    if estado["lancado"]:
        sp = next((s for s, _ in items if s.slug == estado["lancado"]), None)
        (estado["feitos"] if sp is not None and sp.status == "Done" else estado["falhados"]).append(estado["lancado"])
        estado["lancado"] = None
    fila, excluidos = plan(items)
    motivo = limite(estado, agora) or ("fila vazia" if not fila else None)
    alvo = fila[0] if motivo is None else None
    if alvo is not None:
        doing = alvo.path.parent.parent / "Doing" / alvo.path.name
        for argv in ([sys.executable, "-I", str(SCRIPTS / "sp-move.py"), "--root", str(root), "--project", alvo.project, alvo.slug, "doing"],
                     [sys.executable, "-I", str(SCRIPTS / "sp-handoff.py"), "--launch", str(doing), "--auto"]):
            r = run(argv, capture_output=True, text=True, encoding="utf-8")
            if r.returncode != 0:
                motivo = f"erro a lançar {alvo.slug}: {(r.stderr or r.stdout).strip()}"
                estado["falhados"].append(alvo.slug)
                alvo = None
                break
    if alvo is None:
        path = relatorio(estado, fila, excluidos, motivo, rel_dir, run, agora)
        Path(estado_path).unlink()
        return {"acao": "fim", "motivo": motivo, "relatorio": str(path)}
    estado["lancado"] = alvo.slug
    estado["usados"] += REQ_POR_SP
    Path(estado_path).write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"acao": "lancou", "slug": alvo.slug, "caminho": str(doing)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fila autónoma de SPs")
    ap.add_argument("--dry-run", action="store_true", help="mostra a ordem e as exclusões, sem lançar")
    ap.add_argument("--seguinte", action="store_true", help="no fecho de um SP da fila: regista e lança o seguinte")
    ap.add_argument("--parar", action="store_true", help="abandona a fila")
    ap.add_argument("--max", type=int, default=MAX_DEFEITO, help=f"nº máximo de SPs (defeito {MAX_DEFEITO})")
    ap.add_argument("--ate", metavar="HH:MM", help="hora limite")
    ap.add_argument("--orcamento", type=int, default=ORCAMENTO, help=f"requests totais; cada SP gasta {REQ_POR_SP}")
    ap.add_argument("--projeto")
    ap.add_argument("--root", default=str(sp_list.DEFAULT_ROOT), help=argparse.SUPPRESS)
    ap.add_argument("--estado", default=str(ESTADO), help=argparse.SUPPRESS)
    ap.add_argument("--relatorios", default=str(RELATORIOS), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    estado = Path(args.estado)

    if args.parar:
        estado.unlink(missing_ok=True)
        print("fila abandonada")
        return 0
    if args.dry_run:
        fila, excluidos = plan(load(args.root, args.projeto), args.max)
        print(render_plan(fila, excluidos))
        return 0
    if args.seguinte:
        if not estado.exists():
            print("erro: sem fila em curso (arrancar com `sp-fila.py`)", file=sys.stderr)
            return 1
    else:
        if estado.exists():
            print(f"erro: fila já em curso ({estado}); `--seguinte` continua, `--parar` abandona", file=sys.stderr)
            return 1
        estado.parent.mkdir(parents=True, exist_ok=True)
        estado.write_text(json.dumps({"max": args.max, "ate": args.ate, "orcamento": args.orcamento, "usados": 0,
                                      "feitos": [], "falhados": [], "lancado": None, "projeto": args.projeto,
                                      "inicio": datetime.now().isoformat(timespec="seconds")}), encoding="utf-8")
    out = seguinte(args.root, estado, Path(args.relatorios))
    if out["acao"] == "lancou":
        print(f"lançado: {out['slug']} ({out['caminho']}); terminar o turno, a sessão nova arranca em segundo plano")
    else:
        print(f"fila terminada: {out['motivo']}\nrelatório: {out['relatorio']}")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
