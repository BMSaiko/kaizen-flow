"""Propõe o escalão de uma tarefa (pequena | media | grande) e o comando sp-new.

Critérios (única fonte; playbook kaizen-flow §Escalões):
  grande: ficheiros > 15 ou horas > 8, ou risco alto com ficheiros > 5
  média:  ficheiros > 3 ou horas > 2, ou risco alto
  pequena: o resto
Override numa linha: --escalao pequena|media|grande.
"""
import argparse
import sys

ESCALOES = ("pequena", "media", "grande")
RISCOS = ("baixo", "medio", "alto")


def classificar(ficheiros, risco, horas):
    if ficheiros > 15 or horas > 8 or (risco == "alto" and ficheiros > 5):
        return "grande"
    if ficheiros > 3 or horas > 2 or risco == "alto":
        return "media"
    return "pequena"


def comando(escalao, project, slug, priority):
    base = f"python -I scripts/sp-new.py --project {project} --priority {priority}"
    if escalao == "pequena":
        return f"{base} --slug {slug}"
    if escalao == "media":
        return f"{base} --program {slug} --children {slug}-a,{slug}-b:{slug}-a"
    return f"{base} --program {slug} --children {slug}-a,{slug}-b:{slug}-a,{slug}-c:{slug}-a+{slug}-b"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--project", required=True)
    p.add_argument("--slug", required=True)
    p.add_argument("--priority", default="P2")
    p.add_argument("--ficheiros", type=int, required=True)
    p.add_argument("--risco", choices=RISCOS, default="baixo")
    p.add_argument("--horas", type=float, required=True)
    p.add_argument("--escalao", choices=ESCALOES, help="override do escalão proposto")
    a = p.parse_args(argv)
    proposto = classificar(a.ficheiros, a.risco, a.horas)
    escalao = a.escalao or proposto
    nota = "" if escalao == proposto else f" (override; proposto: {proposto})"
    print(f"escalão: {escalao}{nota}")
    print(comando(escalao, a.project, a.slug, a.priority))
    return 0


if __name__ == "__main__":
    sys.exit(main())
