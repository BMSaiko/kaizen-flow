#!/usr/bin/env python3
"""Valida um `_PLAN_*.md` do DP: frontmatter, 2-7 fases, cada fase com Done when, Gate e Risco.

Uso:
  python -I scripts/plan-validate.py <plano.md>          # rc 0 = válido, 1 = erros (um por linha)
  python -I scripts/plan-validate.py <plano.md> --gates  # imprime os gates como bloco `gates:` do SP
rc: 0 válido, 1 há erros, 2 número de argumentos errado
"""
import re
import sys
from pathlib import Path

FM_KEYS = ("status", "project", "scope-gate", "research-brief", "created")
FIELDS = ("Done when", "Gate", "Risco")
PLACEHOLDER = {"", "tbd", "todo", "n/a", "na", "-", "?", "..."}


def _fases(text):
    m = re.search(r"^## Phases\s*$(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not m:
        return []
    partes = re.split(r"^### (\d+)\.[^\n]*\n", m.group(1), flags=re.M)
    return [(int(partes[i]), partes[i + 1]) for i in range(1, len(partes) - 1, 2)]


def _campo(corpo, nome):
    m = re.search(rf"^- \*\*{nome}:\*\*[ \t]*(.*)$", corpo, re.M)
    return m.group(1).strip() if m else None


def _cmd(valor):
    return valor.strip().strip("`").strip()


def validate(path):
    text = Path(path).read_text(encoding="utf-8")
    erros = []
    fm = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not fm:
        erros.append("frontmatter em falta")
    else:
        for k in FM_KEYS:
            if not re.search(rf"^{k}:\s*\S", fm.group(1), re.M):
                erros.append(f"frontmatter sem {k}")
    fases = _fases(text)
    if not 2 <= len(fases) <= 7:
        erros.append(f"{len(fases)} fases (esperado 2-7)")
    for n, corpo in fases:
        for nome in FIELDS:
            v = _campo(corpo, nome)
            if v is None:
                erros.append(f"fase {n}: falta {nome}")
            elif nome == "Gate" and _cmd(v).lower() in PLACEHOLDER:
                erros.append(f"fase {n}: Gate vazio/placeholder")
            elif nome != "Gate" and v.lower() in PLACEHOLDER:
                erros.append(f"fase {n}: {nome} vazio")
    for sec in ("Risks", "Out of Scope"):
        if not re.search(rf"^## {sec}\s*$", text, re.M):
            erros.append(f"falta a secção {sec}")
    return erros


def avisos(path):
    """Avisos (nunca erros): plano de código cuja fase 1 não é o walking skeleton."""
    text = Path(path).read_text(encoding="utf-8")
    fases = _fases(text)
    if not fases:
        return []
    codigo = False
    for _, corpo in fases:
        scope = _campo(corpo, "Scope") or ""
        for caminho in re.findall(r"[\w.\-]+/[\w./\-]*", scope):
            if not caminho.replace("\\", "/").startswith("knowledge/"):
                codigo = True
    if not codigo:
        return []
    m = re.search(r"^### 1\.([^\n]*)\n", text, re.M)
    fase1 = ((m.group(1) if m else "") + fases[0][1]).lower()
    if "skeleton" in fase1 or "ponta a ponta" in fase1:
        return []
    return ["aviso: plano de código sem walking skeleton na fase 1 (fluxo mais fino ponta a ponta)"]


def gates(path):
    text = Path(path).read_text(encoding="utf-8")
    out = []
    for _, corpo in _fases(text):
        g = _campo(corpo, "Gate")
        if g and _cmd(g).lower() not in PLACEHOLDER and _cmd(g) not in out:
            out.append(_cmd(g))
    return out


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 2
    erros = validate(args[0])
    for e in erros:
        print(e)
    if erros:
        return 1
    for a in avisos(args[0]):
        print(a)
    if "--gates" in argv:
        print("gates:")
        for g in gates(args[0]):
            print(f"  - cmd: {g}\n    timeout: 120")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
