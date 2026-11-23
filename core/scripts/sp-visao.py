#!/usr/bin/env python3
"""VISION.md por projeto: a entrada estável da factory (objetivo de alto nível, validável por máquina).

Uso:
  python -I scripts/sp-visao.py init <projeto> [--dir DIR] [--force]   cria DIR/<projeto>/VISION.md (esqueleto com `TBD`)
  python -I scripts/sp-visao.py validate <ficheiro>                    rc 0 só com tudo preenchido e critérios verificáveis
  python -I scripts/sp-visao.py resumo <ficheiro>                      resumo de um ecrã de um VISION.md válido
Frontmatter: projeto, ui (sim|nao), stack, design_system, orcamento. Secções: Goal, Users, Success criteria, Constraints, Non-goals, Milestones.
Cada critério de sucesso (`- [ ] ...`) leva um comando em `código` ou começa por «Observação:».
Nunca sobrescreve sem `--force`.
rc: 0 ok · 1 inválido, inexistente ou já existe · 2 uso
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402

SECCOES = ("Goal", "Users", "Success criteria", "Constraints", "Non-goals", "Milestones")
CAMPOS = ("projeto", "ui", "stack", "design_system", "orcamento")
NOME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
PLACEHOLDER = re.compile(r"^\W*(tbd|todo|preencher|fixme|xxx|\.\.\.|…)\W*$|^[(<\[]\s*(preencher|tbd|todo)[^)>\]]*[)>\]]$", re.I)
CRITERIO = re.compile(r"^\s*[-*]\s*\[[ xX]\]\s*(.*)$")
SEM_DS = {"", "nenhum", "nao", "não", "none", "-"}

ESQUELETO = """---
projeto: {projeto}
ui: nao
stack: TBD
design_system: nenhum
orcamento: TBD
---
# {projeto}: visão

Objetivo de alto nível para a factory. Validar: `kaizen vision validate`. Substituir cada `TBD`.
`ui: sim` exige `design_system` (caminho do `DESIGN.md`, ver `kaizen ds init`). `orcamento`: teto por SP e por dia, com números (ex.: `5 USD por SP, 20 USD por dia`).

## Goal
TBD

## Users
- TBD

## Success criteria
- [ ] TBD (um comando em `código`, ou «Observação: ...»)

## Constraints
- TBD

## Non-goals
- TBD

