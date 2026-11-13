#!/usr/bin/env python3
"""Valida um Super Prompt: frontmatter obrigatório, 8 secções não vazias e status = pasta.

Só leitura. RC 0 se válido; RC 1 com a lista de problemas no stderr.

Uso:
  python -I scripts/sp-validate.py <caminho.md> [<caminho.md> ...]
rc: 0 válido, 1 problemas
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402
import sp_aprovacao  # noqa: E402

sp_list = kaizen_engine.load("sp-list")
sp_gates = kaizen_engine.load("sp-gates")

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


def _extra(text, titulo):
    """Corpo da secção `## <titulo>` (sem numeração)."""
    corpo, dentro = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            dentro = line[3:].strip().lower().startswith(titulo.lower())
        elif dentro:
            corpo.append(line)
    return "\n".join(corpo).strip()


def _decisoes(text):
    return _extra(text, "Decisões")


def _esboco(text):
    return _extra(text, "Esboço")


GATES_OBRIGATORIOS_DESDE = "2026-11-13"  # SPs anteriores só têm aviso


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
        if fm.get("michi_modelo") and fm["michi_modelo"] not in ("simples", "default", "complexo"):
            errors.append(f"michi_modelo '{fm['michi_modelo']}' inválido (simples|default|complexo)")
        if fm.get("execucao"):
            if fm["execucao"] not in ("sequencial", "paralelo"):
                errors.append(f"execucao '{fm['execucao']}' inválido (sequencial|paralelo)")
            if fm.get("kind") != "program":
                errors.append("execucao só se aplica a SP-mãe (kind: program)")
        for key in ("commit", "push", "pr"):
            if fm.get(key) and fm[key] not in ("auto", "pergunta", "nunca"):
                errors.append(f"{key} '{fm[key]}' inválido (auto|pergunta|nunca)")
        if fm.get("push") == "auto" and fm.get("commit") == "nunca":
            errors.append("push auto exige commit ≠ nunca")
        if fm.get("pr") == "auto" and fm.get("push") != "auto":
            errors.append("pr auto exige push auto")
        if fm.get("merge") and fm["merge"] not in ("auto", "nunca"):
            errors.append(f"merge '{fm['merge']}' inválido (auto|nunca)")
        if fm.get("merge") == "auto" and fm.get("pr") != "auto":
            errors.append("merge auto exige pr auto")
        if fm.get("perfil") and fm["perfil"] not in ("cauteloso", "normal", "autonomo"):
            errors.append(f"perfil '{fm['perfil']}' inválido (cauteloso|normal|autonomo)")
        for key in ("max_tentativas", "max_requests"):
            if key in fm and not (fm[key].isdigit() and int(fm[key]) >= 1):
                errors.append(f"{key} '{fm[key]}' tem de ser um inteiro ≥ 1")
        bad = [x for x in sp_list.parse_list(fm.get("parar_se")) if x not in ("gate-falha", "ambiguidade", "ficheiro-fora-de-escopo", "custo")]
        if bad:
            errors.append(f"parar_se inválido {bad}")
        globs = {k: sp_list.parse_list(fm.get(k)) for k in ("escopo", "fora_de_escopo")}
        for key, vals in globs.items():
            if key in fm and not vals:
                errors.append(f"{key} vazio")
            errors += [f"{key}: glob inválido '{g}'" for g in vals if ".." in g.replace("\\", "/").split("/")]
        if globs["fora_de_escopo"] and not globs["escopo"]:
            errors.append("fora_de_escopo exige escopo")
        if fm.get("perfil") == "autonomo" and not sp_gates.parse_gates(text):
            errors.append("perfil autonomo exige gates")
        if fm.get("modo") == "auto" and fm.get("kind") != "program" and str(fm.get("date", "")) >= GATES_OBRIGATORIOS_DESDE                 and not sp_gates.parse_gates(text):
            errors.append(f"modo auto exige 'gates:' executáveis (SP de {GATES_OBRIGATORIOS_DESDE} em diante)")
        errors += sp_gates.problems(sp_gates.parse_gates(text))
        novo = str(fm.get("date", "")) >= sp_aprovacao.DESDE and fm.get("kind") != "program" and not fm.get("origem")
        if novo and not sp_gates.parse_gates(text):
            errors.append("SP novo exige 'gates:' executáveis (ponto 6 do grill: gate executável)")
        if novo and not _decisoes(text):
            errors.append("SP novo exige '## Decisões' não vazia (o grill-me fica registado)")
        if fm.get("ui") == "sim" and not _esboco(text):
            errors.append("ui: sim exige a secção '## Esboço' (ASCII ou mermaid)")
        if "permitir" in fm:
            cmds = kaizen_engine.parse_permitir(fm["permitir"])
            if not cmds:
                errors.append("permitir vazio")
            errors += [f"permitir proibido ({sp_gates.forbidden(c)}): {c}" for c in cmds if sp_gates.forbidden(c)]
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
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    import kf_errlog
    sys.exit(kf_errlog.executar("sp-validate", main))
