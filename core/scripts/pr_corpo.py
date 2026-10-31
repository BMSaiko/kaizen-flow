#!/usr/bin/env python3
"""Fase final: corpo do PR a partir do SP, do pen test e do review; abre o PR se a política deixar.

Uso: pr_corpo.py <SP.md> --review <estado.json> [--pentest <relatorio>] [--repo R] [--titulo T] [--criar]
Sem --criar só imprime o corpo. Com --criar: exige review APROVADO e respeita `pr:` do SP
(auto cria; pergunta sai com rc 3 para o agente pedir confirmação; nunca recusa).
rc 0 ok, 2 review não aprovado, 3 pedir confirmação, 4 política `nunca`/em falta, 5 corpo incompleto.
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
    prova = "\n".join([p for p in [prova, *extra] if p])
    tpl = TEMPLATE.read_text(encoding="utf-8") if TEMPLATE else TEMPLATE_FALLBACK
    for k, v in {"feito": feito, "decisoes": decisoes or "Sem decisões registadas.", "por_fazer": por_fazer, "prova": prova}.items():
        tpl = tpl.replace("{" + k + "}", v)
    return tpl, bool(feito and prova)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sp")
    ap.add_argument("--review", required=True)
    ap.add_argument("--pentest")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--titulo")
    ap.add_argument("--criar", action="store_true")
    a = ap.parse_args(argv)
    sp = Path(a.sp).read_text(encoding="utf-8")
    review = json.loads(Path(a.review).read_text(encoding="utf-8"))
    pent = Path(a.pentest).read_text(encoding="utf-8") if a.pentest else None
    texto, completo = corpo(sp, review, pent)
    print(texto)
    if not a.criar:
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
    titulo = a.titulo or frontmatter(sp, "slug") or "PR"
    r = subprocess.run(["gh", "pr", "create", "--title", titulo, "--body", texto], cwd=a.repo, text=True)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
