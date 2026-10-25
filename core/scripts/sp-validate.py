#!/usr/bin/env python3
"""Valida um Super Prompt: frontmatter obrigatório, 8 secções não vazias e status = pasta.

Só leitura. RC 0 se válido; RC 1 com a lista de problemas no stderr.

Uso:
  python -I scripts/sp-validate.py <caminho.md> [<caminho.md> ...]
"""
import argparse
import importlib.util
import re
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("sp_list", Path(__file__).with_name("sp-list.py"))
sp_list = importlib.util.module_from_spec(_spec)
sys.modules["sp_list"] = sp_list
_spec.loader.exec_module(sp_list)

_gspec = importlib.util.spec_from_file_location("sp_gates", Path(__file__).with_name("sp-gates.py"))
sp_gates = importlib.util.module_from_spec(_gspec)
sys.modules["sp_gates"] = sp_gates
_gspec.loader.exec_module(sp_gates)

REQUIRED_FIELDS = ("status", "created", "updated", "phase", "slug", "date", "project", "priority")
SECTION_NAMES = {
    1: "Role", 2: "Context", 3: "Objective", 4: "Success criteria",
    5: "Constraints", 6: "Seams", 7: "Steps", 8: "Done-when",
}
HEADING = re.compile(r"^##\s+(\d+)\.\s+(.*?)\s*$")


def _sections(text):
    """Mapa número -> corpo da secção (texto até ao próximo `## `)."""
    found, current = {}, None
    for line in text.splitlines():
        m = HEADING.match(line)
        if m and int(m.group(1)) in SECTION_NAMES and m.group(2).lower().startswith(SECTION_NAMES[int(m.group(1))].lower()):
            current = int(m.group(1))
            found[current] = []
        elif line.startswith("## "):
            current = None
        elif current is not None:
            found[current].append(line)
    return {n: "\n".join(body).strip() for n, body in found.items()}


def validate(text, folder=None):
    """Devolve a lista de erros (vazia = válido). `folder` = pasta (TODO|Doing|Done) ou None."""
    errors = []
    fm = sp_list.parse_frontmatter(text)
    if not fm:
        errors.append("frontmatter em falta")
    else:
        for field in REQUIRED_FIELDS:
            if not fm.get(field):
                errors.append(f"frontmatter sem '{field}'")
        if fm.get("modo") and fm["modo"] not in ("auto", "manual"):
            errors.append(f"modo '{fm['modo']}' inválido (auto|manual)")
        for key in ("commit", "push", "pr"):
            if fm.get(key) and fm[key] not in ("auto", "pergunta", "nunca"):
                errors.append(f"{key} '{fm[key]}' inválido (auto|pergunta|nunca)")
        if fm.get("push") == "auto" and fm.get("commit") == "nunca":
            errors.append("push auto exige commit ≠ nunca")
        if fm.get("pr") == "auto" and fm.get("push") != "auto":
            errors.append("pr auto exige push auto")
        errors += sp_gates.problems(sp_gates.parse_gates(text))
        if "prova" in fm:
            if not fm["prova"]:
                errors.append("prova vazia")
            elif sp_gates.forbidden(fm["prova"]):
                errors.append(f"prova proibida ({sp_gates.forbidden(fm['prova'])}): {fm['prova']}")
        if folder and fm.get("status") and fm["status"] != folder:
            errors.append(f"status '{fm['status']}' ≠ pasta '{folder}'")
    sections = _sections(text)
    for n, name in SECTION_NAMES.items():
        if n not in sections:
            errors.append(f"secção em falta: {n}. {name}")
        elif not sections[n]:
            errors.append(f"secção vazia: {n}. {name}")
    return errors


def warnings(text):
    """Avisos (não bloqueiam): SP `modo: auto` sem gates executáveis."""
    fm = sp_list.parse_frontmatter(text)
    if fm.get("modo") == "auto" and not sp_gates.parse_gates(text):
        return ["modo auto sem 'gates:' (a verificação fica inferida)"]
    return []


def main(argv=None):
    ap = argparse.ArgumentParser(description="Valida Super Prompts")
    ap.add_argument("paths", nargs="+")
    args = ap.parse_args(argv)
    rc = 0
    for raw in args.paths:
        path = Path(raw)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{path}: erro de leitura ({exc.__class__.__name__})", file=sys.stderr)
            rc = 1
            continue
        folder = path.parent.name if path.parent.name in sp_list.FOLDERS else None
        errors = validate(text, folder)
        for w in warnings(text):
            print(f"{path.name}: aviso: {w}", file=sys.stderr)
        if errors:
            rc = 1
            for e in errors:
                print(f"{path.name}: {e}", file=sys.stderr)
        else:
            print(f"{path.name}: ok")
    return rc


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
