#!/usr/bin/env python3
"""Report da fase 6 do michi, montado só com fontes duráveis do SP. Não faz commit.

Secções fixas: Alterado · Verificado · Provas · Dificuldades · Em aberto.
- Alterado: `git diff --stat` contra a base (por omissão `master`).
- Verificado: comandos de `gates:`; o RC vem de `--gates` (corre-os) e, sem isso, fica «não corrido».
- Provas: `## Prova` do SP.
- Dificuldades: causas das linhas `Reflect <fase>:` (obrigatória; vazia = aviso e rc 3).
- Em aberto: critérios `- [ ]` por cumprir.

Uso: python -I scripts/sp-report.py <slug|caminho.md> [--base master] [--gates] [--project P]
rc: 0 ok, 1 erro, 3 secção «Dificuldades» vazia
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kf_git  # noqa: E402
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


def aviso_atraso(atras: int, base: str = "master") -> str:
    if atras <= 0:
        return ""
    return f"AVISO: a worktree está {atras} commit(s) atrás de {base}; o diff pode mostrar remoções que não são deste SP (fazer rebase/merge de {base}).\n"


def _atras(base: str, cwd) -> int:
    r = kf_git.run(cwd or ".", "rev-list", "--count", f"HEAD..{base}", run=subprocess.run)
    return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else 0


def gerar(text: str, slug: str, diff_stat: list[str] | None = None, gates: list[dict] | None = None, atras: int = 0) -> str:
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
        "## Alterado\n" + aviso_atraso(atras) + ("\n".join(f"    {l}" for l in diff_stat) if diff_stat else "- sem diff contra a base"),
        "## Verificado\n" + _bullets(verificado, "sem gates no frontmatter"),
        "## Provas\n" + _bullets(provas, "sem `## Prova` no SP"),
        "## Dificuldades\n" + (_bullets(dif, "") if dif else "- SEM DIFICULDADES REGISTADAS: escrever «nenhuma» com a justificação ou correr `/reflect fase`"),
        "## Em aberto\n" + _bullets(abertos, "nada"),
    ]
    return "\n\n".join(partes) + "\n"


def _git_stat(base: str, cwd=None) -> list[str]:
    r = kf_git.run(cwd or HERE.parent, "diff", "--stat", base, run=subprocess.run)
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
    sp_gates = _load("sp_gates_run", "sp-gates.py")
    sp_list = _load("sp_list_report", "sp-list.py")
    alvo, raiz = None, None
    p = Path(a.sp)
    roots = [Path(r) for r in sp_gates.sp_roots(a.sp)] if p.suffix != ".md" else [Path(HERE.parent)]
    for root in roots:
        for sp in sp_list.collect(sp_list.default_root(root), include_done=True):
            if (p.suffix == ".md" and sp.path.resolve() == p.resolve()) or sp.slug == a.sp:
                if a.project is None or sp.project == a.project:
                    alvo, raiz = sp, root
                    break
        if alvo:
            break
    if alvo is None:
        print(f"SP não encontrado: {a.sp}")
        return 1
    text = alvo.path.read_text(encoding="utf-8")
    res = None
    if a.gates:
        res = sp_gates.run(sp_gates.parse_gates(text))
    print(gerar(text, alvo.slug, _git_stat(a.base, raiz), res, _atras(a.base, raiz)))
    return 0 if dificuldades_ok(text) else 3


if __name__ == "__main__":
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    import kf_errlog
    sys.exit(kf_errlog.executar("sp-report", main))
