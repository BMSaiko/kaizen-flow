#!/usr/bin/env python3
"""Fase final: corpo do PR a partir do SP, do pen test e do review; abre o PR se a política deixar.

Uso: pr_corpo.py <SP.md> --review <estado.json> [--pentest <relatorio>] [--repo R] [--titulo T] [--base B] [--criar] [--dry-run]
Sem --criar (ou com --dry-run) só imprime o corpo e a base detetada; nunca cria PR. Com --criar: exige review APROVADO e respeita `pr:` do SP
(auto cria; pergunta sai com rc 3 para o agente pedir confirmação; nunca recusa).
rc 0 ok, 2 review não aprovado, 3 pedir confirmação, 4 política `nunca`/em falta, 5 corpo incompleto,
6 base ambígua (main/master/dev): pedir ao user ou passar --base.
Nunca acrescenta atribuição a agentes.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TEMPLATE = next((p for p in (RAIZ / ".claude" / "skills" / "pr-fase" / "PR_TEMPLATE.md", RAIZ / "skills" / "pr-fase" / "PR_TEMPLATE.md") if p.exists()), None)
TEMPLATE_FALLBACK = "## O que foi feito\n{feito}\n\n## Decisões tomadas\n{decisoes}\n\n## O que ficou por fazer\n{por_fazer}\n\n## Prova\n{prova}\n"


def seccao(texto, *titulos):
    """Conteúdo da primeira secção `## <titulo>` (prefixo, sem distinguir maiúsculas) até ao próximo `## `."""
    for t in titulos:
        m = re.search(rf"^##\s+{re.escape(t)}[^\n]*\n(.*?)(?=^##\s|\Z)", texto, re.S | re.M | re.I)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return ""


def frontmatter(texto, chave):
    m = re.search(rf"^{chave}:\s*(\S+)", texto, re.M)
    return m.group(1) if m else ""


ATRIBUICAO = re.compile(r"^.*(co-authored-by|generated with).*\n?", re.I | re.M)


def provas_e_gates(sp_texto):
    """Linhas extra para a Prova: paths `proofs/...` citados no SP e comandos das gates do frontmatter."""
    linhas = []
    caminhos = sorted(set(re.findall(r"[\w./\\-]*proofs[/\\][\w./\-]+", sp_texto)))
    if caminhos:
        linhas.append("Provas: " + ", ".join(f"`{c}`" for c in caminhos))
    fm = re.match(r"---\n(.*?)\n---", sp_texto, re.S)
    cmds = re.findall(r"cmd:\s*(.+)", fm.group(1)) if fm else []
    if cmds:
        linhas.append("Gates: " + "; ".join(f"`{c.strip()}`" for c in cmds))
    return linhas


def detetar_base(repo):
    """(base, candidatos): ramos remotos main/master/dev; base só se houver exatamente um."""
    r = subprocess.run(["git", "branch", "-r"], cwd=repo, text=True, capture_output=True)
    nomes = {l.strip().split("/", 1)[1] for l in r.stdout.splitlines() if "/" in l and "->" not in l}
    cand = [b for b in ("main", "master", "dev") if b in nomes]
    return (cand[0] if len(cand) == 1 else None), cand


def corpo(sp_texto, review, pentest_txt):
    feito = seccao(sp_texto, "3. Objective", "Objective") or seccao(sp_texto, "Progresso")
    progresso = seccao(sp_texto, "Progresso")
    if progresso and progresso not in feito:
        feito = f"{feito}\n\n{progresso}".strip()
    decisoes = seccao(sp_texto, "Decisões", "Decisoes")
    por_fazer = seccao(sp_texto, "Por fazer") or "Nada em aberto."
    prova = seccao(sp_texto, "Prova de done", "Prova")
    extra = []
    if pentest_txt is not None:
        extra.append(f"Pen test: {pentest_txt.strip() or 'sem achados'}")
    if review:
        extra.append(f"Review: {review.get('veredicto')} ao fim de {review.get('iteracao')} iteração(ões)")
    prova = "\n".join([p for p in [prova, *provas_e_gates(sp_texto), *extra] if p])
    tpl = TEMPLATE.read_text(encoding="utf-8") if TEMPLATE else TEMPLATE_FALLBACK
    for k, v in {"feito": feito, "decisoes": decisoes or "Sem decisões registadas.", "por_fazer": por_fazer, "prova": prova}.items():
        tpl = tpl.replace("{" + k + "}", v)
    return ATRIBUICAO.sub("", tpl), bool(feito and prova)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sp")
    ap.add_argument("--review", required=True)
    ap.add_argument("--pentest")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--titulo")
    ap.add_argument("--base")
    ap.add_argument("--criar", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    sp = Path(a.sp).read_text(encoding="utf-8")
    review = json.loads(Path(a.review).read_text(encoding="utf-8"))
    pent = Path(a.pentest).read_text(encoding="utf-8") if a.pentest else None
    texto, completo = corpo(sp, review, pent)
    print(texto)
    base, cand = (a.base, [a.base]) if a.base else detetar_base(a.repo)
    print(f"Base: {base or 'ambígua ' + str(cand)}", file=sys.stderr)
    if a.dry_run or not a.criar:
        return 0
    if review.get("veredicto") != "APROVADO":
        print("PR recusado: review não aprovado", file=sys.stderr)
        return 2
    if not completo:
        print("PR recusado: corpo sem 'feito' ou sem 'prova'", file=sys.stderr)
        return 5
    pol = frontmatter(sp, "pr")
    if pol == "pergunta":
        print("PR: política `pergunta`, pedir confirmação ao utilizador", file=sys.stderr)
        return 3
    if pol != "auto":
        print(f"PR não criado: política `{pol or 'em falta'}`", file=sys.stderr)
        return 4
    if not base:
        print(f"PR não criado: base ambígua ou desconhecida {cand}, pedir ao user ou usar --base", file=sys.stderr)
        return 6
    titulo = a.titulo or frontmatter(sp, "slug") or "PR"
    r = subprocess.run(["gh", "pr", "create", "--base", base, "--title", titulo, "--body", texto], cwd=a.repo, text=True)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
