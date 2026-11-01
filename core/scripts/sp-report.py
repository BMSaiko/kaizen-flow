#!/usr/bin/env python3
"""Report da fase 6 do michi, montado só com fontes duráveis do SP. Não faz commit.

Secções fixas: Alterado · Verificado · Provas · Dificuldades · Em aberto.
- Alterado: `git diff --stat` contra a base (por omissão `master`).
- Verificado: comandos de `gates:`; o RC vem de `--gates` (corre-os) e, sem isso, fica «não corrido».
- Provas: `## Prova` do SP.
- Dificuldades: causas das linhas `Reflect <fase>:` (obrigatória; vazia = aviso e rc 3).
- Em aberto: critérios `- [ ]` por cumprir.

Uso: python -I scripts/sp-report.py <slug|caminho.md> [--base master] [--gates] [--project P]
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEM_PATCH = re.compile(r"^(?:[-*]\s*)?Reflect\s+[^:]*:\s*sem patch\.?\s*$", re.I)
LINHA = re.compile(r"^(?:[-*]\s*)?Reflect\b[^:\n]*:\s*\S", re.I)


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def section(text: str, prefix: str) -> str:
    m = re.search(rf"^##\s+{re.escape(prefix)}[^\n]*\n(.*?)(?=^##\s|\Z)", text, re.S | re.M)
    return m.group(1) if m else ""


def dificuldades(text: str) -> list[str]:
    """Linhas `Reflect <fase>: ...` com causa (exclui «sem patch» puro)."""
    out = []
    for linha in section(text, "Reflect").splitlines():
        s = linha.strip()
        if LINHA.match(s) and not SEM_PATCH.match(s):
            out.append(s.lstrip("-* ").strip())
    return out


def dificuldades_ok(text: str) -> bool:
    return bool(dificuldades(text))


def _bullets(linhas: list[str], vazio: str) -> str:
    return "\n".join(f"- {l}" for l in linhas) if linhas else f"- {vazio}"


def gerar(text: str, slug: str, diff_stat: list[str] | None = None, gates: list[dict] | None = None) -> str:
    sp_gates = _load("sp_gates_report", "sp-gates.py")
    rc_por_cmd = {g["cmd"]: g for g in (gates or [])}
    verificado = []
    for g in sp_gates.parse_gates(text):
        r = rc_por_cmd.get(g["cmd"])
        rc = "não corrido" if r is None else ("timeout" if r.get("timeout") else r["rc"])
        verificado.append(f"`{g['cmd']}` rc={rc}")
    provas = [l.strip().lstrip("-* ").strip() for l in section(text, "Prova").splitlines() if l.strip()]
    abertos = [m.strip() for m in re.findall(r"^- \[ \]\s*(.+)$", section(text, "4."), re.M)]
    dif = dificuldades(text)
    partes = [
        f"# Report — {slug}",
        "## Alterado\n" + ("\n".join(f"    {l}" for l in diff_stat) if diff_stat else "- sem diff contra a base"),
        "## Verificado\n" + _bullets(verificado, "sem gates no frontmatter"),
        "## Provas\n" + _bullets(provas, "sem `## Prova` no SP"),
        "## Dificuldades\n" + (_bullets(dif, "") if dif else "- SEM DIFICULDADES REGISTADAS: escrever «nenhuma» com a justificação ou correr `/reflect fase`"),
        "## Em aberto\n" + _bullets(abertos, "nada"),
    ]
    return "\n\n".join(partes) + "\n"


def _git_stat(base: str) -> list[str]:
    r = subprocess.run(["git", "diff", "--stat", base], capture_output=True, text=True, cwd=HERE.parent, encoding="utf-8")
    return r.stdout.splitlines() if r.returncode == 0 else []


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Report da fase 6 do michi")
    ap.add_argument("sp", help="slug ou caminho .md")
    ap.add_argument("--base", default="master")
    ap.add_argument("--gates", action="store_true", help="corre os gates do SP para registar o RC")
    ap.add_argument("--project")
    a = ap.parse_args(argv)
    sp_list = _load("sp_list_report", "sp-list.py")
    alvo = None
    p = Path(a.sp)
    for sp in sp_list.collect(sp_list.default_root(), include_done=True):
        if (p.suffix == ".md" and sp.path.resolve() == p.resolve()) or sp.slug == a.sp:
            if a.project is None or sp.project == a.project:
                alvo = sp
                break
    if alvo is None:
        print(f"SP não encontrado: {a.sp}")
        return 1
    text = alvo.path.read_text(encoding="utf-8")
    res = None
    if a.gates:
        sp_gates = _load("sp_gates_run", "sp-gates.py")
        res = sp_gates.run(sp_gates.parse_gates(text))
    print(gerar(text, alvo.slug, _git_stat(a.base), res))
    return 0 if dificuldades_ok(text) else 3


if __name__ == "__main__":
    sys.exit(main())