## Milestones
1. TBD
"""


def _ler(caminho):
    p = Path(caminho)
    if not p.is_file():
        raise FileNotFoundError(f"ficheiro não encontrado: {p}")
    return p.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")


def _seccoes(texto):
    """Devolve {titulo: [linhas]} das secções `## X` (o corpo sem frontmatter)."""
    corpo = texto.split("\n---\n", 1)[1] if texto.startswith("---") and "\n---\n" in texto else texto
    out, atual = {}, None
    for linha in corpo.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", linha)
        if m:
            atual = m.group(1)
            out.setdefault(atual, [])
        elif atual is not None:
            out[atual].append(linha)
    return out


def _util(linhas):
    """Linhas com conteúdo real, sem marcadores de lista nem placeholders."""
    res = []
    for linha in linhas:
        s = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*(?:\[[ xX]\]\s*)?", "", linha).strip()
        if s and not PLACEHOLDER.match(s):
            res.append(s)
    return res


def _criterio_verificavel(texto):
    return bool(re.search(r"`[^`]+`", texto)) or bool(re.match(r"^observa[cç][aã]o\s*:\s*\S", texto, re.I))


def analisar(texto):
    """Devolve (campos, seccoes, problemas)."""
    problemas = []
    if not texto.startswith("---"):
        return {}, {}, ["frontmatter em falta (o ficheiro tem de abrir com `---`)"]
    campos = kaizen_engine.parse_frontmatter(texto)
    for c in CAMPOS:
        v = str(campos.get(c, "")).strip()
        if not v or PLACEHOLDER.match(v):
            problemas.append(f"frontmatter: `{c}` por preencher")
    ui = str(campos.get("ui", "")).strip().lower()
    if ui and ui not in ("sim", "nao") and not PLACEHOLDER.match(ui):
        problemas.append("frontmatter: `ui` tem de ser `sim` ou `nao`")
    elif ui == "sim" and str(campos.get("design_system", "")).strip().lower() in SEM_DS:
        problemas.append("frontmatter: `design_system` obrigatório com `ui: sim`")
    orc = str(campos.get("orcamento", "")).strip()
    if orc and not PLACEHOLDER.match(orc) and not re.search(r"\d", orc):
        problemas.append("frontmatter: `orcamento` sem número (teto por SP e por dia)")
    seccoes = _seccoes(texto)
    for sec in SECCOES:
        if sec not in seccoes:
            problemas.append(f"secção em falta: {sec}")
        elif not _util(seccoes[sec]):
            problemas.append(f"secção por preencher: {sec}")
    if "Success criteria" in seccoes:
        criterios = [m.group(1).strip() for ln in seccoes["Success criteria"] if (m := CRITERIO.match(ln))]
        if _util(seccoes["Success criteria"]) and not criterios:
            problemas.append("Success criteria: usar a lista `- [ ] critério`")
        for c in criterios:
            if c and not PLACEHOLDER.match(c) and not _criterio_verificavel(c):
                problemas.append(f"critério sem comando nem «Observação:»: {c}")
    return campos, seccoes, problemas


def cmd_init(projeto, base, force):
    if not NOME.match(projeto or ""):
        print("erro: nome de projeto inválido (letras, dígitos, `.`, `_`, `-`; sem caminhos)", file=sys.stderr)
        return 2
    alvo = Path(base) / projeto / "VISION.md"
    if alvo.exists() and not force:
        print(f"erro: já existe {alvo} (usar --force)", file=sys.stderr)
        return 1
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(ESQUELETO.format(projeto=projeto), encoding="utf-8", newline="\n")
    print(f"criado {alvo}")
    return 0


def cmd_validate(ficheiro):
    try:
        _, _, problemas = analisar(_ler(ficheiro))
    except (FileNotFoundError, UnicodeDecodeError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
    if problemas:
        print(f"{ficheiro}: {len(problemas)} problema(s)", file=sys.stderr)
        for p in problemas:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"{ficheiro}: ok")
    return 0


def cmd_resumo(ficheiro):
    try:
        campos, seccoes, problemas = analisar(_ler(ficheiro))
    except (FileNotFoundError, UnicodeDecodeError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
    if problemas:
        print(f"erro: VISION.md inválido ({len(problemas)} problema(s); correr validate)", file=sys.stderr)
        return 1
    n = sum(1 for ln in seccoes["Success criteria"] if CRITERIO.match(ln))
    print(f"{campos['projeto']} · ui: {campos['ui']} · stack: {campos['stack']} · orçamento: {campos['orcamento']}")
    print(f"Goal: {' '.join(_util(seccoes['Goal']))}")
    print(f"{n} critérios · Milestones: {len(_util(seccoes['Milestones']))}")
    for m in _util(seccoes["Milestones"]):
        print(f"  - {m}")
    return 0


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    uso = "uso: sp-visao.py init <projeto> [--dir DIR] [--force] | validate <ficheiro> | resumo <ficheiro>"
    if not a or a[0] not in ("init", "validate", "resumo"):
        print(uso, file=sys.stderr)
        return 2
    sub, resto = a[0], a[1:]
    if sub == "init":
        base, force, pos = ".", False, []
        i = 0
        while i < len(resto):
            if resto[i] == "--force":
                force = True
            elif resto[i] == "--dir" and i + 1 < len(resto):
                base = resto[i + 1]
                i += 1
            else:
                pos.append(resto[i])
            i += 1
        if len(pos) != 1:
            print(uso, file=sys.stderr)
            return 2
        return cmd_init(pos[0], base, force)
    if len(resto) != 1:
        print(uso, file=sys.stderr)
        return 2
    return cmd_validate(resto[0]) if sub == "validate" else cmd_resumo(resto[0])


if __name__ == "__main__":
    sys.exit(main())
