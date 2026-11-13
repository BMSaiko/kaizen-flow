#!/usr/bin/env python3
"""Resumo de 1 ecrã de um SP para o user aprovar: Quê · Porquê · Forma · Limites · Prova · Destino.

Só leitura. Máximo 40 linhas de 100 colunas. Num SP-mãe acrescenta a tabela de filhos; com `ui: sim`
mostra a secção `## Esboço`. rc 1 se faltar matéria para alguma secção (o texto diz qual).

Uso:
  python -I scripts/sp-resumo.py <slug> [--project P]
rc: 0 completo, 1 falta matéria ou SP em falta
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402

sp_list = kaizen_engine.load("sp-list")
sp_validate = kaizen_engine.load("sp-validate")
sp_gates = kaizen_engine.load("sp-gates")

LARGURA, MAX_LINHAS = 100, 40


def _corta(linha):
    linha = linha.rstrip()
    return linha if len(linha) <= LARGURA else linha[:LARGURA - 1] + "…"


def _itens(corpo, maximo):
    """Linhas não vazias do corpo (marcadores de lista mantidos), cortadas e limitadas."""
    linhas = [_corta(x) for x in corpo.splitlines() if x.strip()]
    return linhas[:maximo]


def _seccao_extra(texto, titulo):
    """Corpo da secção `## <titulo>` (sem numeração), ou ''."""
    corpo, dentro = [], False
    for linha in texto.splitlines():
        if linha.startswith("## "):
            dentro = linha[3:].strip().lower().startswith(titulo.lower())
        elif dentro:
            corpo.append(linha)
    return "\n".join(corpo).strip("\n")


def _filhos(root, sp):
    kids = [s for s in sp_list.collect(root, include_done=True) if s.project == sp.project and s.parent == sp.slug]
    linhas = []
    for k in sorted(kids, key=lambda s: (len(s.depends_on), s.slug)):
        dep = f"depende de {', '.join(k.depends_on)}" if k.depends_on else "sem dependências"
        linhas.append(_corta(f"  {k.slug} [{k.status}] {dep}"))
    return linhas


def resumo(root, slug, project=None):
    """(rc, texto) do resumo do SP `slug`."""
    found = [s for s in sp_list.collect(root, include_done=True) if s.slug == slug and (not project or s.project == project)]
    if len(found) != 1:
        return 1, f"SP '{slug}' {'ambíguo (usar --project)' if found else 'não encontrado'}"
    sp = found[0]
    texto = sp.path.read_bytes().decode("utf-8")
    fm = sp_list.parse_frontmatter(texto)
    sec = sp_validate._sections(texto)
    mae = fm.get("kind") == "program"
    cmds = [_corta(f"- {g['cmd'].strip()}") for g in sp_gates.parse_gates(texto)]

    decisoes = _seccao_extra(texto, "Decisões")
    fora = [_corta(x.strip()) for x in decisoes.splitlines() if x.strip().lstrip("- ").lower().startswith("fora de âmbito")]
    limites = _itens(sec.get(5, ""), 4) + [x.lstrip() for x in fora]
    if fm.get("fora_de_escopo"):
        limites.append(_corta(f"- Fora de escopo: {fm['fora_de_escopo']}"))
    destino = " · ".join(f"{k} {fm[k]}" for k in ("commit", "push", "pr", "merge") if fm.get(k))
    if fm.get("modo"):
        destino = f"modo {fm['modo']} · {destino}" if destino else f"modo {fm['modo']}"

    partes = [
        ("Quê", _itens(sec.get(3, ""), 2)),
        ("Porquê", _itens(sec.get(1, ""), 2)),
        ("Forma", _itens(sec.get(7, ""), 3 if mae else 5)),
        ("Limites (fora de âmbito incluído)", limites[:5]),
        ("Prova (gates)", (cmds + _itens(sec.get(8, ""), 1))[:4]),
        ("Destino e autorizações", [_corta(destino)] if destino else []),
    ]
    if fm.get("ui") == "sim":
        partes.append(("Esboço", _itens(_seccao_extra(texto, "Esboço"), 10)))
    if mae:
        partes.insert(3, ("Filhos (entrega, dependências)", _filhos(root, sp)[:8]))

    saida, faltas = [f"RESUMO · {slug}"], []
    for titulo, linhas in partes:
        if not linhas:
            faltas.append(titulo.split(" (")[0])
            linhas = ["(em falta)"]
        saida += [f"{titulo}:"] + [x if x.startswith(" ") or x.startswith("-") or not x else f"  {x}" for x in linhas]
    if faltas:
        saida.append(_corta(f"FALTA matéria: {', '.join(faltas)}"))
    if len(saida) > MAX_LINHAS:
        saida = saida[:MAX_LINHAS - 1] + ["…"]
        if faltas:
            saida[-1] = _corta(f"FALTA matéria: {', '.join(faltas)}")
    return (1 if faltas else 0), "\n".join(saida)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Resumo de 1 ecrã de um SP")
    ap.add_argument("slug")
    ap.add_argument("--project")
    ap.add_argument("--root", default=str(sp_list.DEFAULT_ROOT), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    rc, texto = resumo(args.root, sp_list.normalize_ref(args.root, args.slug), args.project)
    print(texto)
    return rc


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import kf_errlog
    sys.exit(kf_errlog.executar("sp-resumo", main))
