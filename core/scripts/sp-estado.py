#!/usr/bin/env python3
"""Estado de um SP numa só leitura (≤30 linhas). Só leitura.

Junta o que o arranque de `/michi <SP>` ou de um handoff lê em chamadas separadas:
pasta/fase, critérios e passos, gates, dependências, últimas linhas de `## Progresso`,
ramo e ficheiros alterados no git.

Uso:
  python -I scripts/sp-estado.py <slug|caminho.md> [--project P]
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kaizen_engine  # noqa: E402

MAX_LINES = 30
MAX_FILES = 8
MAX_PROGRESSO = 3


def section(text, prefix):
    """Corpo da secção `## <prefix>...` até à seguinte `## `."""
    m = re.search(rf"^##\s+{re.escape(prefix)}[^\n]*\n(.*?)(?=^##\s|\Z)", text, re.S | re.M)
    return m.group(1) if m else ""


def git_state():
    def run(*a):
        r = subprocess.run(["git", *a], capture_output=True, text=True, cwd=HERE.parent)
        return r.stdout.splitlines()
    return run("rev-parse", "--abbrev-ref", "HEAD")[:1] + run("status", "--short")


def estado(ref, root=None, project=None, git_lines=None):
    sp_list = kaizen_engine.load("sp-list")
    sp_gates = kaizen_engine.load("sp-gates")
    root = Path(root) if root else sp_list.default_root()
    sps = sp_list.collect(root, include_done=True)
    alvo = None
    p = Path(ref)
    ref = sp_list.normalize_ref(root, ref)
    for sp in sps:
        if (p.suffix == ".md" and sp.path.resolve() == p.resolve()) or sp.slug == ref:
            if project is None or sp.project == project:
                alvo = sp
                break
    if alvo is None:
        return f"SP não encontrado: {ref}"
    text = alvo.path.read_text(encoding="utf-8")
    fm = kaizen_engine.parse_frontmatter(text)
    done = {s.slug for s in sps if s.status == "Done"}
    unmet = [d for d in alvo.depends_on if d not in done]

    crit = re.findall(r"^- \[([ xX])\]", section(text, "4."), re.M)
    feitos = sum(1 for c in crit if c.lower() == "x")
    passos = re.findall(r"^\d+\.\s+(.*)", section(text, "7."), re.M)
    prog = [l for l in section(text, "Progresso").splitlines() if l.strip()][-MAX_PROGRESSO:]
    gl = git_lines if git_lines is not None else git_state()
    ramo, ficheiros = (gl[0] if gl else "?"), gl[1:]

    filhos = [s for s in sps if s.parent == alvo.slug and s.project == alvo.project]
    out = [
        f"{alvo.slug} · {alvo.status} · {alvo.priority} · {alvo.project} · modo {fm.get('modo', '-')}",
        f"parent: {alvo.parent or '-'} · dependências: " + (("por cumprir " + ", ".join(unmet)) if unmet else ("ok" if alvo.depends_on else "-")),
        f"critérios: {feitos}/{len(crit)} · gates: {len(sp_gates.parse_gates(text))}",
        f"passos ({len(passos)}): " + " | ".join(s.rstrip(".") for s in passos[:6]),
    ]
    if filhos:
        out.append(f"filhos: {len(filhos)} filhos · perguntar concorrência (com/sem; defeito sem) antes de arrancar a fila")
    if prog:
        out.append("progresso:")
        out += [f"  {l.strip()}" for l in prog]
    out.append(f"git: {ramo} · {len(ficheiros)} alterados")
    out += [f"  {l}" for l in ficheiros[:MAX_FILES]]
    if len(ficheiros) > MAX_FILES:
        out.append(f"  … +{len(ficheiros) - MAX_FILES}")
    return "\n".join(out[:MAX_LINES])


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Estado de um SP numa só leitura")
    ap.add_argument("sp", help="slug ou caminho .md")
    ap.add_argument("--project")
    args = ap.parse_args(argv)
    out = estado(args.sp, project=args.project)
    print(out)
    return 1 if out.startswith("SP não encontrado") else 0


if __name__ == "__main__":
    sys.exit(main())
